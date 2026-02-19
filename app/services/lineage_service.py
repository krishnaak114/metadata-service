"""
Lineage service — creates and queries directed dataset lineage edges.

Cycle prevention is enforced here using a DFS-based graph check
before any edge is written to the database.
"""

import logging
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import ConflictError, CycleError, NotFoundError
from app.models.orm import Dataset, Lineage
from app.schemas.dataset import DatasetLineageResponse, LineageNodeResponse
from app.services.dataset_service import get_dataset_by_fqn
from app.utils.graph import build_adjacency, would_create_cycle

logger = logging.getLogger(__name__)


def _load_full_adjacency(db: Session):
    """Load ALL lineage edges and build the adjacency map in one query."""
    edges = db.scalars(select(Lineage)).all()
    return build_adjacency(edges)


def add_lineage(db: Session, upstream_fqn: str, downstream_fqn: str) -> Lineage:
    """
    Create a directed lineage edge: upstream → downstream.

    Validates:
    1. Both datasets exist.
    2. The edge does not already exist (duplicate).
    3. Adding the edge would not create a cycle in the lineage DAG.

    Parameters
    ----------
    db:            Active SQLAlchemy session.
    upstream_fqn:  FQN of the source dataset.
    downstream_fqn: FQN of the target dataset.

    Returns
    -------
    Lineage
        The newly created lineage edge ORM object.

    Raises
    ------
    ValueError
        With a descriptive message for any of the three failure cases.
    """
    upstream = get_dataset_by_fqn(db, upstream_fqn)
    if not upstream:
        raise NotFoundError(f"Upstream dataset '{upstream_fqn}' not found.")

    downstream = get_dataset_by_fqn(db, downstream_fqn)
    if not downstream:
        raise NotFoundError(f"Downstream dataset '{downstream_fqn}' not found.")

    # Check for duplicate edge
    existing = db.scalar(
        select(Lineage).where(
            Lineage.upstream_id == upstream.id,
            Lineage.downstream_id == downstream.id,
        )
    )
    if existing:
        raise ConflictError(
            f"Lineage edge '{upstream_fqn}' → '{downstream_fqn}' already exists."
        )

    # ── Cycle detection ─────────────────────────────────────────────────────
    adjacency = _load_full_adjacency(db)

    if would_create_cycle(upstream.id, downstream.id, adjacency):
        raise CycleError(
            f"Cannot add lineage '{upstream_fqn}' → '{downstream_fqn}': "
            f"this would create a cycle. "
            f"'{upstream_fqn}' is already downstream of '{downstream_fqn}' "
            f"(directly or transitively)."
        )

    edge = Lineage(upstream_id=upstream.id, downstream_id=downstream.id)
    db.add(edge)
    db.commit()
    db.refresh(edge)
    logger.info("Created lineage: %s → %s", upstream_fqn, downstream_fqn)
    return edge


def remove_lineage(db: Session, upstream_fqn: str, downstream_fqn: str) -> None:
    """
    Delete a specific lineage edge.

    Raises
    ------
    ValueError
        If either dataset or the edge does not exist.
    """
    upstream = get_dataset_by_fqn(db, upstream_fqn)
    if not upstream:
        raise NotFoundError(f"Upstream dataset '{upstream_fqn}' not found.")

    downstream = get_dataset_by_fqn(db, downstream_fqn)
    if not downstream:
        raise NotFoundError(f"Downstream dataset '{downstream_fqn}' not found.")

    edge = db.scalar(
        select(Lineage).where(
            Lineage.upstream_id == upstream.id,
            Lineage.downstream_id == downstream.id,
        )
    )
    if not edge:
        raise NotFoundError(
            f"Lineage edge '{upstream_fqn}' → '{downstream_fqn}' does not exist."
        )

    db.delete(edge)
    db.commit()
    logger.info("Removed lineage: %s → %s", upstream_fqn, downstream_fqn)


def get_dataset_lineage(db: Session, fqn: str) -> DatasetLineageResponse:
    """
    Return a dataset's direct upstream and downstream neighbours.

    Parameters
    ----------
    fqn:  FQN of the dataset to inspect.

    Returns
    -------
    DatasetLineageResponse
        Dataset metadata + lists of direct upstream / downstream datasets.

    Raises
    ------
    ValueError
        If the dataset does not exist.
    """
    from app.schemas.dataset import DatasetResponse  # avoid circular at top-level

    dataset = get_dataset_by_fqn(db, fqn)
    if not dataset:
        raise NotFoundError(f"Dataset '{fqn}' not found.")

    upstream_datasets = [
        LineageNodeResponse.model_validate(edge.upstream)
        for edge in dataset.upstream_edges
    ]
    downstream_datasets = [
        LineageNodeResponse.model_validate(edge.downstream)
        for edge in dataset.downstream_edges
    ]

    return DatasetLineageResponse(
        dataset=DatasetResponse.model_validate(dataset),
        upstream_datasets=upstream_datasets,
        downstream_datasets=downstream_datasets,
    )


def get_all_lineage_edges(db: Session) -> List[Lineage]:
    """Return all lineage edges (used for graph visualisation / export)."""
    return list(db.scalars(select(Lineage)).all())
