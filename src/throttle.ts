// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Copyright 2026 Chun-Yu Yen (Hunter Yen)
//
// Request throttle for the USPTO ODP provider.
//
// Serializes calls (one in-flight at a time) and enforces a minimum gap between
// sequential calls, to respect ODP's burst=1 fair-use limit and avoid account
// blocks (ODP allows only ONE request per key at a time; concurrent calls 429).

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export type Throttle = <T>(fn: () => Promise<T>) => Promise<T>;

export function makeThrottle(minGapMs: number): Throttle {
  let queue: Promise<unknown> = Promise.resolve();
  let lastAt = 0;

  return function run<T>(fn: () => Promise<T>): Promise<T> {
    const p = queue.then(async () => {
      const gap = minGapMs - (Date.now() - lastAt);
      if (gap > 0) await sleep(gap);
      try {
        return await fn();
      } finally {
        lastAt = Date.now();
      }
    });
    // Keep the chain alive regardless of success/failure so one rejection does
    // not poison the queue.
    queue = p.then(
      () => undefined,
      () => undefined
    );
    return p as Promise<T>;
  };
}
