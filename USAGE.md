<!-- SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 -->
<!-- Copyright 2026 Chun-Yu Yen (Hunter Yen) -->

# Usage

Four read-only tools, all keyed on a **US application number** (e.g. `15/643,719` or
`15643719`). A publication or patent number is **not** an application number.

> Reminder — this builds the **US continuity** genealogy (a parent/child DAG within the
> USPTO), **not** the INPADOC cross-office family. See the [README](README.md).

---

## `patent_continuity`

One hop of the genealogy: a single application's direct **parents and children** by
continuation / CIP / division / provisional parentage, each link tagged with its
claim-parentage type. Pass a parent/child number from the result back in to walk further.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| `applicationNumber` | string | ✅ | — | Any format: `15/643,719` or `15643719`. |

**Output:** a text summary of the direct parents and children with relationship types.
**ODP cost:** 1 request.

> *"Show the parents and children of US application 15/643,719."*

---

## `patent_family_tree`

Server-side breadth-first walk of the **whole** continuity DAG from a root application,
returned as nodes + directed edges — a `family_raw.json` payload for the bundled
`build/render_html.py` / `build/render_mermaid.py`.

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| `applicationNumber` | string | ✅ | — | Root application. |
| `maxNodes` | int 1–150 | — | `40` | Cap on **total** applications (fetched + boundary). Beyond it, extra neighbours are recorded as an omitted count instead of exploding the graph. Each fetched node = one serialized ODP call, so a higher cap is slower. |
| `maxDepth` | int 1–12 | — | `6` | Max generations from the root in either direction. |
| `scope` | `full` \| `lineal` | — | `full` | `full` = whole connected family (incl. collateral cases). `lineal` = only this application's priority chain up + descendants down; collateral excluded (a descendant's other CIP parents remain as un-expanded stubs for EFD analysis). Use `lineal` for a priority-chain / copendency review. |
| `outputPath` | string (absolute) | — | — | Write the compact JSON to a file instead of inlining it. Returns a summary + the path. **Recommended for `maxNodes` > ~30.** Refuses to overwrite an existing file. |

**Output:** a `family_raw.json` block (or a summary + file path when `outputPath` is set).
**ODP cost:** 1 request per fetched application (serialized under burst = 1; disk-cached).

> *"Build the full US family tree for application 14/054,414 and write it to
> `/Users/me/crispr_family.json`."*

---

## `patent_family_chart`

The family tree **rendered**. Runs the bundled Python renderers (needs Python 3 on PATH).

| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| `applicationNumber` | string | ✅ | — | Root application. |
| `format` | `html` \| `mermaid` | — | `html` | `html` = self-contained interactive page (filters incl. lineal-only, year-axis timeline + copendency red flags, light/dark toggle, zoom/pan, hover, PNG/SVG download). `mermaid` = static inline diagram for a quick look. |
| `scope` | `full` \| `lineal` | — | `full` | Same meaning as `patent_family_tree`. |
| `maxNodes` | int 1–150 | — | `40` | Total-node cap. |
| `maxDepth` | int 1–12 | — | `6` | Max generations from the root. |
| `lang` | `en` \| `zh` | — | `PATENT_FAMILY_LANG`, else `en` | Chart UI language. |
| `minify` | boolean | — | `true` | HTML only: minify the embedded render JS (behaviour unchanged; obscures render code, **not** the embedded case data). |

**Output:** an HTML page (present as an artifact, unmodified) or an inline Mermaid block.
**ODP cost:** same as `patent_family_tree` (it walks the tree first, then renders).

> **Node-cap etiquette:** if you don't set `maxNodes`, the assistant should confirm the
> default cap of 40 with you before rendering (large families can be slow).

> *"Chart the US family tree for application 15/643,719 as an interactive HTML artifact,
> lineal scope, in Chinese."*

---

## `patent_status`

Reports whether `USPTO_API_KEY` is configured and the running server version. No input.
Useful as a first call to confirm the server is wired up before spending quota.

> *"Is the USPTO patent-family server configured?"*

---

## Notes & known limits

- **Requires `USPTO_API_KEY`** for all tools except `patent_status`. The three data tools
  return a clear "not configured" error without it.
- **ODP burst = 1 / weekly quota** — calls are serialized and disk-cached; large families
  take proportionally longer. An HTTP 429 aborts the walk and returns partial results
  (clearly flagged). Set `PATENT_ODP_RETRY_429=1` to retry once after a ≥5 s wait.
- **`patent_family_chart` needs Python 3**; `patent_family_tree` (raw JSON) does not.
- **Continuity ≠ perfected legal benefit** — the graph shows *as-recorded* relationships;
  specific-reference completeness and §120 copendency must still be checked case by case.
  Not legal advice; unofficial; not affiliated with the USPTO.
