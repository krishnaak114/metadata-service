"""
Tests for lineage endpoints — including cycle detection.

Key test scenarios:
  - Happy path:  A → B → C  (valid DAG)
  - Cycle:       C → A  (must be rejected — A is upstream of C)
  - Near cycle:  B → A  (must be rejected — A is upstream of B)
  - Self-loop:   A → A  (rejected at schema level)
  - Delete edge then verify
"""

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_dataset(client: TestClient, connection: str, db: str, schema: str, table: str) -> dict:
    resp = client.post(
        "/api/v1/datasets",
        json={
            "connection_name": connection,
            "database_name": db,
            "schema_name": schema,
            "table_name": table,
            "source_system": "Snowflake",
        },
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


def _add_lineage(client: TestClient, upstream: str, downstream: str):
    return client.post(
        "/api/v1/lineage",
        json={"upstream_fqn": upstream, "downstream_fqn": downstream},
    )


@pytest.fixture
def three_layer(client: TestClient):
    """
    Create three datasets and link them:  raw → clean → aggregated
    Returns (raw_fqn, clean_fqn, agg_fqn)
    """
    raw = _make_dataset(client, "sf", "bi", "bronze", "orders_raw")["fqn"]
    clean = _make_dataset(client, "sf", "bi", "silver", "orders_clean")["fqn"]
    agg = _make_dataset(client, "sf", "bi", "gold", "orders_aggregated")["fqn"]

    assert _add_lineage(client, raw, clean).status_code == 201
    assert _add_lineage(client, clean, agg).status_code == 201

    return raw, clean, agg


# ── Add lineage ───────────────────────────────────────────────────────────────

class TestAddLineage:
    def test_valid_chain(self, client, three_layer):
        raw, clean, agg = three_layer
        # No assertion needed — fixture already verified creation

    def test_missing_upstream_returns_404(self, client):
        _make_dataset(client, "sf", "bi", "s", "downonly")
        resp = _add_lineage(client, "non.existent.up.stream", "sf.bi.s.downonly")
        assert resp.status_code == 404

    def test_missing_downstream_returns_404(self, client):
        _make_dataset(client, "sf", "bi", "s", "uponly")
        resp = _add_lineage(client, "sf.bi.s.uponly", "non.existent.down.stream")
        assert resp.status_code == 404

    def test_duplicate_edge_rejected(self, client, three_layer):
        raw, clean, _ = three_layer
        resp = _add_lineage(client, raw, clean)
        assert resp.status_code == 409  # ConflictError → 409 Conflict

    def test_self_loop_rejected_by_schema(self, client):
        _make_dataset(client, "sf", "bi", "s", "self_ref")
        resp = _add_lineage(client, "sf.bi.s.self_ref", "sf.bi.s.self_ref")
        assert resp.status_code == 422  # Pydantic model_validator catches it


# ── Cycle detection ───────────────────────────────────────────────────────────

class TestCycleDetection:
    def test_direct_cycle_rejected(self, client, three_layer):
        """
        Graph: raw → clean → agg
        Attempt: agg → raw  ← must be rejected (closes the cycle)
        """
        raw, clean, agg = three_layer
        resp = _add_lineage(client, agg, raw)
        assert resp.status_code == 422
        assert "cycle" in resp.json()["detail"].lower()

    def test_indirect_cycle_rejected(self, client, three_layer):
        """
        Graph: raw → clean → agg
        Attempt: agg → clean  ← rejected (clean is already upstream of agg)
        """
        raw, clean, agg = three_layer
        resp = _add_lineage(client, agg, clean)
        assert resp.status_code == 422
        assert "cycle" in resp.json()["detail"].lower()

    def test_b_to_a_cycle_rejected(self, client, three_layer):
        """
        Graph: raw → clean → agg
        Attempt: clean → raw  ← rejected
        """
        raw, clean, agg = three_layer
        resp = _add_lineage(client, clean, raw)
        assert resp.status_code == 422

    def test_longer_chain_cycle_rejected(self, client):
        """
        Graph: A → B → C → D
        Attempt: D → A  ← must be rejected
        """
        a = _make_dataset(client, "s", "d", "sc", "a")["fqn"]
        b = _make_dataset(client, "s", "d", "sc", "b")["fqn"]
        c = _make_dataset(client, "s", "d", "sc", "c")["fqn"]
        d = _make_dataset(client, "s", "d", "sc", "d")["fqn"]

        _add_lineage(client, a, b)
        _add_lineage(client, b, c)
        _add_lineage(client, c, d)

        resp = _add_lineage(client, d, a)
        assert resp.status_code == 422
        assert "cycle" in resp.json()["detail"].lower()

    def test_diamond_dag_is_valid(self, client):
        """
        Diamond (valid DAG, not a cycle):
            A → B
            A → C
            B → D
            C → D
        All four edges must be accepted.
        """
        a = _make_dataset(client, "s", "d", "sc", "da")["fqn"]
        b = _make_dataset(client, "s", "d", "sc", "db")["fqn"]
        c = _make_dataset(client, "s", "d", "sc", "dc")["fqn"]
        d = _make_dataset(client, "s", "d", "sc", "dd")["fqn"]

        assert _add_lineage(client, a, b).status_code == 201
        assert _add_lineage(client, a, c).status_code == 201
        assert _add_lineage(client, b, d).status_code == 201
        assert _add_lineage(client, c, d).status_code == 201


# ── Query lineage ─────────────────────────────────────────────────────────────

class TestGetLineage:
    def test_upstream_and_downstream(self, client, three_layer):
        raw, clean, agg = three_layer
        resp = client.get(f"/api/v1/lineage/{clean}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["dataset"]["fqn"] == clean
        upstream_fqns = [u["fqn"] for u in body["upstream_datasets"]]
        downstream_fqns = [d["fqn"] for d in body["downstream_datasets"]]
        assert raw in upstream_fqns
        assert agg in downstream_fqns

    def test_root_node_has_no_upstream(self, client, three_layer):
        raw, clean, agg = three_layer
        resp = client.get(f"/api/v1/lineage/{raw}")
        body = resp.json()
        assert body["upstream_datasets"] == []
        assert len(body["downstream_datasets"]) == 1

    def test_leaf_node_has_no_downstream(self, client, three_layer):
        raw, clean, agg = three_layer
        resp = client.get(f"/api/v1/lineage/{agg}")
        body = resp.json()
        assert body["downstream_datasets"] == []
        assert len(body["upstream_datasets"]) == 1

    def test_lineage_nonexistent_dataset_returns_404(self, client):
        assert client.get("/api/v1/lineage/no.such.thing.here").status_code == 404


# ── Delete lineage ────────────────────────────────────────────────────────────

class TestDeleteLineage:
    def test_delete_edge(self, client, three_layer):
        raw, clean, agg = three_layer
        resp = client.delete(
            "/api/v1/lineage",
            params={"upstream_fqn": raw, "downstream_fqn": clean},
        )
        assert resp.status_code == 204

        # Verify edge is gone
        body = client.get(f"/api/v1/lineage/{clean}").json()
        assert body["upstream_datasets"] == []

    def test_delete_nonexistent_edge_returns_404(self, client, three_layer):
        raw, clean, agg = three_layer
        resp = client.delete(
            "/api/v1/lineage",
            params={"upstream_fqn": raw, "downstream_fqn": agg},
        )
        assert resp.status_code == 404
