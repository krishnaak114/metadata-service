"""Dataset CRUD service."""

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import ConflictError, NotFoundError
from app.models.orm import Dataset, DatasetColumn
from app.schemas.dataset import DatasetCreate, DatasetUpdate

logger = logging.getLogger(__name__)


def get_dataset_by_fqn(db: Session, fqn: str) -> Optional[Dataset]:
    """Return a Dataset by its FQN, or None if not found."""
    return db.scalar(select(Dataset).where(Dataset.fqn == fqn))


def list_datasets(db: Session, skip: int = 0, limit: int = 50) -> List[Dataset]:
    """Return a paginated list of all datasets."""
    stmt = select(Dataset).offset(skip).limit(limit).order_by(Dataset.fqn)
    return list(db.scalars(stmt).all())


def create_dataset(db: Session, payload: DatasetCreate) -> Dataset:
    """
    Create a new dataset with its columns.

    Raises
    ------
    ValueError
        If a dataset with the same FQN already exists.
    """
    fqn = payload.fqn
    if get_dataset_by_fqn(db, fqn):
        raise ConflictError(f"Dataset '{fqn}' already exists.")

    dataset = Dataset(
        fqn=fqn,
        connection_name=payload.connection_name,
        database_name=payload.database_name,
        schema_name=payload.schema_name,
        table_name=payload.table_name,
        source_system=payload.source_system,
        description=payload.description,
    )

    # Bulk-create columns
    dataset.columns = [
        DatasetColumn(
            name=col.name.strip(),
            data_type=col.data_type.strip().upper(),
            description=col.description,
        )
        for col in payload.columns
    ]

    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    logger.info("Created dataset: %s", fqn)
    return dataset


def update_dataset(db: Session, fqn: str, payload: DatasetUpdate) -> Dataset:
    """
    Update mutable fields on an existing dataset.

    If ``columns`` is provided in the payload, the entire column list is
    replaced (upsert-by-name is intentionally avoided for simplicity).

    Raises
    ------
    ValueError
        If the dataset does not exist.
    """
    dataset = get_dataset_by_fqn(db, fqn)
    if not dataset:
        raise NotFoundError(f"Dataset '{fqn}' not found.")

    if payload.source_system is not None:
        dataset.source_system = payload.source_system
    if payload.description is not None:
        dataset.description = payload.description

    if payload.columns is not None:
        # Replace column list
        for col in dataset.columns:
            db.delete(col)
        db.flush()
        dataset.columns = [
            DatasetColumn(
                dataset_id=dataset.id,
                name=col.name.strip(),
                data_type=col.data_type.strip().upper(),
                description=col.description,
            )
            for col in payload.columns
        ]

    db.commit()
    db.refresh(dataset)
    logger.info("Updated dataset: %s", fqn)
    return dataset


def delete_dataset(db: Session, fqn: str) -> None:
    """
    Delete a dataset and all its columns and lineage edges.

    Raises
    ------
    ValueError
        If the dataset does not exist.
    """
    dataset = get_dataset_by_fqn(db, fqn)
    if not dataset:
        raise NotFoundError(f"Dataset '{fqn}' not found.")

    db.delete(dataset)
    db.commit()
    logger.info("Deleted dataset: %s", fqn)
