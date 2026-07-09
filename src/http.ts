// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
import { config, redactSecrets } from "./config.js";

/** Drop any query string from a URL — it may carry a secret token. */
function stripQuery(url: string): string {
  const i = url.indexOf("?");
  return i === -1 ? url : url.slice(0, i);
}

export class HttpError extends Error {
  constructor(
    public status: number,
    public url: string,
    public body: string
  ) {
    // Never put the query string in the message — it can leak an API token. Run
    // the response body through redactSecrets too, in case a provider echoes a
    // credential back to us (belt-and-suspenders before guard()'s outer redact).
    super(`HTTP ${status} for ${stripQuery(url)}: ${redactSecrets(body.slice(0, 300))}`);
    this.name = "HttpError";
  }
}

interface FetchOpts {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
  timeoutMs?: number;
}

/**
 * fetch() with an AbortController timeout. Providers that need custom response
 * handling (e.g. USPTO ODP's 429 logic) call this directly so they still get a
 * timeout. Throws a tagged Error so callers can distinguish a timeout from an abort.
 */
export async function fetchWithTimeout(url: string, opts: FetchOpts = {}): Promise<Response> {
  const controller = new AbortController();
  const ms = opts.timeoutMs ?? config.httpTimeoutMs;
  const timeout = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, {
      method: opts.method ?? "GET",
      headers: opts.headers,
      body: opts.body,
      signal: controller.signal,
    });
  } catch (e: any) {
    if (e?.name === "AbortError") {
      throw new Error(`Request timed out after ${ms}ms for ${stripQuery(url)}`);
    }
    throw e;
  } finally {
    clearTimeout(timeout);
  }
}
