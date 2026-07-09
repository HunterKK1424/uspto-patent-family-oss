// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
//
// Unit tests for the US continuity fetch + BFS logic. Zero network: familyTree()
// takes an injected fetchDetail, so the whole walk runs offline & deterministically.
//
//   npm test    (runs: tsc && node --test dist/test.js)

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  normalizeAppNo,
  normalizeRel,
  mapStatusText,
  classifyLineage,
  familyTree,
  OdpRateLimitError,
  type AppDetail,
  type ContinuityRef,
  type FamilyNode,
} from "./providers/uspto.js";

// ── Helpers ────────────────────────────────────────────────────────────────
// Build an in-memory continuity graph and hand familyTree a fetcher over it.
type Spec = { parents?: [string, string][]; children?: [string, string][]; patent?: string; status?: string };

function fakeFetcher(graph: Record<string, Spec>, opts: { failOn?: string; rateLimitOn?: string } = {}) {
  const calls: string[] = [];
  const fetchDetail = async (appNo: string): Promise<AppDetail> => {
    calls.push(appNo);
    if (opts.rateLimitOn === appNo) throw new OdpRateLimitError();
    if (opts.failOn === appNo) throw new Error("404 boundary");
    const g = graph[appNo] ?? {};
    const ref = (a: string, rel: string): ContinuityRef => ({
      applicationNumberText: a,
      relationshipCode: rel,
      relationshipDesc: rel,
    });
    return {
      applicationNumberText: appNo,
      biblio: { patentNumber: g.patent, statusText: g.status, statusCode: g.patent ? 150 : undefined },
      parents: (g.parents ?? []).map(([a, rel]) => ref(a, rel)),
      children: (g.children ?? []).map(([a, rel]) => ref(a, rel)),
    };
  };
  return { fetchDetail, calls };
}

const byId = (t: { nodes: FamilyNode[] }) => Object.fromEntries(t.nodes.map((n) => [n.applicationNumberText, n]));

// ── normalizeAppNo ───────────────────────────────────────────────────────────
test("normalizeAppNo strips punctuation and whitespace", () => {
  assert.equal(normalizeAppNo("15/643,719"), "15643719");
  assert.equal(normalizeAppNo("  15 643 719 "), "15643719");
  assert.equal(normalizeAppNo("PCT/US2016/019088"), "PCTUS2016019088");
});

// ── normalizeRel (CIP must beat CON) ─────────────────────────────────────────
test("normalizeRel classifies relationships, CIP before CON", () => {
  assert.equal(normalizeRel("CON", "Continuation in part"), "CIP");
  assert.equal(normalizeRel("", "is a Continuation of"), "CON");
  assert.equal(normalizeRel("DIV"), "DIV");
  assert.equal(normalizeRel("", "Provisional application"), "PRO");
  assert.equal(normalizeRel("REISSUE"), "REISSUE");
  assert.equal(normalizeRel("weird"), "WEIRD");
});

// ── mapStatusText ────────────────────────────────────────────────────────────
test("mapStatusText coarsens status buckets", () => {
  assert.equal(mapStatusText("Patented Case", 150), "granted");
  assert.equal(mapStatusText("Provisional Application Expired"), "provisional");
  assert.equal(mapStatusText("Abandoned"), "abandoned");
  assert.equal(mapStatusText("Non Final Action Mailed"), "pending");
  assert.equal(mapStatusText(undefined), "unknown");
});

// ── familyTree: basic linear chain ───────────────────────────────────────────
test("familyTree walks a linear chain in both directions", async () => {
  const { fetchDetail, calls } = fakeFetcher({
    P: { children: [["ROOT", "CON"]], patent: "US1" },
    ROOT: { parents: [["P", "CON"]], children: [["C", "CON"]], patent: "US2" },
    C: { parents: [["ROOT", "CON"]], patent: "US3" },
  });
  const t = await familyTree("ROOT", 40, 6, { fetchDetail });
  assert.equal(t.nodes.length, 3);
  assert.equal(t.edges.length, 2);
  assert.equal(t.truncated, false);
  assert.equal(calls.length, 3); // one ODP call per node
  assert.equal(byId(t)["ROOT"].lineage, "root");
  assert.equal(byId(t)["P"].lineage, "ancestor");
  assert.equal(byId(t)["C"].lineage, "descendant");
});

// ── familyTree: dedup on a diamond (DAG merge) ───────────────────────────────
test("familyTree dedups a node reachable by two paths (DAG merge)", async () => {
  const { fetchDetail } = fakeFetcher({
    ROOT: { children: [["A", "CON"], ["B", "CON"]] },
    A: { parents: [["ROOT", "CON"]], children: [["M", "CIP"]] },
    B: { parents: [["ROOT", "CON"]], children: [["M", "CIP"]] },
    M: { parents: [["A", "CIP"], ["B", "CIP"]] },
  });
  const t = await familyTree("ROOT", 40, 6, { fetchDetail });
  const ids = t.nodes.map((n) => n.applicationNumberText).sort();
  assert.deepEqual(ids, ["A", "B", "M", "ROOT"]); // M appears exactly once
  const intoM = t.edges.filter((e) => e.to === "M");
  assert.equal(intoM.length, 2); // both parents recorded
});

