"""
Search service — priority-ordered full-text search across datasets.

Search priority (lower number = shown first):
    1  table_name     — FQN table component matches query
    2  column_name    — any column name in the dataset matches query
    3  schema_name    — FQN schema component matches query
    4  database_name  — FQN database component matches query

De-duplication: a dataset is returned at most once, at its highest-priority
match type.  If a dataset matches multiple criteria, only the best one appears.
"""

import logging
from typing import List

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.orm import Dataset, DatasetColumn
from app.schemas.dataset import DatasetResponse, LineageNodeResponse, SearchResponse, SearchResultItem

logger = logging.getLogger(__name__)

# Priority constants — these directly match the assignment spec
_PRIORITY = {
    "table_name": 1,
    "column_name": 2,
    "schema_name": 3,
    "database_name": 4,
}


def search_datasets(db: Session, query: str, limit: int = 50) -> SearchResponse:
    """
    Search datasets by name components and column names.

    The search is case-insensitive and uses SQL LIKE with ``%query%``
    for substring matching.

    Parameters
    ----------
    db:    Active SQLAlchemy session.
    query: Search term (e.g. "order").
    limit: Maximum number of results to return.

    Returns
    -------
    SearchResponse
        Priority-sorted, de-duplicated search results.
    """
    if not query or not query.strip():
        return SearchResponse(query=query, total=0, results=[])

    term = query.strip()
    like = f"%{term}%"

    # ── 1: table_name matches ────────────────────────────────────────────────
    table_matches = list(
        db.scalars(
            select(Dataset).where(Dataset.table_name.ilike(like))
        ).all()
    )

    # ── 2: column_name matches ───────────────────────────────────────────────
    # fetch dataset IDs that have a matching column
    col_dataset_ids = list(
        db.scalars(
            select(DatasetColumn.dataset_id).where(
                DatasetColumn.name.ilike(like)
            ).distinct()
        ).all()
    )
    col_dataset_map: dict[int, str] = {}  # dataset_id → matched column name
    if col_dataset_ids:
        for col in db.scalars(
            select(DatasetColumn).where(
                DatasetColumn.dataset_id.in_(col_dataset_ids),
                DatasetColumn.name.ilike(like),
            )
        ).all():
            # store first matched column name per dataset
            col_dataset_map.setdefault(col.dataset_id, col.name)

    col_datasets = (
        list(db.scalars(select(Dataset).where(Dataset.id.in_(col_dataset_ids))).all())
        if col_dataset_ids
        else []
    )

    # ── 3: schema_name matches ───────────────────────────────────────────────
    schema_matches = list(
        db.scalars(
            select(Dataset).where(Dataset.schema_name.ilike(like))
        ).all()
    )

    # ── 4: database_name matches ─────────────────────────────────────────────
    db_matches = list(
        db.scalars(
            select(Dataset).where(Dataset.database_name.ilike(like))
        ).all()
    )

    # ── De-duplicate by FQN (keep highest priority match) ───────────────────
    seen_fqns: set[str] = set()
    results: List[SearchResultItem] = []

    def _add(dataset: Dataset, match_type: str, matched_on: str) -> None:
        if dataset.fqn in seen_fqns:
            return
        seen_fqns.add(dataset.fqn)
        upstream = [
            LineageNodeResponse.model_validate(edge.upstream)
            for edge in dataset.upstream_edges
        ]
        downstream = [
            LineageNodeResponse.model_validate(edge.downstream)
            for edge in dataset.downstream_edges
        ]
        results.append(
            SearchResultItem(
                dataset=DatasetResponse.model_validate(dataset),
                match_type=match_type,
                matched_on=matched_on,
                priority=_PRIORITY[match_type],
                upstream_datasets=upstream,
                downstream_datasets=downstream,
            )
        )

    for ds in table_matches:
        _add(ds, "table_name", ds.table_name)

    for ds in col_datasets:
        _add(ds, "column_name", col_dataset_map.get(ds.id, term))

    for ds in schema_matches:
        _add(ds, "schema_name", ds.schema_name)

    for ds in db_matches:
        _add(ds, "database_name", ds.database_name)

    # Results are already insertion-ordered by priority (we added in order 1→4)
    # but sort explicitly to be safe
    results.sort(key=lambda r: (r.priority, r.dataset.fqn))

    total = len(results)
    logger.info("Search '%s' → %d result(s)", term, total)
    return SearchResponse(query=term, total=total, results=results[:limit])
