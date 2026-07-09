// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
//
// Persistent on-disk cache for ODP GET responses.
//
// ODP has a WEEKLY quota and burst=1 serialization, so re-walking the same
// patent family (e.g. tweaking a chart) would otherwise re-spend calls. Patent
// bibliographic + continuity data changes slowly, so a TTL'd file cache keyed by
// request path is safe and cheap. Cache HITS skip the network AND the throttle.
//
// Config (all optional):
//   PATENT_ODP_CACHE=0            -> disable entirely
//   PATENT_ODP_CACHE_DIR=<path>   -> cache location (default: <tmp>/patent-mcp-cache)
//   PATENT_ODP_CACHE_TTL_MS=<ms>  -> freshness window (default: 7 days)

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const ENABLED = process.env.PATENT_ODP_CACHE !== "0";
const DIR = process.env.PATENT_ODP_CACHE_DIR?.trim() || join(tmpdir(), "patent-mcp-cache");
const TTL_MS = Number(process.env.PATENT_ODP_CACHE_TTL_MS || 7 * 24 * 3600_000);

let ready = false;
function ensureDir(): boolean {
  if (!ENABLED) return false;
  if (ready) return true;
  try {
    if (!existsSync(DIR)) mkdirSync(DIR, { recursive: true });
    ready = true;
  } catch {
    return false; // never let cache I/O break a real request
  }
  return ready;
}

function fileFor(key: string): string {
  const h = createHash("sha1").update(key).digest("hex");
  return join(DIR, `${h}.json`);
}

/** Return cached value for `key` if present and within TTL, else undefined. */
export function cacheGet(key: string): any | undefined {
  if (!ensureDir()) return undefined;
  const f = fileFor(key);
  if (!existsSync(f)) return undefined;
  try {
    const { ts, data } = JSON.parse(readFileSync(f, "utf8"));
    if (typeof ts !== "number" || Date.now() - ts > TTL_MS) return undefined;
    return data;
  } catch {
    return undefined; // corrupt entry -> treat as miss
  }
}

/** Store `data` under `key`. Best-effort; failures are swallowed. */
export function cacheSet(key: string, data: any): void {
  if (!ensureDir()) return;
  try {
    writeFileSync(fileFor(key), JSON.stringify({ ts: Date.now(), data }));
  } catch {
    /* best-effort */
  }
}
