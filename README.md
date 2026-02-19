# Metadata Service

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?style=flat&logo=mysql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x-D71F00?style=flat)
![Alembic](https://img.shields.io/badge/Alembic-1.13-6BA539?style=flat)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat&logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-50%20Passing-brightgreen?style=flat)
![License](https://img.shields.io/badge/License-MIT-blue?style=flat)

A **production-ready data governance metadata service** for managing dataset metadata, column definitions, and dataset-to-dataset lineage across data systems.

The lineage graph is enforced as a **Directed Acyclic Graph (DAG)** at all times — cycles are detected via DFS and rejected before any write reaches the database.

**Repository:** [github.com/krishnaak114/metadata-service](https://github.com/krishnaak114/metadata-service)
**Author:** [Krishna Agrawal](https://www.linkedin.com/in/agrawal-krishna-aa11a61ba/) | [@krishnaak114](https://github.com/krishnaak114)

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
  - [Run with Docker Compose](#run-with-docker-compose)
  - [Run Locally without Docker](#run-locally-without-docker)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [API Reference](#api-reference)
  - [Datasets](#datasets)
  - [Lineage](#lineage)
  - [Search](#search)
  - [Health](#health)
- [Request and Response Examples](#request-and-response-examples)
- [Lineage and Cycle Detection](#lineage-and-cycle-detection)
- [Search Behaviour](#search-behaviour)
- [Architecture Decisions](#architecture-decisions)
- [Project Structure](#project-structure)
- [Database Schema](#database-schema)
- [Code Quality](#code-quality)

---

## Features

- **Dataset Registry** — store and manage dataset metadata identified by a fully qualified name (FQN)
- **Column Definitions** — each dataset carries its field/column schema (name, type, description)
- **Lineage Tracking** — define upstream/downstream relationships between datasets
- **DAG Enforcement** — iterative DFS cycle detection runs before every lineage write; cycles are rejected with a descriptive error
- **Priority Search** — case-insensitive substring search across table name, column name, schema name, and database name — sorted by priority
- **Lineage Embedded in Search** — every search result includes the dataset's direct upstream and downstream neighbours
- **Paginated List** — `GET /datasets` supports `skip`/`limit` pagination
- **One-command Docker Setup** — `docker compose up --build` starts MySQL + API
- **Zero-dependency Tests** — test suite runs on in-memory SQLite; no MySQL needed for `pytest`

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI 0.115 |
| Language | Python 3.11+ |
| ORM | SQLAlchemy 2.x (mapped columns, typed relationships) |
| Database | MySQL 8.0 (production) / SQLite in-memory (tests) |
| Migrations | Alembic 1.13 |
| Validation | Pydantic v2 |
| Config | pydantic-settings + `.env` file |
| Containerisation | Docker + Docker Compose |
| Dependency Management | Poetry |
| Linter + Formatter | Ruff (replaces black + flake8 + isort) |
| Pre-commit | pre-commit hooks |
| Test Framework | pytest + FastAPI TestClient |

---

## Quick Start

### Run with Docker Compose

**Prerequisites:** Docker and Docker Compose installed.

```bash
# 1. Clone the repository
git clone https://github.com/krishnaak114/metadata-service
cd metadata-service

# 2. Copy the environment file (defaults work out of the box with docker-compose)
cp .env.example .env

# 3. Start the full stack — MySQL 8 + API
docker compose up --build
```

The API is then available at:

| URL | Description |
|---|---|
| `http://localhost:8000/api/v1/docs` | Swagger UI — interactive API explorer |
| `http://localhost:8000/api/v1/redoc` | ReDoc — readable API documentation |
| `http://localhost:8000/api/v1/health` | Liveness probe |

> On first boot the API waits for MySQL to pass its healthcheck (~20-30 s), then auto-creates all tables.

---

### Run Locally without Docker

**Prerequisites:** Python 3.11+, Poetry, a running MySQL 8 instance.

```bash
# 1. Install Poetry
pip install poetry

# 2. Install all dependencies (including dev)
poetry install

# 3. Configure environment
cp .env.example .env
# Edit DATABASE_URL in .env to point at your local MySQL

# 4. Apply database migrations
poetry run alembic upgrade head

# 5. Start the dev server with auto-reload
poetry run uvicorn app.main:app --reload --port 8000
```

---

## Environment Variables

All settings are read from `.env` (or real environment variables). Copy `.env.example` to get started.

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `Metadata Service` | Application name shown in logs and Swagger UI |
| `ENVIRONMENT` | `development` | `development` or `production` — disables SQL echo in production |
| `LOG_LEVEL` | `INFO` | Python logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `API_PREFIX` | `/api/v1` | URL prefix applied to all routes |
| `DATABASE_URL` | `mysql+pymysql://metadata_user:metadata_pass@db:3306/metadata_db` | SQLAlchemy connection string |
| `DB_POOL_SIZE` | `5` | SQLAlchemy connection pool size |
| `DB_MAX_OVERFLOW` | `10` | Extra connections allowed above pool size |
| `DB_POOL_PRE_PING` | `true` | Validate connections before checkout (recommended for MySQL) |

> `DATABASE_URL` must use the `mysql+pymysql://` or `mysql+mysqlconnector://` scheme. Any other scheme is rejected at startup with a clear validation error.

---

## Running Tests

Tests use an **in-memory SQLite** database. No MySQL, no Docker needed.

```bash
poetry run pytest -v
```

Expected output: `50 passed`

### Test Coverage

| Test file | What is covered |
|---|---|
| `tests/test_datasets.py` | Create (success, FQN normalisation to lowercase, duplicate 409, empty columns, invalid enum 422), GET, list with pagination, update, delete |
| `tests/test_lineage.py` | Valid chain creation, missing upstream/downstream 404, duplicate edge 409, self-loop 422, direct cycle 422, transitive cycle 422, diamond DAG valid, delete edge, lineage query |
| `tests/test_search.py` | Priority ordering (14), deduplication, table/column/schema/database match, lineage embedded in results, limit respected, missing query 422 |
| `tests/test_graph.py` | Pure unit tests for `would_create_cycle()` and `build_adjacency()` — no DB, no HTTP layer |

Each test gets a fresh database via an `autouse` pytest fixture that drops and recreates all SQLite tables before every test.

---

## API Reference

All routes are prefixed with `/api/v1`.

### Datasets

| Method | Path | Status codes | Description |
|---|---|---|---|
| `POST` | `/datasets` | 201, 409, 422 | Register a new dataset with columns |
| `GET` | `/datasets` | 200 | List all datasets (paginated, ordered by FQN) |
| `GET` | `/datasets/{fqn}` | 200, 404 | Get a single dataset by FQN |
| `PUT` | `/datasets/{fqn}` | 200, 404, 422 | Update description, source system, or columns |
| `DELETE` | `/datasets/{fqn}` | 204, 404 | Delete a dataset and cascade to columns + lineage edges |

**FQN format:** `connection_name.database_name.schema_name.table_name`
Example: `snowflake_prod.bi_team.bronze.orders_raw`

**Important rules:**
- FQN components are normalised to **lowercase** on creation (`MySQL_Prod` becomes `mysql_prod`)
- FQN components are **immutable** after creation — only `source_system`, `description`, and `columns` can be updated
- Deleting a dataset removes all its columns and any lineage edges it participates in (cascade)

**Pagination query parameters for `GET /datasets`:**

| Parameter | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `skip` | int | `0` | >= 0 | Number of records to skip |
| `limit` | int | `50` | 1-200 | Maximum number of records to return |

**Supported `source_system` values:** `MySQL`, `MSSQL`, `PostgreSQL`, `Snowflake`, `BigQuery`, `Other`

---

### Lineage

| Method | Path | Status codes | Description |
|---|---|---|---|
| `POST` | `/lineage` | 201, 404, 409, 422 | Add a directed edge: upstream produces downstream |
| `GET` | `/lineage` | 200 | List all lineage edges in the graph |
| `GET` | `/lineage/{fqn}` | 200, 404 | Get direct upstream and downstream datasets for a given FQN |
| `DELETE` | `/lineage?upstream_fqn=&downstream_fqn=` | 204, 404 | Remove a specific directed edge |

**Error codes for `POST /lineage`:**

| Code | Reason |
|---|---|
| 404 | Upstream or downstream dataset does not exist |
| 409 | This exact edge already exists |
| 422 | Adding the edge would create a cycle in the DAG |

---

### Search

| Method | Path | Status codes | Description |
|---|---|---|---|
| `GET` | `/search` | 200, 422 | Search datasets by name components and column names |

**Query parameters:**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `q` | string | Yes | — | min_length=1 | Search term |
| `limit` | int | No | `50` | 1-200 | Maximum number of results |

**Search priority:**

| Priority | Match on | Example |
|---|---|---|
| 1 | `table_name` | table name contains the query |
| 2 | `column_name` | any column in the dataset contains the query |
| 3 | `schema_name` | schema name contains the query |
| 4 | `database_name` | database name contains the query |

- Search is **case-insensitive** (SQL `ILIKE '%term%'`)
- Each dataset appears **at most once**, at its **highest priority** match
- Results are sorted ascending by `(priority, fqn)`
- Every result includes full dataset metadata **and** direct lineage (upstream + downstream)

---

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness probe — returns `{"status": "ok"}` if the process is alive |
| `GET` | `/` | Root — same health response |

---

## Request and Response Examples

### Create a Dataset

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/datasets \
  -H "Content-Type: application/json" \
  -d '{
    "connection_name": "snowflake_prod",
    "database_name":   "bi_team",
    "schema_name":     "bronze",
    "table_name":      "orders_raw",
    "source_system":   "Snowflake",
    "description":     "Raw orders ingested from transactional DB",
    "columns": [
      {"name": "order_id",   "data_type": "INT"},
      {"name": "order_date", "data_type": "TIMESTAMP"}
    ]
  }'
```

**Response 201:**
```json
{
  "fqn":             "snowflake_prod.bi_team.bronze.orders_raw",
  "connection_name": "snowflake_prod",
  "database_name":   "bi_team",
  "schema_name":     "bronze",
  "table_name":      "orders_raw",
  "source_system":   "Snowflake",
  "description":     "Raw orders ingested from transactional DB",
  "columns": [
    {"id": 1, "name": "order_id",   "data_type": "INT",       "description": null},
    {"id": 2, "name": "order_date", "data_type": "TIMESTAMP", "description": null}
  ],
  "created_at": "2026-02-19T10:00:00",
  "updated_at": "2026-02-19T10:00:00"
}
```

---

### Add a Lineage Edge

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/lineage \
  -H "Content-Type: application/json" \
  -d '{
    "upstream_fqn":   "snowflake_prod.bi_team.bronze.orders_raw",
    "downstream_fqn": "snowflake_prod.bi_team.silver.orders_clean"
  }'
```

**Response 201:**
```json
{
  "upstream":   {"fqn": "snowflake_prod.bi_team.bronze.orders_raw",   "source_system": "Snowflake", "description": null},
  "downstream": {"fqn": "snowflake_prod.bi_team.silver.orders_clean", "source_system": "Snowflake", "description": null},
  "created_at": "2026-02-19T10:01:00"
}
```

**Cycle rejection — Response 422:**
```json
{
  "detail": "Cannot add lineage 'snowflake_prod.bi_team.gold.orders_aggregated' -> 'snowflake_prod.bi_team.bronze.orders_raw': this would create a cycle. 'snowflake_prod.bi_team.gold.orders_aggregated' is already downstream of 'snowflake_prod.bi_team.bronze.orders_raw' (directly or transitively)."
}
```

---

### Get Lineage for a Dataset

**Request:**
```bash
curl http://localhost:8000/api/v1/lineage/snowflake_prod.bi_team.silver.orders_clean
```

**Response 200:**
```json
{
  "dataset": {
    "fqn": "snowflake_prod.bi_team.silver.orders_clean",
    "source_system": "Snowflake",
    "columns": [],
    "..."
  },
  "upstream_datasets": [
    {"fqn": "snowflake_prod.bi_team.bronze.orders_raw",     "source_system": "Snowflake", "description": null}
  ],
  "downstream_datasets": [
    {"fqn": "snowflake_prod.bi_team.gold.orders_aggregated", "source_system": "Snowflake", "description": null}
  ]
}
```

---

### Search

**Request:**
```bash
curl "http://localhost:8000/api/v1/search?q=order"
```

**Response 200:**
```json
{
  "query": "order",
  "total": 2,
  "results": [
    {
      "dataset": {"fqn": "snowflake_prod.bi_team.bronze.orders_raw", "..."},
      "match_type":  "table_name",
      "matched_on":  "orders_raw",
      "priority":    1,
      "upstream_datasets":   [],
      "downstream_datasets": [{"fqn": "snowflake_prod.bi_team.silver.orders_clean", "..."}]
    },
    {
      "dataset": {"fqn": "mysql.other.other.shipments", "..."},
      "match_type":  "column_name",
      "matched_on":  "order_id",
      "priority":    2,
      "upstream_datasets":   [],
      "downstream_datasets": []
    }
  ]
}
```

---

### Full End-to-End Workflow

```bash
BASE=http://localhost:8000/api/v1

# 1. Create three datasets
curl -s -X POST $BASE/datasets -H "Content-Type: application/json" -d '{"connection_name":"snowflake_prod","database_name":"bi_team","schema_name":"bronze","table_name":"orders_raw","source_system":"Snowflake","columns":[{"name":"order_id","data_type":"INT"},{"name":"order_date","data_type":"TIMESTAMP"}]}'

curl -s -X POST $BASE/datasets -H "Content-Type: application/json" -d '{"connection_name":"snowflake_prod","database_name":"bi_team","schema_name":"silver","table_name":"orders_clean","source_system":"Snowflake"}'

curl -s -X POST $BASE/datasets -H "Content-Type: application/json" -d '{"connection_name":"snowflake_prod","database_name":"bi_team","schema_name":"gold","table_name":"orders_aggregated","source_system":"Snowflake"}'

# 2. Create lineage: raw -> clean -> aggregated
curl -s -X POST $BASE/lineage -H "Content-Type: application/json" -d '{"upstream_fqn":"snowflake_prod.bi_team.bronze.orders_raw","downstream_fqn":"snowflake_prod.bi_team.silver.orders_clean"}'

curl -s -X POST $BASE/lineage -H "Content-Type: application/json" -d '{"upstream_fqn":"snowflake_prod.bi_team.silver.orders_clean","downstream_fqn":"snowflake_prod.bi_team.gold.orders_aggregated"}'

# 3. Attempt a cycle — will be rejected with 422
curl -s -X POST $BASE/lineage -H "Content-Type: application/json" -d '{"upstream_fqn":"snowflake_prod.bi_team.gold.orders_aggregated","downstream_fqn":"snowflake_prod.bi_team.bronze.orders_raw"}'

# 4. Get lineage for orders_clean
curl -s "$BASE/lineage/snowflake_prod.bi_team.silver.orders_clean"

# 5. Search for "order" — returns results with embedded lineage
curl -s "$BASE/search?q=order"
```

---

## Lineage and Cycle Detection

Lineage is modelled as a **Directed Acyclic Graph (DAG)**.  
An edge `A -> B` means: dataset A **produces** dataset B.

### Supported graph shape

```
orders_raw  (bronze)
    |
    v
orders_clean  (silver)
    |
    v
orders_aggregated  (gold)
```

### Cycle Detection Algorithm

Before any edge is written to the database the service:

1. Loads **all existing edges** into an adjacency map `{ upstream_id: {downstream_id, ...} }` — O(E)
2. Runs an **iterative DFS from the proposed `downstream` node**, following existing downstream edges
3. If the DFS ever reaches the **proposed `upstream` node**, a path `downstream -> ... -> upstream` already exists in the graph — adding `upstream -> downstream` would close a loop

**Rejected with HTTP 422 and a descriptive message.**

```
Existing graph:  A -> B -> C
Proposed edge:   C -> A   (upstream=C, downstream=A)

DFS from A (downstream), following existing edges:
  A -> B -> C   <- found C (upstream!) CYCLE DETECTED -> REJECTED
```

**Self-loops** (`A -> A`) are rejected at the Pydantic schema layer before the database is even touched, via a `@model_validator`.

**Complexity:** O(V + E) per write — acceptable for metadata graphs (thousands of datasets, not millions).

---

## Search Behaviour

Four separate SQL `ILIKE '%term%'` queries run in priority order.  
De-duplication is done in Python with a `seen_fqns` set.

A dataset matching at priority 1 (table name) will **not** appear again at priority 2 (column name) even if it also has matching columns.

**Each result contains:**

| Field | Description |
|---|---|
| `dataset` | Full dataset metadata including all columns and timestamps |
| `match_type` | Which tier matched: `table_name`, `column_name`, `schema_name`, `database_name` |
| `matched_on` | The exact value that matched (e.g. column name `order_id`) |
| `priority` | Numeric priority — 1 is best |
| `upstream_datasets` | Direct parents in the lineage graph |
| `downstream_datasets` | Direct children in the lineage graph |

Results are sorted ascending by `(priority, fqn)`.

---

## Architecture Decisions

### Layered Architecture

```
routers/       <-- HTTP layer: FastAPI routes, request validation, status code mapping
services/      <-- Business logic: CRUD, cycle detection, search priority, de-duplication
models/orm.py  <-- SQLAlchemy ORM models (Dataset, DatasetColumn, Lineage)
schemas/       <-- Pydantic v2 request/response schemas with field constraints
utils/graph.py <-- Pure-Python graph utilities, no DB dependency, fully unit-testable
exceptions.py  <-- Typed domain exceptions (NotFoundError, ConflictError, CycleError)
config.py      <-- pydantic-settings: all config loaded from environment / .env file
database.py    <-- Engine, session factory, get_db() dependency, init_db()
```

### FQN as Business Key

The FQN (`connection.database.schema.table`) is the **public API identifier** used in all URL paths.
Internally, a **surrogate integer PK** is used for all joins — faster MySQL index lookups on `INT` vs `VARCHAR(512)`.

FQN components are stored in **separate indexed columns** (`connection_name`, `database_name`, `schema_name`, `table_name`). This makes the four search queries fast without parsing the FQN string at query time.

### Lineage as a DAG

Simple DFS cycle detection runs before every lineage write.
O(E) to load all edges + O(V + E) for DFS = acceptable for metadata-scale graphs.
This avoids the complexity of incremental ancestor tracking while being fully correct.

### Search — Four Queries, Python De-duplication

Four targeted SQL `ILIKE` queries (one per priority tier) keep the SQL simple and readable.
Priority logic and de-duplication live in Python, making them explicit and independently testable (`test_graph.py` has zero HTTP involvement).

Each search result embeds direct lineage via SQLAlchemy relationships already loaded on the ORM object — no extra queries per result.

### Typed Domain Exceptions

Three exception types (`NotFoundError`, `ConflictError`, `CycleError`) are raised in the service layer and caught in the router layer, which maps them to HTTP status codes. This cleanly separates business logic from HTTP concerns without string-matching on error messages.

### Graceful Startup

`init_db()` is called in the FastAPI `lifespan` context manager. If the database is briefly unreachable at startup, the API logs a warning but stays alive. Useful in Docker even with healthchecks, where a small retry window is practical.

### Pre-commit Hooks

`ruff` is used as both linter and formatter — a single tool replacing `black + flake8 + isort`. Configured in `pyproject.toml` (`[tool.ruff]`), hooked via `.pre-commit-config.yaml`.

---

## Project Structure

```
metadata-service/
|-- app/
|   |-- main.py                    # FastAPI app, lifespan, CORS, router registration
|   |-- config.py                  # pydantic-settings: all config from env / .env
|   |-- database.py                # Engine, session factory, get_db(), init_db()
|   |-- exceptions.py              # NotFoundError, ConflictError, CycleError
|   |-- models/
|   |   `-- orm.py                 # Dataset, DatasetColumn, Lineage ORM models
|   |-- schemas/
|   |   `-- dataset.py             # All Pydantic v2 request/response schemas
|   |-- routers/
|   |   |-- datasets.py            # CRUD endpoints
|   |   |-- lineage.py             # Lineage endpoints
|   |   `-- search.py              # Search endpoint
|   |-- services/
|   |   |-- dataset_service.py     # Dataset CRUD business logic
|   |   |-- lineage_service.py     # Lineage creation, deletion, cycle detection
|   |   `-- search_service.py      # Priority search + de-duplication
|   `-- utils/
|       `-- graph.py               # would_create_cycle() and build_adjacency()
|-- alembic/
|   |-- env.py
|   |-- script.py.mako
|   `-- versions/
|       `-- 001_initial_schema.py  # Initial migration: datasets, columns, lineage
|-- tests/
|   |-- conftest.py                # In-memory SQLite, autouse reset fixture, DI override
|   |-- test_datasets.py
|   |-- test_lineage.py            # Includes cycle detection tests
|   |-- test_search.py             # Priority, deduplication, lineage-in-results
|   `-- test_graph.py              # Pure unit tests for DFS graph utilities
|-- .env.example
|-- .gitignore
|-- .pre-commit-config.yaml
|-- alembic.ini
|-- docker-compose.yml
|-- Dockerfile
|-- pyproject.toml
`-- README.md
```

---

## Database Schema

### `datasets`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INT | PK, autoincrement | Surrogate primary key |
| `fqn` | VARCHAR(512) | UNIQUE, NOT NULL, indexed | Fully qualified name |
| `connection_name` | VARCHAR(128) | NOT NULL, indexed | FQN component |
| `database_name` | VARCHAR(128) | NOT NULL, indexed | FQN component |
| `schema_name` | VARCHAR(128) | NOT NULL, indexed | FQN component |
| `table_name` | VARCHAR(128) | NOT NULL, indexed | FQN component |
| `source_system` | ENUM | NOT NULL | MySQL / MSSQL / PostgreSQL / Snowflake / BigQuery / Other |
| `description` | TEXT | nullable | Optional free-text description |
| `created_at` | DATETIME | NOT NULL, server_default=NOW() | Creation timestamp |
| `updated_at` | DATETIME | NOT NULL, server_default=NOW(), onupdate | Last modification timestamp |

### `dataset_columns`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INT | PK, autoincrement | Surrogate primary key |
| `dataset_id` | INT | FK -> datasets.id ON DELETE CASCADE | Parent dataset |
| `name` | VARCHAR(128) | NOT NULL, indexed | Column name (unique within dataset) |
| `data_type` | VARCHAR(64) | NOT NULL | e.g. INT, VARCHAR, TIMESTAMP |
| `description` | TEXT | nullable | Optional column description |

Unique constraint: `(dataset_id, name)`

### `lineage`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INT | PK, autoincrement | Surrogate primary key |
| `upstream_id` | INT | FK -> datasets.id ON DELETE CASCADE, indexed | Source dataset |
| `downstream_id` | INT | FK -> datasets.id ON DELETE CASCADE, indexed | Target dataset |
| `created_at` | DATETIME | NOT NULL, server_default=NOW() | When the edge was recorded |

Unique constraint: `(upstream_id, downstream_id)` — no duplicate edges

---

## Code Quality

### Pre-commit Hooks

```bash
# Install hooks (one-time, after poetry install)
poetry run pre-commit install

# Run manually against all files
poetry run pre-commit run --all-files
```

Hooks in `.pre-commit-config.yaml`:
- `ruff` — linting (E, F, I, UP, B, SIM rule sets)
- `ruff-format` — code formatting (replaces black)

### Ruff Configuration

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["app"]
```