// ── familyTree: node cap bounds a big family ─────────────────────────────────
test("familyTree respects maxNodes and records omitted neighbours", async () => {
  const graph: Record<string, Spec> = {
    ROOT: { children: [["c1", "CON"], ["c2", "CON"], ["c3", "CON"], ["c4", "CON"]] },
  };
  for (const c of ["c1", "c2", "c3", "c4"]) graph[c] = { parents: [["ROOT", "CON"]] };
  const t = await familyTree("ROOT", 3, 6, { fetchDetail: fakeFetcher(graph).fetchDetail });
  assert.ok(t.nodes.length <= 3, `nodes ${t.nodes.length} must be <= cap 3`);
  assert.equal(t.truncated, true);
  assert.equal(t.truncationReason, "node-cap");
  const omitted = t.nodes.reduce((s, n) => s + (n._omitted ?? 0), 0);
  assert.ok(omitted > 0, "some neighbours must be recorded as omitted");
});

// ── familyTree: depth cap ────────────────────────────────────────────────────
test("familyTree respects maxDepth", async () => {
  const { fetchDetail } = fakeFetcher({
    ROOT: { children: [["d1", "CON"]] },
    d1: { parents: [["ROOT", "CON"]], children: [["d2", "CON"]] },
    d2: { parents: [["d1", "CON"]], children: [["d3", "CON"]] },
    d3: { parents: [["d2", "CON"]] },
  });
  const t = await familyTree("ROOT", 40, 1, { fetchDetail });
  assert.equal(t.truncated, true);
  assert.equal(t.truncationReason, "depth-cap");
  assert.ok(!t.nodes.some((n) => n.applicationNumberText === "d2" && n._fetched));
});

// ── familyTree: 429 aborts the walk ──────────────────────────────────────────
test("familyTree aborts on a 429 with truncationReason rate-limit", async () => {
  const { fetchDetail } = fakeFetcher(
    {
      ROOT: { children: [["a", "CON"]] },
      a: { parents: [["ROOT", "CON"]], children: [["b", "CON"]] },
      b: { parents: [["a", "CON"]] },
    },
    { rateLimitOn: "a" }
  );
  const t = await familyTree("ROOT", 40, 6, { fetchDetail });
  assert.equal(t.truncated, true);
  assert.equal(t.truncationReason, "rate-limit");
});

// ── familyTree: a 404 boundary keeps walking ─────────────────────────────────
test("familyTree treats a fetch failure as a boundary and continues", async () => {
  const { fetchDetail } = fakeFetcher(
    {
      ROOT: { children: [["ok", "CON"], ["bad", "CON"]] },
      ok: { parents: [["ROOT", "CON"]] },
    },
    { failOn: "bad" }
  );
  const t = await familyTree("ROOT", 40, 6, { fetchDetail });
  assert.equal(t.truncated, false); // a 404 is not a truncation
  assert.equal(byId(t)["bad"]._fetched, false); // recorded as an un-fetched boundary
  assert.equal(byId(t)["ok"]._fetched, true);
});

// ── familyTree: lineal scope excludes collateral ─────────────────────────────
test("familyTree lineal scope drops collateral siblings", async () => {
  const { fetchDetail } = fakeFetcher({
    GP: { children: [["ROOT", "CON"], ["SIB", "CON"]] },
    ROOT: { parents: [["GP", "CON"]] },
    SIB: { parents: [["GP", "CON"]] },
  });
  const full = await familyTree("ROOT", 40, 6, { fetchDetail, scope: "full" });
  assert.ok(full.nodes.some((n) => n.applicationNumberText === "SIB" && n._fetched));
  const { fetchDetail: f2 } = fakeFetcher({
    GP: { children: [["ROOT", "CON"], ["SIB", "CON"]] },
    ROOT: { parents: [["GP", "CON"]] },
    SIB: { parents: [["GP", "CON"]] },
  });
  const lineal = await familyTree("ROOT", 40, 6, { fetchDetail: f2, scope: "lineal" });
  // SIB is an ancestor's other child (collateral) → not expanded in lineal mode
  assert.ok(!lineal.nodes.some((n) => n.applicationNumberText === "SIB" && n._fetched));
});

// ── classifyLineage direct ───────────────────────────────────────────────────
test("classifyLineage labels ancestors, descendants and collateral", () => {
  const nodes: FamilyNode[] = ["ROOT", "P", "C", "COL"].map((a) => ({
    applicationNumberText: a, status: "unknown", _fetched: true, _depth: 0,
  }));
  const edges = [
    { from: "P", to: "ROOT" },
    { from: "ROOT", to: "C" },
    { from: "P", to: "COL" }, // COL is a sibling of ROOT (shares parent P)
  ];
  classifyLineage(nodes, edges, "ROOT");
  const m = Object.fromEntries(nodes.map((n) => [n.applicationNumberText, n.lineage]));
  assert.equal(m["ROOT"], "root");
  assert.equal(m["P"], "ancestor");
  assert.equal(m["C"], "descendant");
  assert.equal(m["COL"], "collateral");
});
