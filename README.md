# Metadata Service

A production-ready data governance metadata service built with **FastAPI**, **MySQL**, **SQLAlchemy**, and **Docker**.

Manages dataset metadata, column definitions, and dataset-to-dataset lineage — enforcing a valid Directed Acyclic Graph (DAG) at all times.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- (Optional, for local dev) Python 3.11+, Poetry

### Run with Docker Compose

```bash
# 1. Clone and enter the project
git clone https://github.com/krishnaak114/metadata-service
cd metadata-service

# 2. Copy the environment file
cp .env.example .env      # Edit DATABASE_URL if needed — defaults work with docker-compose

# 3. Start the stack (MySQL + API)
docker compose up --build

# 4. The API is now live at:
#    http://localhost:8000/api/v1/docs   ← Swagger UI
#    http://localhost:8000/api/v1/redoc  ← ReDoc
```

> On first boot the API waits for MySQL to be healthy (≈20–30 s), then auto-creates all tables.

### Run Locally (without Docker)

```bash
# Install Poetry if you don't have it
pip install poetry

# Install dependencies
poetry install

# Configure a local MySQL instance, then:
cp .env.example .env
# Edit DATABASE_URL in .env to point at your local MySQL

# Run Alembic migrations
poetry run alembic upgrade head

# Start the dev server
poetry run uvicorn app.main:app --reload --port 8000
```

---

## Running Tests

Tests use an **in-memory SQLite** database — no MySQL required.

```bash
poetry run pytest -v
```

---

## API Reference

All routes are prefixed with `/api/v1`.

### Datasets

| Method   | Path                   | Description |
|----------|------------------------|-------------|
| `POST`   | `/datasets`            | Create a dataset with columns |
| `GET`    | `/datasets`            | List all datasets (paginated) |
| `GET`    | `/datasets/{fqn}`      | Get a dataset by FQN |
| `PUT`    | `/datasets/{fqn}`      | Update description / columns |
| `DELETE` | `/datasets/{fqn}`      | Delete a dataset (cascades) |

**FQN format:** `connection_name.database_name.schema_name.table_name`  
Example: `snowflake_prod.bi_team.bronze.orders_raw`

### Lineage

| Method   | Path               | Description |
|----------|--------------------|-------------|
| `POST`   | `/lineage`         | Add a lineage edge (cycle-safe) |
| `GET`    | `/lineage/{fqn}`   | Get upstream & downstream for a dataset |
| `GET`    | `/lineage`         | List all lineage edges |
| `DELETE` | `/lineage`         | Remove an edge (`?upstream_fqn=&downstream_fqn=`) |

### Search

| Method | Path      | Description |
|--------|-----------|-------------|
| `GET`  | `/search` | Search by name components and columns (`?q=order`) |

**Search priority (ascending — 1 is best):**

| Priority | Match type      | Example |
|----------|----------------|---------|
| 1        | `table_name`    | table is `orders` |
| 2        | `column_name`   | dataset has column `order_id` |
| 3        | `schema_name`   | schema is `orders_schema` |
| 4        | `database_name` | database is `orders_db` |

Each dataset appears at most once, at its highest-priority match.

---

## Example Workflow

