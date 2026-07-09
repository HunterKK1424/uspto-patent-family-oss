# Architecture

The server is a thin, layered pipeline. Data fetching (which spends API quota) is
isolated from graph analysis and rendering (which are deterministic and testable).

```
┌─ Layer 1 — Fetch (TypeScript, src/providers/uspto.ts) ───────────────────────┐
│  USPTO ODP REST → normalized nodes + edges.                                   │
│  GET /patent/applications/{appNo} returns biblio + continuity bags together,  │
│  so the walk costs ONE ODP call per application. Serialized under burst=1,     │
│  disk-cached (7-day TTL), no auto-retry on 429.                               │
└──────────────────────────────────────────────────────────────────────────────┘
                         │  emits a family_raw.json payload
                         ▼   (contract: docs/family_raw.schema.json)
┌─ Layer 2 — Build (TypeScript, src/providers/uspto.ts::familyTree) ────────────┐
│  Server-side BFS over the continuity DAG from a root application.             │
│  Bounded by maxNodes / maxDepth / time-budget; a 429 aborts with a reason.    │
│  Classifies each node's lineage (root / ancestor / descendant / collateral).  │
└──────────────────────────────────────────────────────────────────────────────┘
                         │  family_raw.json
                         ▼
┌─ Layer 3 — Render (Python, build/*.py) — 100% deterministic, zero network ────┐
│  render_html.py     → self-contained interactive HTML (filters, year-axis,    │
│                       copendency flags, PNG/SVG export, en/zh).               │
│  render_mermaid.py  → Mermaid diagram + text summary (en/zh).                 │
│  layering.py        → shared topological generation layering.                 │
│  validate.py        → family_raw.json contract validation.                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Why the split

- **Layer 3 is pure.** The renderers take a `family_raw.json` and produce output with no
  network access and no credentials, so they are fully unit-tested (`tests/test_render.py`)
  and can be run standalone on the `fixtures/`.
- **`family_raw.json` is the contract** between fetch and render
  (`docs/family_raw.schema.json`). Anything that can produce a conforming payload — this
  server, a fixture, or your own fetcher — can be rendered. That keeps the renderer
  independent of how the data was obtained.

## The MCP tools

`src/index.ts` registers four read-only tools over the layers above:

- `patent_continuity` → Layer 1 single hop.
- `patent_family_tree` → Layers 1–2 → `family_raw.json`.
- `patent_family_chart` → Layers 1–3 → rendered HTML/Mermaid (shells out to Python).
- `patent_status` → configuration/version report.

The API key is redacted from **all** tool output (success and error) as defence in depth.

## Rendering bridge

`patent_family_chart` runs the bundled Python renderers via `src/render-bridge.ts`. The
render directory is resolved relative to the compiled module (`import.meta.url` → the
repo's `build/`), so it works regardless of the working directory; override with
`PATENT_FAMILY_RENDER_DIR` if you relocate the renderers.

## Key ODP fields (for reference)

`GET /patent/applications/{appNo}` → `patentFileWrapperDataBag[0]` carries
`applicationMetaData` (title, dates, `patentNumber`, status, type) plus
`parentContinuityBag` / `childContinuityBag`. Each continuity entry has
`claimParentageTypeCode` (CON / CIP / DIV / …), the neighbour's application number,
filing date, and status. Application numbers may be PCT-formatted (e.g. `PCTUS2016019088`).
