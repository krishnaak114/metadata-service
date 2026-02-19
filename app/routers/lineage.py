"""Lineage management router."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import ConflictError, CycleError, NotFoundError
from app.schemas.dataset import (
    DatasetLineageResponse,
    LineageCreate,
    LineageEdgeResponse,
)
from app.services import lineage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lineage", tags=["Lineage"])


@router.post(
    "",
    response_model=LineageEdgeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a lineage edge",
    description=(
        "Define that ``upstream_fqn`` produces ``downstream_fqn``. "
        "Cycles are rejected with a descriptive error message."
    ),
)
def add_lineage(
    payload: LineageCreate,
    db: Session = Depends(get_db),
) -> LineageEdgeResponse:
    try:
        edge = lineage_service.add_lineage(
            db,
            upstream_fqn=payload.upstream_fqn,
            downstream_fqn=payload.downstream_fqn,
        )
        db.refresh(edge)
        return LineageEdgeResponse.model_validate(edge)
    except CycleError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a lineage edge",
    description="Delete the directed edge between two datasets.",
)
def remove_lineage(
    upstream_fqn: str = Query(..., description="FQN of the upstream (source) dataset"),
    downstream_fqn: str = Query(..., description="FQN of the downstream (target) dataset"),
    db: Session = Depends(get_db),
) -> None:
    try:
        lineage_service.remove_lineage(db, upstream_fqn, downstream_fqn)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{fqn:path}",
    response_model=DatasetLineageResponse,
    summary="Get lineage for a dataset",
    description=(
        "Returns the dataset's direct upstream (sources) and downstream (targets). "
        "Use the full FQN as the path parameter."
    ),
)
def get_lineage(
    fqn: str,
    db: Session = Depends(get_db),
) -> DatasetLineageResponse:
    try:
        return lineage_service.get_dataset_lineage(db, fqn)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "",
    response_model=List[LineageEdgeResponse],
    summary="List all lineage edges",
    description="Return the full lineage graph as a list of directed edges.",
)
def list_all_lineage(
    db: Session = Depends(get_db),
) -> List[LineageEdgeResponse]:
    edges = lineage_service.get_all_lineage_edges(db)
    return [LineageEdgeResponse.model_validate(e) for e in edges]
