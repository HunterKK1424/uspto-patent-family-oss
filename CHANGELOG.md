<!-- SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 -->
<!-- Copyright 2026 Chun-Yu Yen (Hunter Yen) -->

# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-10

Initial public (source-available) release.

### Added

- MCP server (stdio) exposing four read-only tools against the USPTO Open Data Portal:
  - `patent_continuity` — one-hop parent/child continuity for an application.
  - `patent_family_tree` — server-side BFS of the whole US continuity DAG →
    `family_raw.json` (supports `scope` full/lineal, `maxNodes`, `maxDepth`, `outputPath`).
  - `patent_family_chart` — the tree rendered as self-contained interactive HTML
    (filters, year-axis timeline with copendency red flags, light/dark, zoom/pan,
    PNG/SVG export) or a static Mermaid diagram.
  - `patent_status` — API-key configuration + server version.
- English / Traditional Chinese output (`PATENT_FAMILY_LANG`, per-call `lang`, or the
  Python renderers' `--lang`).
- ODP burst = 1 request serializer, disk cache (7-day TTL), and node/depth/time-budget
  bounds so large families degrade gracefully with an omitted-neighbour count.
- API-key redaction across all tool output, 429 handling (no auto-retry by default;
  opt-in single retry via `PATENT_ODP_RETRY_429`), and HTTP timeouts.
- Synthetic fixtures, TypeScript tests (`node --test`) and Python renderer tests, and a
  GitHub Actions CI running both.

### Notes

- Licensed under the **PolyForm Noncommercial License 1.0.0** (source-available,
  noncommercial). Commercial use requires a separate license — see [NOTICE](NOTICE).
- This is the **US continuity** genealogy, not the INPADOC cross-office family.

[0.1.0]: https://github.com/HunterKK1424/uspto-patent-family-oss/releases/tag/v0.1.0
