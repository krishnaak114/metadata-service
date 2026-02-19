"""SQLAlchemy ORM models for the metadata service."""

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SourceSystem(str, enum.Enum):
    """Supported source system types."""

    MYSQL = "MySQL"
    MSSQL = "MSSQL"
    POSTGRESQL = "PostgreSQL"
    SNOWFLAKE = "Snowflake"
    BIGQUERY = "BigQuery"
    OTHER = "Other"


# ── Dataset ───────────────────────────────────────────────────────────────────

class Dataset(Base):
    """
    Represents a table or file in a data system.

    The fully qualified name (FQN) is the primary business key:
        <connection_name>.<database_name>.<schema_name>.<table_name>
    e.g. ``snowflake_prod.sales.public.orders``
    """

    __tablename__ = "datasets"

    # surrogate PK (joins are faster than string PKs on MySQL)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # FQN is the unique business identifier — used in all public API paths
    fqn: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)

    # FQN components stored separately for efficient search/filter
    connection_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    source_system: Mapped[SourceSystem] = mapped_column(
        Enum(SourceSystem), nullable=False, default=SourceSystem.OTHER
    )

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────
    columns: Mapped[List["DatasetColumn"]] = relationship(
        "DatasetColumn",
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Lineage edges where this dataset is the upstream source
    downstream_edges: Mapped[List["Lineage"]] = relationship(
        "Lineage",
        foreign_keys="Lineage.upstream_id",
        back_populates="upstream",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # Lineage edges where this dataset is the downstream target
    upstream_edges: Mapped[List["Lineage"]] = relationship(
        "Lineage",
        foreign_keys="Lineage.downstream_id",
        back_populates="downstream",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Dataset fqn={self.fqn!r}>"


# ── DatasetColumn ─────────────────────────────────────────────────────────────

class DatasetColumn(Base):
    """A single column/field belonging to a dataset."""

    __tablename__ = "dataset_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(64), nullable=False, default="STRING")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="columns")

    __table_args__ = (
        # A column name is unique within a dataset
        UniqueConstraint("dataset_id", "name", name="uq_column_dataset_name"),
        Index("ix_column_name", "name"),  # fast column-name search
    )

    def __repr__(self) -> str:
        return f"<DatasetColumn {self.name}:{self.data_type}>"


# ── Lineage ───────────────────────────────────────────────────────────────────

class Lineage(Base):
    """
    Directed edge in the dataset lineage graph.

        upstream ──produces──► downstream

    Both ``upstream_id`` and ``downstream_id`` are surrogate FK references
    to the ``datasets`` table.  The pair is unique (no duplicate edges).
    """

    __tablename__ = "lineage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    upstream_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    downstream_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    upstream: Mapped["Dataset"] = relationship(
        "Dataset", foreign_keys=[upstream_id], back_populates="downstream_edges"
    )
    downstream: Mapped["Dataset"] = relationship(
        "Dataset", foreign_keys=[downstream_id], back_populates="upstream_edges"
    )

    __table_args__ = (
        # No duplicate lineage edges
        UniqueConstraint("upstream_id", "downstream_id", name="uq_lineage_edge"),
        # No self-loops: enforced in service layer (DB constraint can't span two cols easily)
        Index("ix_lineage_upstream", "upstream_id"),
        Index("ix_lineage_downstream", "downstream_id"),
    )

    def __repr__(self) -> str:
        return f"<Lineage upstream_id={self.upstream_id} → downstream_id={self.downstream_id}>"
