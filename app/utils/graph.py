"""
Directed Acyclic Graph (DAG) utilities for lineage cycle detection.

Algorithm
---------
To validate that adding the edge  ``upstream → downstream``  does **not**
introduce a cycle, we run a DFS starting from ``downstream`` and follow
existing downstream edges.  If the DFS ever reaches ``upstream``, a cycle
would be formed — the edge is rejected.

Why this works
--------------
A cycle requires a path  downstream → ... → upstream.
If such a path exists in the *current* graph, then adding
upstream → downstream closes the loop.  So:

    has_cycle(upstream, downstream, graph) is True
    iff  upstream is reachable from downstream

Complexity
----------
O(V + E) per check — acceptable for metadata graphs which are typically
small (thousands of datasets, not millions).

Example::

    graph = {
        "A": {"B"},   # A feeds B
        "B": {"C"},   # B feeds C
    }

    # Adding C → A:  DFS from A?  No path A→C in descendants of C.
    # Wait — we check if A is reachable from C (the proposed downstream).
    # C has no outbound edges → A not reachable → cycle detected? No…
    # Let me re-state:  we add  upstream=C, downstream=A.
    # DFS from A (downstream) following existing downstream edges:
    #   A → B → C  ← found upstream=C  → CYCLE!

"""

from typing import Dict, Set


def would_create_cycle(
    upstream_id: int,
    downstream_id: int,
    adjacency: Dict[int, Set[int]],
) -> bool:
    """
    Return True if adding the directed edge upstream_id → downstream_id
    would create a cycle in the lineage graph.

    Parameters
    ----------
    upstream_id:
        The dataset that would become the source of the new edge.
    downstream_id:
        The dataset that would become the target of the new edge.
    adjacency:
        Mapping of  dataset_id → set of direct downstream dataset_ids,
        representing the **current** (pre-insertion) lineage graph.

    Returns
    -------
    bool
        True  → adding this edge creates a cycle (reject).
        False → adding this edge is safe.

    Examples
    --------
    >>> graph = {1: {2}, 2: {3}}       # 1→2→3
    >>> would_create_cycle(3, 1, graph)  # proposed: 3→1
    True
    >>> would_create_cycle(1, 4, graph)  # proposed: 1→4 (new leaf)
    False
    """
    # A self-loop is always a cycle
    if upstream_id == downstream_id:
        return True

    # DFS from downstream_id through existing outbound edges.
    # If we reach upstream_id, the new edge would close a loop.
    visited: Set[int] = set()
    stack = [downstream_id]

    while stack:
        node = stack.pop()
        if node == upstream_id:
            return True
        if node in visited:
            continue
        visited.add(node)
        for neighbour in adjacency.get(node, set()):
            if neighbour not in visited:
                stack.append(neighbour)

    return False


def build_adjacency(edges: list) -> Dict[int, Set[int]]:
    """
    Build an adjacency map from a list of (upstream_id, downstream_id) tuples.

    Parameters
    ----------
    edges:
        Iterable of objects with ``upstream_id`` and ``downstream_id`` attributes,
        or plain 2-tuples ``(upstream_id, downstream_id)``.

    Returns
    -------
    dict
        ``{node_id: {downstream_id, ...}}``

    Examples
    --------
    >>> build_adjacency([(1, 2), (2, 3)])
    {1: {2}, 2: {3}}
    """
    adj: Dict[int, Set[int]] = {}
    for edge in edges:
        if isinstance(edge, tuple):
            u, d = edge
        else:
            u, d = edge.upstream_id, edge.downstream_id
        adj.setdefault(u, set()).add(d)
    return adj
