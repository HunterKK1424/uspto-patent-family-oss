#!/usr/bin/env node
// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
//
// uspto-patent-family-oss — an MCP server that builds the US DOMESTIC patent
// family tree (continuity: continuation / CIP / division / provisional) from
// the USPTO Open Data Portal, and renders it as Mermaid or interactive HTML.
//
// NOTE: this is the US continuity genealogy (a DAG), NOT the INPADOC cross-office
// family (the same invention filed in other countries). Those are different things.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { config, redactSecrets, capabilityNote } from "./config.js";
import { VERSION } from "./version.js";
import { fmtContinuity, fmtFamilyTree, fmtFamilyTreeSummary } from "./format.js";
import * as uspto from "./providers/uspto.js";
import { renderChart } from "./render-bridge.js";
import { writeFileSync, existsSync } from "node:fs";
import { isAbsolute } from "node:path";

const server = new McpServer({
  name: "uspto-patent-family",
  version: VERSION,
});

// All tools are read-only lookups against the USPTO ODP API.
const READONLY = { readOnlyHint: true, openWorldHint: true } as const;

function textResult(text: string, isError = false) {
  return { content: [{ type: "text" as const, text }], isError };
}

// Redact the configured API key from ALL output (success and error) so it can
// never leak into the chat transcript, even via an unexpected error path.
async function guard(fn: () => Promise<string>) {
  try {
    return textResult(redactSecrets(await fn()));
  } catch (e: any) {
    return textResult(redactSecrets(`Error: ${e?.message ?? String(e)}`), true);
  }
}

// ---------------------------------------------------------------------------
// patent_continuity  (US DOMESTIC parent/child genealogy — one hop)
// ---------------------------------------------------------------------------
server.registerTool(
  "patent_continuity",
  {
    title: "Get US patent continuity (parent/child genealogy)",
    annotations: READONLY,
    description:
      "Retrieve the US DOMESTIC continuity for one application — its parent and child applications by continuation / continuation-in-part (CIP) / division / provisional parentage, with the claim-parentage type of each link. This is the US prosecution family (a DAG), NOT the INPADOC cross-office family. One hop per call: pass a child/parent application number from the result to walk the tree. Served via USPTO ODP (GET /patent/applications/{appNo}/continuity); requires USPTO_API_KEY. Accepts a US application number in any format (e.g. '15/643,719', '15643719'); publication/patent numbers are not application numbers.",
    inputSchema: {
      applicationNumber: z
        .string()
        .describe("US application number, e.g. '15/643,719' or '15643719' (not a patent/publication number)."),
    },
  },
  async (args) => {
    return guard(async () => {
      const r = await uspto.continuity(args.applicationNumber);
      return fmtContinuity(r, config.lang);
    });
  }
);

// ---------------------------------------------------------------------------
// patent_family_tree  (server-side BFS of the US continuity DAG → raw JSON)
// ---------------------------------------------------------------------------
server.registerTool(
  "patent_family_tree",
  {
    title: "Build US patent family tree (continuity DAG)",
    annotations: READONLY,
    description:
      "Walk the US DOMESTIC continuity genealogy from a root application and return the WHOLE family in one call — every parent/child application reached by continuation / CIP / division / provisional parentage (reexam/reissue links included, labelled), as nodes + directed edges (a DAG). NOT the INPADOC cross-office family. One USPTO ODP call per application (biblio + links together), serialized under ODP burst=1 and cached on disk; a large family therefore takes proportionally longer. Output is a `family_raw.json` payload for the bundled render_html.py / render_mermaid.py — for big families pass `outputPath` to write it to a file instead of inlining. Input is a US APPLICATION number (e.g. '15/643,719' or '15643719').",
    inputSchema: {
      applicationNumber: z
        .string()
        .describe("Root US application number, e.g. '15/643,719' or '15643719'."),
      maxNodes: z
        .number()
        .int()
        .min(1)
        .max(150)
        .optional()
        .describe(
          "Cap on TOTAL applications in the graph — fetched + boundary (default 40). Beyond it, extra neighbours are recorded as an omitted count rather than exploding a huge family (e.g. a provisional thicket). Each fetched node is one serialized ODP call, so a large cap means a slower call; raise it (max 150) for big families you want fully expanded."
        ),
      maxDepth: z
        .number()
        .int()
        .min(1)
        .max(12)
        .optional()
        .describe("Max generations from root in either direction (default 6)."),
      scope: z
        .enum(["full", "lineal"])
        .optional()
        .describe(
          "full (default) = the whole connected family (includes collateral cases sharing an ancestor/descendant). lineal = ONLY this application's own priority chain upward (its benefit/§120 ancestors) + its descendants downward; collateral siblings/cousins are excluded (a descendant's other CIP parents are still shown as un-expanded stubs for EFD analysis). Use lineal for a priority-chain / copendency review."
        ),
      outputPath: z
        .string()
        .optional()
        .describe(
          "Absolute path to write the compact family_raw.json to. When set, the tool returns only a summary + the file path (avoids overflowing the tool-result size limit on large families). Recommended for maxNodes > ~30. SAFETY: the tool will NOT overwrite an existing file — it errors if the path already exists — so point it at a fresh filename in a directory you control."
        ),
    },
  },
  async (args) => {
    return guard(async () => {
      const tree = await uspto.familyTree(
        args.applicationNumber,
        args.maxNodes ?? 40,
        args.maxDepth ?? 6,
        { scope: args.scope ?? "full" }
      );
      if (args.outputPath) {
        if (!isAbsolute(args.outputPath)) {
          throw new Error(`outputPath must be an absolute path (got '${args.outputPath}').`);
        }
        // Refuse to overwrite: never clobber an existing file. `wx` fails if the
        // path exists (defence-in-depth alongside the explicit check), so a
        // model-supplied path can't be steered onto an important file.
        if (existsSync(args.outputPath)) {
          throw new Error(`outputPath already exists — refusing to overwrite: ${args.outputPath}`);
        }
        writeFileSync(args.outputPath, JSON.stringify(tree), { flag: "wx" });
        return fmtFamilyTreeSummary(tree, args.outputPath);
      }
      return fmtFamilyTree(tree);
    });
  }
);

