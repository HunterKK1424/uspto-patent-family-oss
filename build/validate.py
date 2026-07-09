#!/usr/bin/env python3
"""Lightweight runtime validation of a family_raw.json payload.

The contract (docs/family_raw.schema.json) is the architecture's linchpin but had
no runtime check — TS interface, JSON schema and Python each described it
separately. This gives the renderers a cheap structural gate (stdlib only, no
jsonschema dependency) so a malformed payload fails loudly instead of producing a
silently-wrong chart.

Returns a list of human-readable error strings ([] == valid).
"""
from __future__ import annotations

from typing import Any

VALID_STATUS = {"granted", "pending", "abandoned", "provisional", "unknown"}
VALID_TRUNC = {"node-cap", "depth-cap", "rate-limit", "time-budget"}
VALID_LINEAGE = {"root", "ancestor", "descendant", "collateral"}


def validate_family_raw(data: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["top-level value is not an object"]

    if not isinstance(data.get("root"), str) or not data.get("root"):
        errs.append("`root` missing or not a non-empty string")
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list):
        errs.append("`nodes` missing or not an array")
        nodes = []
    if not isinstance(edges, list):
        errs.append("`edges` missing or not an array")
        edges = []

    tr = data.get("truncationReason")
    if tr is not None and tr not in VALID_TRUNC:
        errs.append(f"truncationReason '{tr}' not one of {sorted(VALID_TRUNC)}")

    apps: set[str] = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            errs.append(f"node[{i}] is not an object")
            continue
        app = n.get("applicationNumberText")
        if not isinstance(app, str) or not app:
            errs.append(f"node[{i}] missing applicationNumberText")
            continue
        if app in apps:
            errs.append(f"duplicate node applicationNumberText '{app}'")
        apps.add(app)
        if n.get("status") not in VALID_STATUS:
            errs.append(f"node '{app}' status '{n.get('status')}' not in {sorted(VALID_STATUS)}")
        if not isinstance(n.get("_fetched"), bool):
            errs.append(f"node '{app}' _fetched must be boolean")
        if "_omitted" in n and not (isinstance(n["_omitted"], int) and n["_omitted"] >= 0):
            errs.append(f"node '{app}' _omitted must be a non-negative integer")
        if n.get("lineage") is not None and n.get("lineage") not in VALID_LINEAGE:
            errs.append(f"node '{app}' lineage '{n.get('lineage')}' not in {sorted(VALID_LINEAGE)}")

    root = data.get("root")
    if isinstance(root, str) and apps and root not in apps:
        errs.append(f"root '{root}' has no corresponding node")

    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            errs.append(f"edge[{i}] is not an object")
            continue
        for key in ("from", "to", "relationshipType"):
            if not isinstance(e.get(key), str) or not e.get(key):
                errs.append(f"edge[{i}] missing '{key}'")
        # dangling-edge check: both endpoints must be real nodes
        if isinstance(e.get("from"), str) and e["from"] not in apps:
            errs.append(f"edge[{i}] from '{e['from']}' references no node")
        if isinstance(e.get("to"), str) and e["to"] not in apps:
            errs.append(f"edge[{i}] to '{e['to']}' references no node")

    overlay = data.get("overlay")
    if overlay is not None:
        if not isinstance(overlay, dict):
            errs.append("`overlay` must be an object")
        else:
            for app in overlay:
                if apps and app not in apps:
                    errs.append(f"overlay key '{app}' references no node")
    return errs


if __name__ == "__main__":
    import json
    import sys

    data = json.load(open(sys.argv[1], encoding="utf-8"))
    problems = validate_family_raw(data)
    if problems:
        print(f"INVALID ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)
    print("valid ✓")
