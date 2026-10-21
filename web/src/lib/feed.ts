// Merges successive /api/feed snapshots into what the viewer sees. An insight that was in the
// previous snapshot but is missing from the next one was pulled by the server (a VAR overturn
// retracted the facts it cited), so it stays on screen briefly as "leaving" before it goes.

import type { FeedInsight } from './api';

export const LEAVE_MS = 5000;

export interface DisplayCard extends FeedInsight {
  status: 'live' | 'leaving';
  /** True the first time a card appears after the initial load (drives the slide-in). */
  fresh: boolean;
  leftAt?: number;
}

export function byNewest(a: FeedInsight, b: FeedInsight): number {
  return b.t_ms - a.t_ms || b.importance - a.importance;
}

/**
 * @param prev   cards currently displayed
 * @param next   the latest feed snapshot from the server
 * @param now    wall-clock ms, for expiring leaving cards
 * @param reset  true on first load or after a broadcast restart: no exit animations
 */
export function mergeFeed(prev: DisplayCard[], next: FeedInsight[], now: number, reset: boolean): DisplayCard[] {
  if (reset) return [...next].sort(byNewest).map((i) => ({ ...i, status: 'live', fresh: false }));

  const nextIds = new Set(next.map((i) => i.insight_id));
  const prevById = new Map(prev.map((c) => [c.insight_id, c]));
  const out: DisplayCard[] = [];

  for (const i of next) {
    const before = prevById.get(i.insight_id);
    out.push({ ...i, status: 'live', fresh: !before });
  }
  for (const c of prev) {
    if (nextIds.has(c.insight_id)) continue;
    if (c.status === 'leaving') {
      if (c.leftAt !== undefined && now - c.leftAt < LEAVE_MS) out.push(c);
    } else {
      out.push({ ...c, status: 'leaving', fresh: false, leftAt: now });
    }
  }
  return out.sort(byNewest);
}
