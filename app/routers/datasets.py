"""Dataset CRUD router."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import ConflictError, NotFoundError
from app.schemas.dataset import DatasetCreate, DatasetResponse, DatasetUpdate
from app.services import dataset_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.post(
    "",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new dataset",
    description=(
        "Create a dataset with its columns. "
        "The FQN is derived from its four components: "
        "``connection.database.schema.table``."
    ),
)
def create_dataset(
    payload: DatasetCreate,
    db: Session = Depends(get_db),
) -> DatasetResponse:
    try:
        dataset = dataset_service.create_dataset(db, payload)
        return DatasetResponse.model_validate(dataset)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "",
    response_model=List[DatasetResponse],
    summary="List all datasets",
)
def list_datasets(
    skip: int = Query(default=0, ge=0, description="Offset for pagination"),
    limit: int = Query(default=50, ge=1, le=200, description="Page size"),
    db: Session = Depends(get_db),
) -> List[DatasetResponse]:
    datasets = dataset_service.list_datasets(db, skip=skip, limit=limit)
    return [DatasetResponse.model_validate(ds) for ds in datasets]


@router.get(
    "/{fqn:path}",
    response_model=DatasetResponse,
    summary="Get a dataset by FQN",
    description=(
        "Retrieve full metadata for a dataset using its fully qualified name "
        "(URL-encode dots if your client requires it — FastAPI handles both forms)."
    ),
)
def get_dataset(
    fqn: str,
    db: Session = Depends(get_db),
) -> DatasetResponse:
    dataset = dataset_service.get_dataset_by_fqn(db, fqn)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{fqn}' not found.",
        )
    return DatasetResponse.model_validate(dataset)


@router.put(
    "/{fqn:path}",
    response_model=DatasetResponse,
    summary="Update dataset metadata or columns",
    description=(
        "Update ``source_system``, ``description``, or replace the column list. "
        "FQN components (connection / database / schema / table) are immutable."
    ),
)
def update_dataset(
    fqn: str,
    payload: DatasetUpdate,
    db: Session = Depends(get_db),
) -> DatasetResponse:
    try:
        dataset = dataset_service.update_dataset(db, fqn, payload)
        return DatasetResponse.model_validate(dataset)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.delete(
    "/{fqn:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dataset",
    description="Deletes the dataset, its columns, and any lineage edges it participates in.",
)
def delete_dataset(
    fqn: str,
    db: Session = Depends(get_db),
) -> None:
    try:
        dataset_service.delete_dataset(db, fqn)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
