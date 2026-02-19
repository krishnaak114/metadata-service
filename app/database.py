"""
Database engine and session configuration.

Uses SQLAlchemy 2.x with connection pooling.  Session management follows
the FastAPI dependency-injection pattern (yield-based).
"""

import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


# ── SQLAlchemy engine ────────────────────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    pool_pre_ping=settings.db_pool_pre_ping,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    echo=not settings.is_production,  # SQL logging in dev only
)


# ── Declarative base (shared by all ORM models) ───────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Session factory ───────────────────────────────────────────────────────────
SessionFactory = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Session:
    """
    FastAPI dependency that yields a database session and guarantees cleanup.

    Usage::

        @router.get("/")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


def init_db() -> bool:
    """
    Verify database connectivity and create tables if they do not exist.

    Called once during application startup.  Returns True on success.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified.")
        # Import here to avoid circular import at module level
        from app.models import orm  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ready.")
        return True
    except Exception as exc:
        logger.error("Database initialization failed: %s", exc)
        return False
