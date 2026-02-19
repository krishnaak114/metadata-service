"""Tests for the search endpoint — priority ordering and de-duplication."""

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _ds(client, connection, database, schema, table, columns=None):
    payload = {
        "connection_name": connection,
        "database_name": database,
        "schema_name": schema,
        "table_name": table,
        "source_system": "MySQL",
        "columns": columns or [],
    }
    resp = client.post("/api/v1/datasets", json=payload)
    assert resp.status_code == 201, resp.json()
    return resp.json()["fqn"]


@pytest.fixture
def populated(client: TestClient):
    """
    Seed a small dataset population for search tests.

    FQNs to be created:
        - snowflake.sales.public.orders          (table=orders)
        - snowflake.sales.public.customers        (table=customers)
        - mysql.reporting.orders_schema.revenue   (schema contains 'orders')
        - mysql.orders_db.public.shipments        (database contains 'orders')
        - mysql.other.other.shipments2            (column order_id matches)
    """
    _ds(client, "snowflake", "sales", "public", "orders",
        columns=[{"name": "order_id", "data_type": "INT"}, {"name": "amount", "data_type": "FLOAT"}])
    _ds(client, "snowflake", "sales", "public", "customers")
    _ds(client, "mysql", "reporting", "orders_schema", "revenue")
    _ds(client, "mysql", "orders_db", "public", "shipments")
    _ds(client, "mysql", "other", "other", "shipments2",
        columns=[{"name": "order_id", "data_type": "INT"}])
    return client


# ── Search tests ──────────────────────────────────────────────────────────────

class TestSearch:
    def test_empty_query_returns_400(self, client):
        # q is required (min_length=1)
        resp = client.get("/api/v1/search")
        assert resp.status_code == 422

    def test_no_results(self, populated):
        resp = populated.get("/api/v1/search", params={"q": "zzznomatchzzz"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["results"] == []

    def test_table_name_match(self, populated):
        resp = populated.get("/api/v1/search", params={"q": "orders"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        # "orders" table should be priority 1
        first = results[0]
        assert first["match_type"] == "table_name"
        assert first["priority"] == 1

    def test_priority_ordering(self, populated):
        """
        Searching 'orders' should return results in ascending priority order:
        1 (table_name) before 2 (column_name) before 3 (schema_name) before 4 (database_name)
        """
        resp = populated.get("/api/v1/search", params={"q": "orders"})
        results = resp.json()["results"]
        priorities = [r["priority"] for r in results]
        assert priorities == sorted(priorities), "Results must be sorted by priority asc"

    def test_deduplication(self, populated):
        """
        A dataset that matches both table_name and column_name should appear only once
        at the higher priority.
        snowflake.sales.public.orders matches table_name AND has column order_id.
        It should appear once at priority 1 (table_name).
        """
        resp = populated.get("/api/v1/search", params={"q": "orders"})
        results = resp.json()["results"]
        fqns = [r["dataset"]["fqn"] for r in results]
        assert len(fqns) == len(set(fqns)), "Duplicate FQNs in search results"

        # The table "orders" should appear at priority 1, not 2
        orders_result = next(r for r in results if r["dataset"]["fqn"] == "snowflake.sales.public.orders")
        assert orders_result["priority"] == 1
        assert orders_result["match_type"] == "table_name"

    def test_column_name_match(self, populated):
        """mysql.other.other.shipments2 only matches via column order_id"""
        resp = populated.get("/api/v1/search", params={"q": "order_id"})
        results = resp.json()["results"]
        fqns = [r["dataset"]["fqn"] for r in results]
        assert "mysql.other.other.shipments2" in fqns
        col_match = next(r for r in results if r["dataset"]["fqn"] == "mysql.other.other.shipments2")
        assert col_match["match_type"] == "column_name"
        assert col_match["priority"] == 2

    def test_schema_name_match(self, populated):
        resp = populated.get("/api/v1/search", params={"q": "orders_schema"})
        results = resp.json()["results"]
        assert any(r["match_type"] == "schema_name" for r in results)
        schema_match = next(r for r in results if r["match_type"] == "schema_name")
        assert schema_match["priority"] == 3

    def test_database_name_match(self, populated):
        resp = populated.get("/api/v1/search", params={"q": "orders_db"})
        results = resp.json()["results"]
        assert any(r["match_type"] == "database_name" for r in results)
        db_match = next(r for r in results if r["match_type"] == "database_name")
        assert db_match["priority"] == 4

    def test_response_structure(self, populated):
        resp = populated.get("/api/v1/search", params={"q": "orders"})
        body = resp.json()
        assert "query" in body
        assert "total" in body
        assert "results" in body
        for item in body["results"]:
            assert "dataset" in item
            assert "match_type" in item
            assert "matched_on" in item
            assert "priority" in item
            assert "upstream_datasets" in item
            assert "downstream_datasets" in item

    def test_lineage_embedded_in_search_results(self, client: TestClient):
        """
        Search results must embed direct upstream/downstream lineage.

        Setup:  raw → clean → aggregated
        Search for 'clean' → the result for orders_clean should have:
          - upstream_datasets:  [orders_raw]
          - downstream_datasets: [orders_aggregated]
        """
        raw = _ds(client, "sf", "bi", "bronze", "orders_raw")
        clean = _ds(client, "sf", "bi", "silver", "orders_clean")
        agg = _ds(client, "sf", "bi", "gold", "orders_aggregated")

        # wire up lineage
        client.post("/api/v1/lineage", json={"upstream_fqn": raw, "downstream_fqn": clean})
        client.post("/api/v1/lineage", json={"upstream_fqn": clean, "downstream_fqn": agg})

        resp = client.get("/api/v1/search", params={"q": "orders_clean"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1

        item = results[0]
        assert item["dataset"]["fqn"] == clean

        upstream_fqns = [u["fqn"] for u in item["upstream_datasets"]]
        downstream_fqns = [d["fqn"] for d in item["downstream_datasets"]]

        assert raw in upstream_fqns
        assert agg in downstream_fqns

    def test_limit_respected(self, populated):
        resp = populated.get("/api/v1/search", params={"q": "orders", "limit": 2})
        assert resp.status_code == 200
        assert len(resp.json()["results"]) <= 2
