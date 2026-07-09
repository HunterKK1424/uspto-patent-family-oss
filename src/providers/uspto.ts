// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
//
// USPTO Open Data Portal (ODP) provider — US continuity + family tree.
//
//   Base:  https://api.uspto.gov/api/v1
//   Auth:  header  x-api-key: <key>   (one ODP key covers all ODP APIs)
//
// ACCOUNT-PROTECTION (per data.uspto.gov/apis/api-rate-limits):
//   - Burst = 1: only ONE call per key at a time; concurrent calls are BLOCKED.
//     -> we serialize every ODP request through a queue (never parallel).
//   - Exceeding limits -> HTTP 429. USPTO discourages auto-retry without >=5s.
//     -> on 429 we do NOT auto-retry by default; we surface a clear message.
//   - We also space sequential calls slightly to stay well under the rate.

import { config, usptoEnabled } from "./../config.js";
import { HttpError, fetchWithTimeout } from "../http.js";
import { makeThrottle } from "../throttle.js";
import { cacheGet, cacheSet } from "../cache.js";

const ODP_MIN_GAP_MS = 300; // spacing between sequential ODP calls
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const ODP_429_MSG =
  "USPTO ODP rate limit (HTTP 429). ODP allows only ONE request at a time per key (burst=1) and blocks concurrent calls. Not auto-retrying (to protect your account & weekly quota) — wait a few seconds and try again, and avoid using the same key in two places at once.";

/** Thrown specifically on HTTP 429 so callers (e.g. familyTree) can ABORT a
 *  multi-call walk instead of mistaking a quota block for a missing record. */
export class OdpRateLimitError extends Error {
  constructor(message = ODP_429_MSG) {
    super(message);
    this.name = "OdpRateLimitError";
  }
}

// Opt-in: retry ONCE on 429 after a >=5s wait (USPTO's stated minimum). Off by
// default — USPTO discourages auto-retry. Enable with PATENT_ODP_RETRY_429=1.
const ODP_RETRY_429 = Boolean(process.env.PATENT_ODP_RETRY_429);

// Serializer: guarantees one in-flight ODP request at a time (burst=1) + spacing.
const throttle = makeThrottle(ODP_MIN_GAP_MS);

// GET, cached + serialized. Persistent cache is consulted FIRST: a hit skips both
// the network and the throttle (no quota spend), so re-walking a family is free.
async function odpGet(path: string): Promise<any> {
  const cached = cacheGet(path);
  if (cached !== undefined) return cached;
  return throttle(async () => {
    // Another queued call may have populated the cache while we waited.
    const c = cacheGet(path);
    if (c !== undefined) return c;
    for (let attempt = 0; ; attempt++) {
      const res = await fetchWithTimeout(`${config.uspto.base}${path}`, {
        method: "GET",
        headers: { "x-api-key": config.uspto.key, Accept: "application/json" },
      });
      const text = await res.text();
      if (res.status === 429) {
        if (ODP_RETRY_429 && attempt === 0) {
          await sleep(5000);
          continue;
        }
        throw new OdpRateLimitError();
      }
      if (!res.ok) throw new HttpError(res.status, path, text);
      let parsed: any;
      try {
        parsed = JSON.parse(text);
      } catch {
        throw new Error(`ODP returned non-JSON from ${path}: ${text.slice(0, 200)}`);
      }
      cacheSet(path, parsed);
      return parsed;
    }
  });
}

// ── Continuity (US DOMESTIC parent/child genealogy) ────────────────────────
// This is US continuation / continuation-in-part / division / provisional
// parentage — NOT the INPADOC cross-office family.
//   ODP: GET /patent/applications/{appNo}/continuity
//   Response: { patentFileWrapperDataBag: [ { applicationNumberText,
//                 parentContinuityBag[], childContinuityBag[] } ] }
// Each bag entry carries BOTH parent & child application numbers plus
// claimParentageTypeCode (e.g. "CON","CIP","DIV") + a description text.

export interface ContinuityRef {
  applicationNumberText: string; // the NEIGHBOUR application (parent or child)
  filingDate?: string;
  statusCode?: number;
  statusText?: string;
  relationshipCode?: string; // claimParentageTypeCode, e.g. "CON" / "CIP" / "DIV"
  relationshipDesc?: string; // e.g. "is a Continuation of"
}

