// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
//
// Bridge to the bundled deterministic Python renderers (build/render_*.py).
//
// So the family CHART (not just the raw JSON) can come straight out of a tool
// call, `patent_family_chart` shells out to the bundled render_*.py — no second
// renderer, no drift. This makes charts work anywhere the MCP is connected,
// including a plain Claude Desktop chat (which cannot run local scripts itself).
//
// Config:
//   PATENT_FAMILY_RENDER_DIR  -> dir holding render_html.py / render_mermaid.py
//                                (default: the repo's own build/ dir, resolved
//                                 relative to this module — NOT a hardcoded path)
//   PATENT_PYTHON             -> python executable (default: python3)

import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { FamilyTree } from "./providers/uspto.js";

// Compiled layout: dist/render-bridge.js → repo build/ is one level up (../build).
// import.meta.url makes this work regardless of cwd or where the server is launched.
const DEFAULT_RENDER_DIR = fileURLToPath(new URL("../build", import.meta.url));
const RENDER_DIR = process.env.PATENT_FAMILY_RENDER_DIR?.trim() || DEFAULT_RENDER_DIR;
const PYTHON = process.env.PATENT_PYTHON?.trim() || "python3";

export type ChartFormat = "mermaid" | "html";
export type ChartLang = "en" | "zh";

export function renderDirExists(): boolean {
  return existsSync(join(RENDER_DIR, "render_mermaid.py"));
}

export const renderDir = () => RENDER_DIR;

/** Run the Python renderer over a family_raw payload and return its stdout. */
export function renderChart(tree: FamilyTree, fmt: ChartFormat, minify = false, lang: ChartLang = "en"): string {
  const script = fmt === "html" ? "render_html.py" : "render_mermaid.py";
  const scriptPath = join(RENDER_DIR, script);
  if (!existsSync(scriptPath)) {
    throw new Error(
      `Renderer not found at ${scriptPath}. The bundled Python renderers should sit in the ` +
        `repo's build/ dir; set PATENT_FAMILY_RENDER_DIR to override, or use patent_family_tree ` +
        `and run render_html.py yourself.`
    );
  }
  const dir = mkdtempSync(join(tmpdir(), "pfc-"));
  const jf = join(dir, "family_raw.json");
  const extra = [
    "--lang", lang,
    ...(fmt === "html" && minify ? ["--minify"] : []),
  ];
  try {
    writeFileSync(jf, JSON.stringify(tree));
    return execFileSync(PYTHON, [scriptPath, jf, ...extra], {
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (e: any) {
    const code = e?.code;
    if (code === "ENOENT") {
      throw new Error(
        `'${PYTHON}' not found. Charts need Python 3 on PATH (set PATENT_PYTHON to override), or use patent_family_tree + render locally.`
      );
    }
    throw new Error(`Renderer failed: ${e?.stderr || e?.message || String(e)}`);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
