"""
Shared pytest fixtures for the metadata service test suite.

Uses an in-memory SQLite database so tests run without MySQL.
The FastAPI TestClient provides a fully wired ASGI test harness.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# ── In-memory SQLite engine (no MySQL required for tests) ─────────────────────
# StaticPool ensures all connections reuse the same in-memory database so that
# tables created in reset_db are visible to sessions opened inside the TestClient.
SQLITE_URL = "sqlite://"

_engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSession = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_db():
    """Drop and recreate all tables before each test for isolation."""
    # Import ORM models so metadata knows about all tables
    from app.models import orm  # noqa: F401

    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    yield


@pytest.fixture
def client(reset_db) -> TestClient:
    """Return a TestClient with the DB dependency overridden."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
