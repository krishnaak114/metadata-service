"""Tests for the DFS cycle detection utility (unit tests — no DB required)."""

from app.utils.graph import build_adjacency, would_create_cycle


class TestWouldCreateCycle:
    def test_empty_graph_no_cycle(self):
        assert not would_create_cycle(1, 2, {})

    def test_self_loop_always_cycle(self):
        assert would_create_cycle(1, 1, {})

    def test_direct_reverse_is_cycle(self):
        # Graph: 1→2  Proposed: 2→1
        adj = {1: {2}}
        assert would_create_cycle(2, 1, adj)

    def test_transitive_cycle(self):
        # Graph: 1→2→3  Proposed: 3→1
        adj = {1: {2}, 2: {3}}
        assert would_create_cycle(3, 1, adj)

    def test_valid_extension_not_cycle(self):
        # Graph: 1→2→3  Proposed: 3→4 (new leaf)
        adj = {1: {2}, 2: {3}}
        assert not would_create_cycle(3, 4, adj)

    def test_diamond_valid(self):
        # A→B, A→C, B→D, C→D  — all valid
        adj = {1: {2, 3}, 2: {4}, 3: {4}}
        assert not would_create_cycle(4, 5, adj)  # D→E is fine
        assert would_create_cycle(4, 1, adj)      # D→A closes cycle

    def test_longer_chain(self):
        # 1→2→3→4→5  Proposed: 5→1
        adj = {1: {2}, 2: {3}, 3: {4}, 4: {5}}
        assert would_create_cycle(5, 1, adj)
        assert would_create_cycle(5, 3, adj)
        assert not would_create_cycle(5, 6, adj)


class TestBuildAdjacency:
    def test_from_tuples(self):
        edges = [(1, 2), (2, 3), (1, 3)]
        adj = build_adjacency(edges)
        assert adj == {1: {2, 3}, 2: {3}}

    def test_empty_edges(self):
        assert build_adjacency([]) == {}

    def test_single_edge(self):
        adj = build_adjacency([(10, 20)])
        assert adj == {10: {20}}
