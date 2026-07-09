#!/usr/bin/env python3
"""Shared topological layering for the family DAG (single source of truth).

Both renderers use this so their notion of "generation" can never diverge.

Why not the node's `_depth`? `_depth` is a first-pass BFS hop from the MCP; in a
DAG with cross-generation priority edges (e.g. a provisional claimed by both the
root AND a child of the root) the shortest-hop number is misleading. Longest-path
layering guarantees every directed edge points strictly downward, so a parent is
always placed above its child — the correct genealogy reading.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


def assign_layers(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], root: str):
    """Return ({appNo: generation}, cyclic). root normalized to generation 0;
    ancestors negative, descendants positive. Falls back to `_depth` if the graph
    unexpectedly contains a cycle (continuity should be acyclic)."""
    ids = [n["applicationNumberText"] for n in nodes]
    idset = set(ids)
    E = [(e["from"], e["to"]) for e in edges if e["from"] in idset and e["to"] in idset]
    succ: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = {i: 0 for i in ids}
    for u, v in E:
        succ[u].append(v)
        indeg[v] += 1

    # Kahn topological order (sorted for determinism)
    q = deque(sorted(i for i in ids if indeg[i] == 0))
    ind = dict(indeg)
    order: list[str] = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in succ[u]:
            ind[v] -= 1
            if ind[v] == 0:
                q.append(v)

    if len(order) != len(ids):  # cycle → fall back to the BFS hop depth
        base = {n["applicationNumberText"]: int(n.get("_depth", 0) or 0) for n in nodes}
        off = base.get(root, 0)
        return {k: v - off for k, v in base.items()}, True

    layer = {i: 0 for i in ids}
    for u in order:
        for v in succ[u]:
            if layer[u] + 1 > layer[v]:
                layer[v] = layer[u] + 1
    off = layer.get(root, 0)
    return {k: v - off for k, v in layer.items()}, False


def generation_span(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], root: str):
    """Return (min_gen, max_gen, distinct_count) via proper layering — for summaries."""
    if not nodes:
        return (0, 0, 0)
    layer, _ = assign_layers(nodes, edges, root)
    vals = list(layer.values())
    return (min(vals), max(vals), len(set(vals)))
