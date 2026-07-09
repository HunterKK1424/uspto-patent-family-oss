// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
//
// Central configuration, read from environment variables.
// This source-available build talks to ONE provider: the USPTO Open Data Portal (ODP).
// The key is optional so the server can boot & list tools even before the user
// has registered for the free API credential.

export const config = {
  uspto: {
    // USPTO Open Data Portal (ODP). One key covers all ODP APIs (header x-api-key).
    // Register free at account.uspto.gov (+ ID.me) → Manage API Key.
    key: process.env.USPTO_API_KEY?.trim() || "",
    base: "https://api.uspto.gov/api/v1",
  },
  httpTimeoutMs: Number(process.env.PATENT_HTTP_TIMEOUT_MS || 30000),
  // Default UI language for rendered charts + text output. Set PATENT_FAMILY_LANG=zh
  // once (e.g. in the MCP client config) to default everything to Traditional Chinese;
  // the patent_family_chart tool can also override per call.
  lang: ((process.env.PATENT_FAMILY_LANG || "").toLowerCase().startsWith("zh") ? "zh" : "en") as "en" | "zh",
};

export type Lang = "en" | "zh";

export const usptoEnabled = (): boolean => Boolean(config.uspto.key);

/** Configured secret value(s) (min length guard avoids nuking short substrings). */
function secretValues(): string[] {
  return [config.uspto.key].filter((v) => v && v.length >= 6);
}

/**
 * Replace any occurrence of a configured API key with "***".
 * Defence-in-depth: applied to ALL tool output (success and error) so the key
 * can never leak into the chat transcript, even via an unexpected error path.
 */
export function redactSecrets(text: string): string {
  let out = text;
  for (const s of secretValues()) out = out.split(s).join("***");
  return out;
}

/** A short human-readable note about what is live vs. gated behind the missing key. */
export function capabilityNote(): string {
  return usptoEnabled()
    ? "✅ USPTO ODP: key set. US continuity + family tree live via `patent_continuity` / " +
        "`patent_family_tree` / `patent_family_chart`; requests serialized under burst=1, " +
        "disk-cached, no auto-retry on 429 (protects your weekly quota / account)."
    : "⛔ USPTO ODP: NOT configured — set USPTO_API_KEY (account.uspto.gov + ID.me → " +
        "Manage API Key). All tools are gated until then.";
}
