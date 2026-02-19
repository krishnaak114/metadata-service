"""
Pydantic v2 request / response schemas for the metadata service.

Follows the project-wide pattern of strict validation, Field constraints,
and model_config with json_schema_extra examples.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.orm import SourceSystem


# ── Shared / embeddable ───────────────────────────────────────────────────────

class ColumnBase(BaseModel):
    """Column definition — shared by create and response schemas."""

    name: str = Field(..., min_length=1, max_length=128, description="Column name")
    data_type: str = Field(
        default="STRING",
        max_length=64,
        description="Data type, e.g. VARCHAR, INT, TIMESTAMP",
    )
    description: Optional[str] = Field(default=None, max_length=512)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class ColumnResponse(ColumnBase):
    """Column as returned by the API."""

    id: int

    model_config = ConfigDict(from_attributes=True)


# ── Dataset schemas ───────────────────────────────────────────────────────────

class DatasetCreate(BaseModel):
    """
    Payload for creating a new dataset.

    The FQN is derived from the four component parts.
    Example::

        {
            "connection_name": "snowflake_prod",
            "database_name": "sales",
            "schema_name": "public",
            "table_name": "orders",
            "source_system": "Snowflake",
            "columns": [
                {"name": "order_id", "data_type": "INT"},
                {"name": "customer_id", "data_type": "INT"}
            ]
        }
    """

    connection_name: str = Field(..., min_length=1, max_length=128)
    database_name: str = Field(..., min_length=1, max_length=128)
    schema_name: str = Field(..., min_length=1, max_length=128)
    table_name: str = Field(..., min_length=1, max_length=128)

    source_system: SourceSystem = Field(
        default=SourceSystem.OTHER,
        description="Source system type",
    )
    description: Optional[str] = Field(default=None, max_length=1024)
    columns: List[ColumnBase] = Field(default_factory=list)

    # Validators normalize component names (lowercase, strip whitespace)
    @field_validator("connection_name", "database_name", "schema_name", "table_name", mode="before")
    @classmethod
    def normalize_component(cls, v: str) -> str:
        return v.strip().lower()

    @property
    def fqn(self) -> str:
        """Computed FQN — convenience for service layer."""
        return f"{self.connection_name}.{self.database_name}.{self.schema_name}.{self.table_name}"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "connection_name": "snowflake_prod",
                    "database_name": "bi_team",
                    "schema_name": "bronze",
                    "table_name": "orders_raw",
                    "source_system": "Snowflake",
                    "description": "Raw orders ingested from transactional DB",
                    "columns": [
                        {"name": "order_id", "data_type": "INT"},
                        {"name": "customer_id", "data_type": "INT"},
                        {"name": "order_date", "data_type": "TIMESTAMP"},
                    ],
                }
            ]
        }
    )


class DatasetUpdate(BaseModel):
    """
    Payload for updating an existing dataset.

    FQN components are immutable after creation — only metadata and columns
    can be updated.
    """

    source_system: Optional[SourceSystem] = None
    description: Optional[str] = Field(default=None, max_length=1024)
    columns: Optional[List[ColumnBase]] = None


class DatasetResponse(BaseModel):
    """Full dataset representation returned by the API."""

    fqn: str
    connection_name: str
    database_name: str
    schema_name: str
    table_name: str
    source_system: SourceSystem
    description: Optional[str]
    columns: List[ColumnResponse]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Lineage schemas ───────────────────────────────────────────────────────────

class LineageCreate(BaseModel):
    """
    Payload for creating a directed lineage edge.

    ``upstream_fqn`` produces / feeds into ``downstream_fqn``.

    Example::

        {
            "upstream_fqn":   "snowflake_prod.bi_team.bronze.orders_raw",
            "downstream_fqn": "snowflake_prod.bi_team.silver.orders_clean"
        }
    """

    upstream_fqn: str = Field(..., min_length=1, max_length=512)
    downstream_fqn: str = Field(..., min_length=1, max_length=512)

    @model_validator(mode="after")
    def check_not_self_loop(self) -> "LineageCreate":
        if self.upstream_fqn == self.downstream_fqn:
            raise ValueError("upstream_fqn and downstream_fqn must be different datasets.")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "upstream_fqn": "snowflake_prod.bi_team.bronze.orders_raw",
                    "downstream_fqn": "snowflake_prod.bi_team.silver.orders_clean",
                }
            ]
        }
    )


class LineageNodeResponse(BaseModel):
    """Minimal dataset info embedded in a lineage response."""

    fqn: str
    source_system: SourceSystem
    description: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class LineageEdgeResponse(BaseModel):
    """A single directed edge in the lineage graph."""

    upstream: LineageNodeResponse
    downstream: LineageNodeResponse
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetLineageResponse(BaseModel):
    """
    Full lineage view for a dataset.

    ``upstream_datasets``  — direct parents (what feeds this dataset)
    ``downstream_datasets`` — direct children (what this dataset feeds)
    """

    dataset: DatasetResponse
    upstream_datasets: List[LineageNodeResponse]
    downstream_datasets: List[LineageNodeResponse]


# ── Search schemas ─────────────────────────────────────────────────────────────

class SearchMatchType(str):
    TABLE_NAME = "table_name"
    COLUMN_NAME = "column_name"
    SCHEMA_NAME = "schema_name"
    DATABASE_NAME = "database_name"


class SearchResultItem(BaseModel):
    """A single search result with match context and lineage."""

    dataset: DatasetResponse
    match_type: str = Field(
        description="What matched: table_name | column_name | schema_name | database_name"
    )
    matched_on: str = Field(description="The specific value that matched the query")
    priority: int = Field(description="Lower = higher priority (1 is best)")
    upstream_datasets: List[LineageNodeResponse] = Field(
        default_factory=list,
        description="Direct upstream datasets (sources that feed this dataset)",
    )
    downstream_datasets: List[LineageNodeResponse] = Field(
        default_factory=list,
        description="Direct downstream datasets (what this dataset feeds into)",
    )


class SearchResponse(BaseModel):
    """Paginated search results sorted by priority."""

    query: str
    total: int
    results: List[SearchResultItem]
