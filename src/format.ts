// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
import type { ContinuityRef, ContinuityResult, FamilyTree } from "./providers/uspto.js";

export function fmtContinuity(r: ContinuityResult, lang: "en" | "zh" = "en"): string {
  const parentsHdr = lang === "zh" ? "母案 Parents" : "Parents";
  const childrenHdr = lang === "zh" ? "子案 Children" : "Children";
  const line = (ref: ContinuityRef) => {
    const rel = ref.relationshipDesc || ref.relationshipCode || "related";
    const bits = [ref.filingDate ? `filed ${ref.filingDate}` : null, ref.statusText]
      .filter(Boolean)
      .join(" · ");
    return `- ${ref.applicationNumberText} — ${rel}${bits ? ` (${bits})` : ""}`;
  };
  const out: string[] = [
    `# US continuity — application ${r.applicationNumberText}`,
    "_US domestic parentage (continuation / CIP / division / provisional) — NOT the INPADOC cross-office family._",
    "",
  ];
  out.push(`## ${parentsHdr} — ${r.parents.length}`);
  out.push(r.parents.length ? r.parents.map(line).join("\n") : "- (none — this is an earliest/root application)");
  out.push("");
  out.push(`## ${childrenHdr} — ${r.children.length}`);
  out.push(r.children.length ? r.children.map(line).join("\n") : "- (none — this is a leaf application)");
  if (r.parents.length === 0 && r.children.length === 0) {
    out.push("");
    out.push("> No continuity relations reported for this application (isolated / terminal node).");
  }
  // Machine-readable block so a family-tree builder can parse directly.
  out.push("");
  out.push("```json");
  out.push(JSON.stringify(r, null, 1));
  out.push("```");
  return out.join("\n");
}

/** One-line truncation explanation keyed by the MOST-severe reason. */
function truncationLine(tree: FamilyTree): string | null {
  if (!tree.truncated) return null;
  const omitted = tree.nodes.filter((n) => n._omitted);
  const omittedTotal = omitted.reduce((s, n) => s + (n._omitted ?? 0), 0);
  switch (tree.truncationReason) {
    case "rate-limit":
      return "- ⚠️ **INCOMPLETE — stopped on a USPTO rate limit (HTTP 429).** Some branches were never fetched; wait a bit and retry. Results shown so far are partial.";
    case "time-budget":
      return "- ⚠️ **truncated — hit the time budget**; returned partial results. Lower maxNodes, or retry (a warm cache makes the next run faster).";
    case "depth-cap":
      return "- ⚠️ **truncated — hit maxDepth**; deeper generations were not expanded (raise maxDepth to see more).";
    case "node-cap":
    default:
      return `- ⚠️ **truncated — hit the ${tree.nodes.length}-node cap**${
        omittedTotal ? `; ${omittedTotal} further neighbour(s) omitted across ${omitted.length} node(s) (raise maxNodes to see more)` : ""
      }.`;
  }
}

function familyTreeSummary(tree: FamilyTree): string[] {
  const fetched = tree.nodes.filter((n) => n._fetched).length;
  const boundary = tree.nodes.length - fetched;
  const statusCount = new Map<string, number>();
  for (const n of tree.nodes) statusCount.set(n.status, (statusCount.get(n.status) ?? 0) + 1);
  const statusLine = [...statusCount.entries()].map(([k, v]) => `${k} ${v}`).join(", ");
  const out: string[] = [];
  out.push(`# US patent family tree — root application ${tree.root}`);
  out.push("_US continuity DAG (continuation / CIP / division / provisional). NOT the INPADOC cross-office family._");
  out.push("");
  out.push(
    `- **${tree.nodes.length} applications** (${fetched} fetched${boundary ? `, ${boundary} boundary` : ""}), **${tree.edges.length} links**`
  );
  if (statusLine) out.push(`- status: ${statusLine}`);
  const tline = truncationLine(tree);
  if (tline) out.push(tline);
  return out;
}

export function fmtFamilyTree(tree: FamilyTree): string {
  const out = familyTreeSummary(tree);
  out.push("");
  out.push(
    "This JSON is `family_raw.json` (compact) — render it with the bundled render_html.py / render_mermaid.py:"
  );
  out.push("```json");
  out.push(JSON.stringify(tree)); // compact: keeps large families under the tool-result token cap
  out.push("```");
  return out.join("\n");
}

/** Summary + a pointer to the file the caller wrote (used with outputPath, so a
 *  huge family never has to pass its JSON through the tool-result token cap). */
export function fmtFamilyTreeSummary(tree: FamilyTree, writtenPath: string): string {
  const out = familyTreeSummary(tree);
  out.push("");
  out.push(`✅ family_raw.json written to \`${writtenPath}\` — render it with render_html.py / render_mermaid.py.`);
  return out.join("\n");
}