```bash
BASE=http://localhost:8000/api/v1

# 1. Create three datasets
curl -s -X POST $BASE/datasets -H "Content-Type: application/json" -d '{
  "connection_name": "snowflake_prod", "database_name": "bi_team",
  "schema_name": "bronze", "table_name": "orders_raw",
  "source_system": "Snowflake",
  "columns": [{"name": "order_id", "data_type": "INT"}, {"name": "order_date", "data_type": "TIMESTAMP"}]
}'

curl -s -X POST $BASE/datasets -H "Content-Type: application/json" -d '{
  "connection_name": "snowflake_prod", "database_name": "bi_team",
  "schema_name": "silver", "table_name": "orders_clean",
  "source_system": "Snowflake"
}'

curl -s -X POST $BASE/datasets -H "Content-Type: application/json" -d '{
  "connection_name": "snowflake_prod", "database_name": "bi_team",
  "schema_name": "gold", "table_name": "orders_aggregated",
  "source_system": "Snowflake"
}'

# 2. Add lineage: raw → clean → aggregated
curl -s -X POST $BASE/lineage -H "Content-Type: application/json" -d '{
  "upstream_fqn": "snowflake_prod.bi_team.bronze.orders_raw",
  "downstream_fqn": "snowflake_prod.bi_team.silver.orders_clean"
}'

curl -s -X POST $BASE/lineage -H "Content-Type: application/json" -d '{
  "upstream_fqn": "snowflake_prod.bi_team.silver.orders_clean",
  "downstream_fqn": "snowflake_prod.bi_team.gold.orders_aggregated"
}'

# 3. Attempt to create a cycle (will be rejected)
curl -s -X POST $BASE/lineage -H "Content-Type: application/json" -d '{
  "upstream_fqn": "snowflake_prod.bi_team.gold.orders_aggregated",
  "downstream_fqn": "snowflake_prod.bi_team.bronze.orders_raw"
}'
# → 422: "Cannot add lineage ... this would create a cycle."

# 4. Search
curl -s "$BASE/search?q=order"
```

---

## Architecture Decisions

### Layered Architecture
Follows the same pattern as the rest of this portfolio:
```
routers/       ← HTTP layer (FastAPI routes, request/response serialisation)
services/      ← Business logic (CRUD, cycle detection, search priority)
models/orm.py  ← SQLAlchemy ORM models
schemas/       ← Pydantic v2 request/response schemas
utils/graph.py ← Pure-Python graph utilities (no DB dependency)
config.py      ← pydantic-settings with .env support
database.py    ← Engine, session, init_db()
```

### FQN as Business Key
The FQN (`connection.database.schema.table`) is the public API identifier — used in all URL paths. Internally, a surrogate integer PK is used for joins (faster MySQL index lookups on int vs. varchar(512)).

### Lineage as a DAG — Cycle Detection
Before writing any edge to the database, the service:
1. Loads all existing edges and builds an adjacency map (O(E)).
2. Runs a DFS from the *proposed downstream* node.
3. If the DFS reaches the *proposed upstream*, a cycle would be formed — the edge is rejected with a `422` and a descriptive error message.

This is an intentionally simple, correct approach. For very large graphs (>100K datasets), this could be optimised with incremental ancestor tracking, but for a metadata service it is more than sufficient.

### Search Priority
Search runs four targeted SQL queries (one per priority tier) then de-duplicates in-application memory. This keeps the SQL simple and the priority logic explicit and testable.

Each search result embeds the full dataset metadata **and its direct lineage** (upstream/downstream datasets). The lineage is resolved via SQLAlchemy relationships already loaded on the `Dataset` ORM object — no extra queries are issued per result.

### Optional Services (DB is required, Redis is not)
Unlike the other services in this portfolio, the database is **required** here — all data lives in MySQL. There is no in-process fallback because the service *is* the database layer.

### Pre-commit Hooks
`ruff` is used as both linter and formatter (replaces `black + flake8 + isort`) as configured in `.pre-commit-config.yaml`.

---

## Project Structure

```
metadata-service/
├── app/
│   ├── main.py              # FastAPI app + lifespan
│   ├── config.py            # pydantic-settings based config
│   ├── database.py          # SQLAlchemy engine + session
│   ├── models/
│   │   └── orm.py           # Dataset, DatasetColumn, Lineage ORM models
│   ├── schemas/
│   │   └── dataset.py       # Pydantic v2 request/response schemas
│   ├── routers/
│   │   ├── datasets.py      # CRUD endpoints
│   │   ├── lineage.py       # Lineage endpoints
│   │   └── search.py        # Search endpoint
│   ├── services/
│   │   ├── dataset_service.py
│   │   ├── lineage_service.py
│   │   └── search_service.py
│   └── utils/
│       └── graph.py         # DFS cycle detection
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial_schema.py
├── tests/
│   ├── conftest.py          # SQLite in-memory test fixtures
│   ├── test_datasets.py
│   ├── test_lineage.py      # Includes cycle detection tests
│   ├── test_search.py       # Priority + deduplication tests
│   └── test_graph.py        # Pure unit tests for DFS logic
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```
