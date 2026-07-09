# uspto-patent-family

An [MCP](https://modelcontextprotocol.io) server that builds the **US domestic patent
family tree** — the *continuity* genealogy (continuation / continuation‑in‑part /
division / provisional, plus reissue & reexam links) — from the **USPTO Open Data
Portal (ODP)**, and renders it as an interactive HTML chart or a Mermaid diagram.

> ### ⚠️ This is *continuity*, not INPADOC
> This tool draws the **US prosecution family** (a parent/child DAG within the USPTO).
> It is **not** the INPADOC cross‑office family (the same invention filed in other
> countries). They are different things — do not confuse one for the other.

**See it:** open [`samples/sample-family-tree.html`](samples/sample-family-tree.html) in a
browser for a live, self-contained example rendered from synthetic data (no API key needed).

## What you get

Four read‑only tools:

| Tool | Purpose |
|------|---------|
| `patent_continuity` | One hop: a single application's direct parents & children. |
| `patent_family_tree` | Server‑side BFS of the whole continuity DAG → `family_raw.json`. |
| `patent_family_chart` | The family tree **rendered** — interactive HTML (default) or Mermaid. |
| `patent_status` | Whether your API key is configured + the server version. |

The HTML chart is self‑contained (no external requests): filters (status / relation /
applicant / lineal‑only / generation depth), a filing‑date **year‑axis timeline** with
copendency red‑flag heuristics, light/dark toggle, zoom/pan, hover detail, and built‑in
PNG/SVG download.

## Requirements

- **Node.js ≥ 18** — runs the MCP server.
- **Python 3** — the chart renderers (`patent_family_chart`) shell out to the bundled
  `build/*.py`. If you only use `patent_family_tree` (raw JSON) you don't need Python.
- **A free USPTO ODP API key** — see below.

## Get a USPTO ODP API key

1. Sign in at [account.uspto.gov](https://account.uspto.gov) (verify with ID.me).
2. Open **Manage API Key** and request a key.
3. One ODP key covers the endpoints this server uses (sent as the `x-api-key` header).

The key has a **weekly quota** and **burst = 1** (one request at a time). This server
serializes every call and caches responses on disk to protect your quota.

## Install

```bash
git clone https://github.com/HunterKK1424/uspto-patent-family-oss.git
cd uspto-patent-family-oss
npm install
npm run build
```

## Connect it to an MCP client

Add the server to your MCP client. For **Claude Desktop**, edit
`claude_desktop_config.json`:

```jsonc
{
  "mcpServers": {
    "uspto-patent-family": {
      "command": "node",
      "args": ["/absolute/path/to/uspto-patent-family-oss/dist/index.js"],
      "env": {
        "USPTO_API_KEY": "your-odp-key-here"
      }
    }
  }
}
```

Restart the client. Ask it something like *"show the US family tree for application
15/643,719"* — it will call `patent_family_chart` and present the interactive HTML.

### Try it without a client (CLI)

The renderers work standalone on any `family_raw.json` (the `fixtures/` files need no key):

```bash
python3 build/render_html.py fixtures/cip_fork.json -o tree.html   # open tree.html
python3 build/render_mermaid.py fixtures/cip_fork.json             # Mermaid + summary
```

## Language (English / 中文)

The chart UI and text output default to **English**. To switch:

- Set `PATENT_FAMILY_LANG=zh` in the server `env` to default everything to Traditional
  Chinese, **or**
- pass `lang: "zh"` to `patent_family_chart` for a single call, **or**
- pass `--lang zh` to the Python renderers on the CLI.

## Configuration (environment variables)

| Variable | Default | Meaning |
|----------|---------|---------|
| `USPTO_API_KEY` | — | **Required.** Your ODP key. |
| `PATENT_FAMILY_LANG` | `en` | `en` or `zh` — default UI language. |
| `PATENT_HTTP_TIMEOUT_MS` | `30000` | HTTP timeout. |
| `PATENT_ODP_CACHE` | on | Set `0` to disable the 7‑day disk cache. |
| `PATENT_PYTHON` | `python3` | Python executable for chart rendering. |

## Limitations (by design)

- **ODP burst = 1 / weekly quota** — large families take proportionally longer; a rate
  limit (HTTP 429) aborts the walk and returns partial results (clearly flagged).
- **Large families are bounded** — `maxNodes` (default 40, max 150) caps total nodes;
  extra neighbours are recorded as an omitted count rather than exploding the graph.
- **Foreign priority is out of scope** — Paris Convention foreign priority is *not* part
  of US continuity (that's INPADOC territory).
- **Continuity ≠ perfected legal benefit** — the graph shows *as‑recorded* relationships;
  specific‑reference completeness and §120 copendency must still be checked case by case.

## Disclaimer

This tool is provided for technical reference only. Its data comes from public USPTO
sources and may be incomplete or out of date. **It does not constitute legal advice** and
must not be relied upon for any determination of patent validity, priority, or continuity.
This is an **unofficial** tool and is **not affiliated with or endorsed by the USPTO**.

## License

**PolyForm Noncommercial License 1.0.0** — see [LICENSE](LICENSE). This is a
*source‑available*, **noncommercial** license (not an OSI "open source" license). You may
use, modify, and share it for any **noncommercial** purpose.

**Commercial use requires a separate license.** Contact **hunterip0305@gmail.com**.
See [NOTICE](NOTICE).

## Contributing

Issues and bug reports are welcome. **Pull requests are not accepted** — to keep the
licensing clean for commercial licensing, the author retains sole copyright. Please open
an issue to discuss ideas or report problems instead.

> When filing an issue, **do not paste your API key or full response logs.**