// ---------------------------------------------------------------------------
// patent_family_chart  (family tree, RENDERED — usable directly in a chat)
// ---------------------------------------------------------------------------
server.registerTool(
  "patent_family_chart",
  {
    title: "Render US patent family tree (Mermaid or interactive HTML)",
    annotations: READONLY,
    description:
      "Render a US patent family tree. format='html' (DEFAULT) returns a self-contained interactive HTML page (filters incl. 只看直系/lineal, year-axis timeline + copendency red flags, light/dark toggle, zoom/pan, hover, built-in PNG/SVG download) — present it to the user as an HTML artifact, unmodified. format='mermaid' returns an inline Mermaid diagram (static; use for a quick look). Rendering runs the bundled Python renderers (needs Python 3 on PATH). Input is a US APPLICATION number.\n\nCONFIRM NODE CAP FIRST: if the user has NOT specified maxNodes, do NOT call this tool yet — first tell them the default node cap is 40 and ask them to reply 'ok' to proceed with 40, or raise maxNodes (max 150). Only call after they confirm.",
    inputSchema: {
      applicationNumber: z
        .string()
        .describe("Root US application number, e.g. '15/643,719' or '15643719'."),
      format: z
        .enum(["mermaid", "html"])
        .optional()
        .describe("html (DEFAULT; interactive artifact w/ filters, year-axis, PNG/SVG export) or mermaid (static inline, quick look)."),
      scope: z
        .enum(["full", "lineal"])
        .optional()
        .describe(
          "full (default) = whole connected family. lineal = only this application's priority chain up + descendants down (collateral excluded) — for a priority-chain / copendency view."
        ),
      maxNodes: z.number().int().min(1).max(150).optional().describe("Total-node cap (default 40; confirm with user before rendering — see description)."),
      maxDepth: z.number().int().min(1).max(12).optional().describe("Max generations from root (default 6)."),
      lang: z
        .enum(["en", "zh"])
        .optional()
        .describe("UI language of the rendered chart: en (English) or zh (Traditional Chinese). Defaults to the PATENT_FAMILY_LANG env setting (else en)."),
      minify: z
        .boolean()
        .optional()
        .describe("html only: minify the embedded JS to reduce source readability before sharing (behaviour unchanged). DEFAULT true. Note: this obscures the render code only, NOT the embedded case data."),
    },
  },
  async (args) => {
    return guard(async () => {
      const tree = await uspto.familyTree(
        args.applicationNumber,
        args.maxNodes ?? 40,
        args.maxDepth ?? 6,
        { scope: args.scope ?? "full" }
      );
      const fmt = args.format ?? "html";
      const rendered = renderChart(tree, fmt, args.minify ?? true, args.lang ?? config.lang);
      if (fmt === "html") {
        return (
          "✅ Interactive family-tree chart ready. Present the HTML below to the user as an **HTML artifact** " +
          "(filters, year-axis, light/dark, zoom/pan, PNG/SVG download). Do not modify it.\n\n" +
          rendered
        );
      }
      // mermaid: already a ```mermaid block + summary; renders inline in chat.
      return rendered;
    });
  }
);

// ---------------------------------------------------------------------------
// patent_status  (is the API key configured?)
// ---------------------------------------------------------------------------
server.registerTool(
  "patent_status",
  {
    title: "Server / provider configuration status",
    annotations: READONLY,
    description:
      "Report whether the USPTO ODP API key is configured and the running server version.",
    inputSchema: {},
  },
  async () => {
    return textResult(`# uspto-patent-family (v${VERSION})\n\n${capabilityNote()}`);
  }
);

// ---------------------------------------------------------------------------
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stderr only — stdout is the MCP channel.
  console.error(`uspto-patent-family MCP running on stdio (v${VERSION})`);
}

main().catch((e) => {
  console.error("Fatal:", e);
  process.exit(1);
});
