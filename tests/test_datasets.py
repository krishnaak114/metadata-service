"""Tests for dataset CRUD endpoints."""

import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_dataset(client: TestClient, **overrides) -> dict:
    payload = {
        "connection_name": "snowflake_prod",
        "database_name": "bi_team",
        "schema_name": "bronze",
        "table_name": "orders_raw",
        "source_system": "Snowflake",
        "description": "Raw orders",
        "columns": [
            {"name": "order_id", "data_type": "INT"},
            {"name": "customer_id", "data_type": "INT"},
        ],
        **overrides,
    }
    resp = client.post("/api/v1/datasets", json=payload)
    assert resp.status_code == 201, resp.json()
    return resp.json()


# ── Create ────────────────────────────────────────────────────────────────────

class TestCreateDataset:
    def test_create_success(self, client):
        data = _create_dataset(client)
        assert data["fqn"] == "snowflake_prod.bi_team.bronze.orders_raw"
        assert data["source_system"] == "Snowflake"
        assert len(data["columns"]) == 2

    def test_fqn_is_derived_from_components(self, client):
        data = _create_dataset(
            client,
            connection_name="MySQL_Prod",
            database_name="Sales",
            schema_name="Public",
            table_name="Orders",
        )
        # Components are normalised to lowercase
        assert data["fqn"] == "mysql_prod.sales.public.orders"

    def test_duplicate_fqn_rejected(self, client):
        _create_dataset(client)
        resp = client.post(
            "/api/v1/datasets",
            json={
                "connection_name": "snowflake_prod",
                "database_name": "bi_team",
                "schema_name": "bronze",
                "table_name": "orders_raw",
                "source_system": "Snowflake",
            },
        )
        assert resp.status_code == 409

    def test_create_without_columns(self, client):
        data = _create_dataset(client, columns=[])
        assert data["columns"] == []

    def test_invalid_source_system_rejected(self, client):
        resp = client.post(
            "/api/v1/datasets",
            json={
                "connection_name": "c",
                "database_name": "d",
                "schema_name": "s",
                "table_name": "t",
                "source_system": "ORACLE",  # not in enum
            },
        )
        assert resp.status_code == 422


# ── Read ──────────────────────────────────────────────────────────────────────

class TestGetDataset:
    def test_get_existing(self, client):
        _create_dataset(client)
        resp = client.get("/api/v1/datasets/snowflake_prod.bi_team.bronze.orders_raw")
        assert resp.status_code == 200
        assert resp.json()["fqn"] == "snowflake_prod.bi_team.bronze.orders_raw"

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get("/api/v1/datasets/does.not.exist.here")
        assert resp.status_code == 404

    def test_list_returns_all(self, client):
        _create_dataset(client, table_name="t1")
        _create_dataset(client, table_name="t2")
        resp = client.get("/api/v1/datasets")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ── Update ────────────────────────────────────────────────────────────────────

class TestUpdateDataset:
    def test_update_description(self, client):
        _create_dataset(client)
        resp = client.put(
            "/api/v1/datasets/snowflake_prod.bi_team.bronze.orders_raw",
            json={"description": "Updated description"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_update_columns_replaces_list(self, client):
        _create_dataset(client)
        resp = client.put(
            "/api/v1/datasets/snowflake_prod.bi_team.bronze.orders_raw",
            json={"columns": [{"name": "new_col", "data_type": "VARCHAR"}]},
        )
        assert resp.status_code == 200
        assert len(resp.json()["columns"]) == 1
        assert resp.json()["columns"][0]["name"] == "new_col"

    def test_update_nonexistent_returns_404(self, client):
        resp = client.put(
            "/api/v1/datasets/no.such.dataset.here",
            json={"description": "x"},
        )
        assert resp.status_code == 404


# ── Delete ────────────────────────────────────────────────────────────────────

class TestDeleteDataset:
    def test_delete_success(self, client):
        _create_dataset(client)
        resp = client.delete("/api/v1/datasets/snowflake_prod.bi_team.bronze.orders_raw")
        assert resp.status_code == 204
        # Confirm gone
        assert client.get("/api/v1/datasets/snowflake_prod.bi_team.bronze.orders_raw").status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/v1/datasets/no.such.dataset.here")
        assert resp.status_code == 404
