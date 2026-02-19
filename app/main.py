"""
Metadata Service — FastAPI Application.

Entry point for the data governance metadata service.
Registers routers, configures CORS, and initialises the database
on startup using the lifespan context manager (FastAPI 0.95+ pattern).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.routers import datasets, lineage, search

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    logger.info("🚀 %s starting up (env=%s)", settings.app_name, settings.environment)

    if init_db():
        logger.info("✅ Database ready")
    else:
        logger.warning(
            "⚠️  Database initialisation failed — some endpoints may not work."
        )

    yield

    logger.info("🛑 %s shutting down", settings.app_name)


# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    description=(
        "Data governance metadata service.\n\n"
        "Manage dataset metadata, column definitions, and dataset-to-dataset lineage. "
        "Lineage is validated as a Directed Acyclic Graph (DAG) — cyclical edges are rejected."
    ),
    version="0.1.0",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(datasets.router, prefix=settings.api_prefix)
app.include_router(lineage.router, prefix=settings.api_prefix)
app.include_router(search.router, prefix=settings.api_prefix)


# ── Health / root ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
@app.get(f"{settings.api_prefix}/health", tags=["Health"])
async def health_check():
    """Liveness probe — always returns 200 if the process is alive."""
    return JSONResponse(
        {
            "status": "ok",
            "service": settings.app_name,
            "environment": settings.environment,
            "version": "0.1.0",
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production,
    )