export interface ContinuityResult {
  applicationNumberText: string; // the (normalized) queried application
  parents: ContinuityRef[];
  children: ContinuityRef[];
}

/** Strip formatting from an application number for ODP path use: "15/643,719" -> "15643719". */
export function normalizeAppNo(s: string): string {
  return (s || "").trim().replace(/[^0-9A-Za-z]/g, "");
}

function mapRef(e: any, side: "parent" | "child"): ContinuityRef {
  const p = side === "parent";
  return {
    applicationNumberText: (p ? e?.parentApplicationNumberText : e?.childApplicationNumberText) ?? "",
    filingDate: p ? e?.parentApplicationFilingDate : e?.childApplicationFilingDate,
    statusCode: p ? e?.parentApplicationStatusCode : e?.childApplicationStatusCode,
    statusText: p ? e?.parentApplicationStatusDescriptionText : e?.childApplicationStatusDescriptionText,
    relationshipCode: e?.claimParentageTypeCode,
    relationshipDesc: e?.claimParentageTypeCodeDescriptionText,
  };
}

export async function continuity(appNoRaw: string): Promise<ContinuityResult> {
  if (!usptoEnabled()) {
    throw new Error(
      "USPTO ODP is not configured. Set USPTO_API_KEY (register at account.uspto.gov + ID.me, then Manage API Key)."
    );
  }
  const appNo = normalizeAppNo(appNoRaw);
  if (!appNo) throw new Error("continuity: empty application number.");
  const data = await odpGet(`/patent/applications/${encodeURIComponent(appNo)}/continuity`);
  const fw = (data?.patentFileWrapperDataBag ?? [])[0] ?? {};
  const parents = (fw.parentContinuityBag ?? [])
    .map((e: any) => mapRef(e, "parent"))
    .filter((r: ContinuityRef) => r.applicationNumberText);
  const children = (fw.childContinuityBag ?? [])
    .map((e: any) => mapRef(e, "child"))
    .filter((r: ContinuityRef) => r.applicationNumberText);
  return { applicationNumberText: fw.applicationNumberText ?? appNo, parents, children };
}

// ── Full application detail (biblio + continuity in ONE call) ──────────────
// GET /patent/applications/{appNo} returns applicationMetaData (title, dates,
// patentNumber, status, type) AND the continuity bags in the SAME payload, so
// the family-tree walker needs only ONE ODP call per node.

export interface AppBiblio {
  inventionTitle?: string;
  filingDate?: string;
  grantDate?: string;
  statusDate?: string; // applicationStatusDate — when the current status took effect
  patentNumber?: string; // normalized to "US<number>"
  statusCode?: number;
  statusText?: string;
  typeLabel?: string; // "Utility" / "Provisional" / "Reissue" …
  typeCode?: string; // "UTL" / "PRO" …
  applicant?: string;
}

export interface AppDetail {
  applicationNumberText: string;
  biblio: AppBiblio;
  parents: ContinuityRef[];
  children: ContinuityRef[];
}

export async function applicationDetail(appNoRaw: string): Promise<AppDetail> {
  if (!usptoEnabled()) {
    throw new Error("USPTO ODP is not configured. Set USPTO_API_KEY.");
  }
  const appNo = normalizeAppNo(appNoRaw);
  if (!appNo) throw new Error("applicationDetail: empty application number.");
  const data = await odpGet(`/patent/applications/${encodeURIComponent(appNo)}`);
  const fw = (data?.patentFileWrapperDataBag ?? [])[0] ?? {};
  const md = fw.applicationMetaData ?? {};
  const biblio: AppBiblio = {
    inventionTitle: md.inventionTitle,
    filingDate: md.filingDate,
    grantDate: md.grantDate,
    statusDate: md.applicationStatusDate,
    patentNumber: md.patentNumber ? `US${md.patentNumber}` : undefined,
    statusCode: md.applicationStatusCode,
    statusText: md.applicationStatusDescriptionText,
    typeLabel: md.applicationTypeLabelName,
    typeCode: md.applicationTypeCode,
    applicant: md.firstApplicantName,
  };
  const parents = (fw.parentContinuityBag ?? [])
    .map((e: any) => mapRef(e, "parent"))
    .filter((r: ContinuityRef) => r.applicationNumberText);
  const children = (fw.childContinuityBag ?? [])
    .map((e: any) => mapRef(e, "child"))
    .filter((r: ContinuityRef) => r.applicationNumberText);
  return { applicationNumberText: fw.applicationNumberText ?? appNo, biblio, parents, children };
}

