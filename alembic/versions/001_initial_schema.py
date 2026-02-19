"""Initial schema — datasets, dataset_columns, lineage

Revision ID: 001
Revises: 
Create Date: 2026-02-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── datasets ──────────────────────────────────────────────────────────────
    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fqn", sa.String(512), nullable=False),
        sa.Column("connection_name", sa.String(128), nullable=False),
        sa.Column("database_name", sa.String(128), nullable=False),
        sa.Column("schema_name", sa.String(128), nullable=False),
        sa.Column("table_name", sa.String(128), nullable=False),
        sa.Column(
            "source_system",
            sa.Enum("MySQL", "MSSQL", "PostgreSQL", "Snowflake", "BigQuery", "Other", name="sourcesystem"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_datasets_fqn", "datasets", ["fqn"], unique=True)
    op.create_index("ix_datasets_connection_name", "datasets", ["connection_name"])
    op.create_index("ix_datasets_database_name", "datasets", ["database_name"])
    op.create_index("ix_datasets_schema_name", "datasets", ["schema_name"])
    op.create_index("ix_datasets_table_name", "datasets", ["table_name"])

    # ── dataset_columns ───────────────────────────────────────────────────────
    op.create_table(
        "dataset_columns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("data_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "name", name="uq_column_dataset_name"),
    )
    op.create_index("ix_column_name", "dataset_columns", ["name"])

    # ── lineage ───────────────────────────────────────────────────────────────
    op.create_table(
        "lineage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("upstream_id", sa.Integer(), nullable=False),
        sa.Column("downstream_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["upstream_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["downstream_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upstream_id", "downstream_id", name="uq_lineage_edge"),
    )
    op.create_index("ix_lineage_upstream", "lineage", ["upstream_id"])
    op.create_index("ix_lineage_downstream", "lineage", ["downstream_id"])


def downgrade() -> None:
    op.drop_table("lineage")
    op.drop_index("ix_column_name", table_name="dataset_columns")
    op.drop_table("dataset_columns")
    op.drop_index("ix_datasets_fqn", table_name="datasets")
    op.drop_table("datasets")
    op.execute("DROP TYPE IF EXISTS sourcesystem")
