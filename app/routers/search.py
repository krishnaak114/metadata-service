"""Search router."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.dataset import SearchResponse
from app.services import search_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "",
    response_model=SearchResponse,
    summary="Search datasets",
    description=(
        "Full-text search across table names, column names, schema names, and database names. "
        "Results are sorted by match priority:\n\n"
        "1. **table_name** — exact table component contains the query\n"
        "2. **column_name** — any column in the dataset contains the query\n"
        "3. **schema_name** — schema component contains the query\n"
        "4. **database_name** — database component contains the query\n\n"
        "Each dataset appears **at most once** at its highest-priority match."
    ),
)
def search(
    q: str = Query(..., min_length=1, description="Search term, e.g. 'order'"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results to return"),
    db: Session = Depends(get_db),
) -> SearchResponse:
    return search_service.search_datasets(db, query=q, limit=limit)