// ── Family tree (server-side BFS over continuity) ──────────────────────────
// Normalized short relationship code (mirrors the renderer's normalize_rel).
export function normalizeRel(code?: string, desc?: string): string {
  const s = `${code ?? ""} ${desc ?? ""}`.toUpperCase();
  if (/CIP|IN PART/.test(s)) return "CIP";
  if (/DIV/.test(s)) return "DIV";
  if (/PROVISIONAL/.test(s)) return "PRO";
  if (/371|NATIONAL/.test(s)) return "371";
  if (/REISSUE/.test(s)) return "REISSUE";
  if (/REEXAM|\bREX\b/.test(s)) return "REX";
  if (/CON/.test(s)) return "CON";
  return (code || "UNKNOWN").toUpperCase();
}

// Coarse bucket for COLOURING only. The precise ODP status text is preserved
// separately (FamilyNode.statusText) so nuance ("RO PROCESSING…", national
// stage, expired) is never lost.
export function mapStatusText(statusText?: string, statusCode?: number): string {
  const t = (statusText || "").toLowerCase();
  if (statusCode === 150 || t.includes("patented")) return "granted";
  if (t.includes("provisional")) return "provisional"; // incl. "Provisional Application Expired"
  if (t.includes("abandoned")) return "abandoned";
  if (t) return "pending";
  return "unknown";
}

export function mapStatus(b: AppBiblio): string {
  const type = (b.typeLabel || b.typeCode || "").toLowerCase();
  if (type.includes("provisional") || b.typeCode === "PRO") return "provisional";
  return mapStatusText(b.statusText, b.statusCode);
}

export type Lineage = "root" | "ancestor" | "descendant" | "collateral";

export interface FamilyNode {
  applicationNumberText: string;
  patentNumber?: string;
  inventionTitle?: string;
  filingDate?: string;
  grantDate?: string;
  statusDate?: string; // when current status took effect (for copendency analysis)
  status: string; // coarse bucket for colouring
  statusText?: string; // raw ODP applicationStatusDescriptionText (nuance preserved)
  applicant?: string;
  kind?: string;
  lineage?: Lineage; // relative to root: ancestor(priority chain) / descendant / collateral
  _fetched: boolean;
  _depth: number;
  _omitted?: number; // neighbours dropped because the total-node cap was reached
}

export type TruncationReason = "node-cap" | "depth-cap" | "rate-limit" | "time-budget";
export type FamilyScope = "full" | "lineal";

export interface FamilyTree {
  root: string;
  generatedBy: "provider-a";
  scope: FamilyScope;
  truncated: boolean;
  truncationReason?: TruncationReason; // why the graph is incomplete (most-severe reason)
  nodes: FamilyNode[];
  edges: { from: string; to: string; relationshipType: string; rawTypeCode?: string }[];
}

/**
 * Classify every node as root / ancestor (in root's priority chain, up) /
 * descendant (down) / collateral (shares an ancestor or descendant with root
 * but is on neither of root's own up/down chains). Mode-agnostic: works on a
 * full or lineal graph. Mutates node.lineage.
 */
export function classifyLineage(
  nodes: FamilyNode[],
  edges: { from: string; to: string }[],
  root: string
): void {
  const ids = new Set(nodes.map((n) => n.applicationNumberText));
  const parents = new Map<string, string[]>();
  const children = new Map<string, string[]>();
  for (const e of edges) {
    if (!ids.has(e.from) || !ids.has(e.to)) continue;
    (children.get(e.from) ?? children.set(e.from, []).get(e.from)!).push(e.to);
    (parents.get(e.to) ?? parents.set(e.to, []).get(e.to)!).push(e.from);
  }
  const closure = (start: string, adj: Map<string, string[]>): Set<string> => {
    const seen = new Set<string>();
    const q = [...(adj.get(start) ?? [])];
    while (q.length) {
      const x = q.shift()!;
      if (seen.has(x) || x === start) continue;
      seen.add(x);
      for (const y of adj.get(x) ?? []) if (!seen.has(y)) q.push(y);
    }
    return seen;
  };
  const up = closure(root, parents); // ancestors
  const down = closure(root, children); // descendants
  for (const n of nodes) {
    const a = n.applicationNumberText;
    n.lineage = a === root ? "root" : up.has(a) ? "ancestor" : down.has(a) ? "descendant" : "collateral";
  }
}

