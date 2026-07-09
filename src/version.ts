// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
//
// Server version — derived at runtime from package.json (single source of truth,
// so the version can never drift between package.json and the reported value).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// Compiled layout: dist/version.js → package.json is one level up.
let version = "0.0.0";
try {
  const pkg = JSON.parse(readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8"));
  if (typeof pkg.version === "string") version = pkg.version;
} catch {
  /* fall back to 0.0.0 if package.json is unreadable */
}

export const VERSION = version;