const FAMILY_TIME_BUDGET_MS = Number(process.env.PATENT_FAMILY_TIME_BUDGET_MS || 100_000);

export interface FamilyTreeOpts {
  /** Injected per-node fetcher (defaults to applicationDetail); lets tests run
   *  the full BFS with no network. */
  fetchDetail?: (appNo: string) => Promise<AppDetail>;
  /** Stop the walk after this wall-clock budget and return partial results,
   *  rather than risking an MCP-client timeout with no output. */
  timeBudgetMs?: number;
  /** Injectable clock for deterministic tests. */
  now?: () => number;
  /** "full" (default) = whole connected family; "lineal" = only root's priority
   *  chain up (ancestors) + descendants down, plus any CIP collateral parents of
   *  descendants shown as un-expanded stubs (for EFD analysis). */
  scope?: FamilyScope;
}

// Severity so the reported reason is the MOST important cause (a rate-limit
// abort matters more than merely hitting the node cap).
const TRUNC_SEVERITY: Record<TruncationReason, number> = {
  "rate-limit": 0,
  "time-budget": 1,
  "node-cap": 2,
  "depth-cap": 3,
};

/**
 * BFS the US continuity DAG from a root application. ONE ODP call per fetched
 * node (biblio + links together).
 *   maxNodes caps the TOTAL nodes in the graph (fetched + boundary). Once hit,
 *   further neighbours are NOT added as nodes/edges; instead the parent records
 *   how many were omitted (`_omitted`) so a huge family (e.g. a provisional
 *   thicket) stays bounded and legible rather than exploding into hundreds of
 *   stub nodes. ODP calls ≤ maxNodes.
 *   maxDepth caps generations from root in either direction.
 *   A 429 rate-limit ABORTS the walk (truncationReason "rate-limit") rather than
 *   silently marking the node unexpanded; a wall-clock budget likewise returns
 *   partial results. `_depth` is a first-pass BFS hop; renderers recompute exact
 *   generations by topological layering.
 */
export async function familyTree(
  rootRaw: string,
  maxNodes = 40,
  maxDepth = 6,
  opts: FamilyTreeOpts = {}
): Promise<FamilyTree> {
  const fetchDetail = opts.fetchDetail ?? applicationDetail;
  const now = opts.now ?? Date.now;
  const timeBudgetMs = opts.timeBudgetMs ?? FAMILY_TIME_BUDGET_MS;
  const scope: FamilyScope = opts.scope ?? "full";
  if (!opts.fetchDetail && !usptoEnabled()) {
    throw new Error("USPTO ODP is not configured. Set USPTO_API_KEY.");
  }
  const root = normalizeAppNo(rootRaw);
  if (!root) throw new Error("familyTree: empty application number.");
  const t0 = now();

  const nodes = new Map<string, FamilyNode>();
  const edgeKeys = new Set<string>();
  const edges: FamilyTree["edges"] = [];
  const visited = new Set<string>();
  let truncated = false;
  let reason: TruncationReason | undefined;
  const markTruncated = (r: TruncationReason) => {
    truncated = true;
    if (reason === undefined || TRUNC_SEVERITY[r] < TRUNC_SEVERITY[reason]) reason = r;
  };

  const ensureNode = (app: string, depth: number): FamilyNode => {
    let n = nodes.get(app);
    if (!n) {
      n = { applicationNumberText: app, status: "unknown", _fetched: false, _depth: depth };
      nodes.set(app, n);
    } else if (Math.abs(depth) < Math.abs(n._depth)) {
      n._depth = depth; // keep the shallowest depth seen
    }
    return n;
  };
  const stubFromRef = (r: ContinuityRef, depth: number) => {
    const n = ensureNode(r.applicationNumberText, depth);
    if (!n._fetched) {
      if (!n.filingDate && r.filingDate) n.filingDate = r.filingDate;
      if (!n.statusText && r.statusText) n.statusText = r.statusText;
      if (n.status === "unknown") n.status = mapStatusText(r.statusText, r.statusCode);
    }
  };
  const addEdge = (from: string, to: string, code?: string, desc?: string) => {
    const rel = normalizeRel(code, desc);
    const key = `${from}->${to}:${rel}`;
    if (edgeKeys.has(key)) return;
    edgeKeys.add(key);
    const raw = code ?? desc;
    // keep rawTypeCode only when it adds info beyond the normalized short code
    const edge: FamilyTree["edges"][number] = { from, to, relationshipType: rel };
    if (raw && raw.toUpperCase() !== rel) edge.rawTypeCode = raw;
    edges.push(edge);
  };

  // Record an edge + neighbour; enqueue to keep walking only when `enqueue`.
  // In lineal mode a descendant's OTHER parents are recorded (edge + stub) but
  // NOT enqueued → they appear as un-expanded "collateral" CIP parents.
  const consider = (
    n: FamilyNode,
    r: ContinuityRef,
    edgeFrom: string,
    edgeTo: string,
    nd: number,
    dir: Dir,
    enqueue: boolean
  ) => {
    const nb = r.applicationNumberText;
    if (!nodes.has(nb) && nodes.size >= maxNodes) {
      n._omitted = (n._omitted ?? 0) + 1;
      markTruncated("node-cap");
      return;
    }
    addEdge(edgeFrom, edgeTo, r.relationshipCode, r.relationshipDesc);
    stubFromRef(r, nd);
    if (!enqueue || visited.has(nb)) return;
    if (Math.abs(nd) > maxDepth) {
      markTruncated("depth-cap");
      return;
    }
    queue.push({ app: nb, depth: nd, dir });
  };

  ensureNode(root, 0);
  const queue: { app: string; depth: number; dir: Dir }[] = [{ app: root, depth: 0, dir: "root" }];
  while (queue.length) {
    if (now() - t0 > timeBudgetMs) {
      markTruncated("time-budget"); // return what we have rather than time out
      break;
    }
    const { app, depth, dir } = queue.shift()!;
    if (visited.has(app)) continue;
    visited.add(app);

    let detail: AppDetail;
    try {
      detail = await fetchDetail(app);
    } catch (e) {
      if (e instanceof OdpRateLimitError) {
        markTruncated("rate-limit"); // quota block: STOP; don't hammer further
        ensureNode(app, depth)._fetched = false;
        break;
      }
      ensureNode(app, depth)._fetched = false; // e.g. 404: boundary, keep going
      continue;
    }

    const n = ensureNode(app, depth);
    n._fetched = true;
    n.patentNumber = detail.biblio.patentNumber;
    const title = detail.biblio.inventionTitle;
    n.inventionTitle = title && title.length > 100 ? title.slice(0, 99) + "…" : title;
    n.filingDate = detail.biblio.filingDate ?? n.filingDate;
    n.grantDate = detail.biblio.grantDate;
    n.statusDate = detail.biblio.statusDate ?? n.statusDate;
    n.applicant = detail.biblio.applicant;
    n.kind = (detail.biblio.typeLabel || detail.biblio.typeCode || "").toLowerCase() || undefined;
    n.status = mapStatus(detail.biblio);
    n.statusText = detail.biblio.statusText ?? n.statusText;

    const lineal = scope === "lineal";
    const goUp = !lineal || dir === "root" || dir === "up"; // keep climbing ancestors
    const goDown = !lineal || dir === "root" || dir === "down"; // keep descending

    // Parents: climb when goUp; else (lineal descendant) still record collateral parents (no enqueue).
    for (const r of detail.parents) consider(n, r, r.applicationNumberText, app, depth - 1, "up", goUp);
    // Children: descend when goDown; an ancestor's other children are collateral siblings → skip entirely.
    if (goDown) for (const r of detail.children) consider(n, r, app, r.applicationNumberText, depth + 1, "down", true);
  }

  const nodeList = [...nodes.values()];
  classifyLineage(nodeList, edges, root);
  const tree: FamilyTree = { root, generatedBy: "provider-a", scope, truncated, nodes: nodeList, edges };
  if (reason) tree.truncationReason = reason;
  return tree;
}

type Dir = "root" | "up" | "down";
