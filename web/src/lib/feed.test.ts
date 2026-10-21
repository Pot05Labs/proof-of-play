import { describe, expect, it } from 'vitest';
import type { FeedInsight } from './api';
import { LEAVE_MS, mergeFeed } from './feed';

const ins = (id: string, t_ms: number): FeedInsight => ({
  insight_id: id, minute: Math.floor(t_ms / 60000), t_ms, text: `text ${id}`, fact_ids: [`F-${id}`], importance: 0.5, kind: 'goal',
});

describe('mergeFeed', () => {
  it('first load shows everything newest first without slide-in', () => {
    const out = mergeFeed([], [ins('a', 1000), ins('b', 5000)], 0, true);
    expect(out.map((c) => c.insight_id)).toEqual(['b', 'a']);
    expect(out.every((c) => !c.fresh && c.status === 'live')).toBe(true);
  });

  it('marks only newly arrived insights as fresh', () => {
    const first = mergeFeed([], [ins('a', 1000)], 0, true);
    const second = mergeFeed(first, [ins('a', 1000), ins('b', 2000)], 10, false);
    expect(second.find((c) => c.insight_id === 'b')?.fresh).toBe(true);
    expect(second.find((c) => c.insight_id === 'a')?.fresh).toBe(false);
    const third = mergeFeed(second, [ins('a', 1000), ins('b', 2000)], 20, false);
    expect(third.every((c) => !c.fresh)).toBe(true);
  });

  it('keeps a pulled insight as leaving, then drops it after LEAVE_MS', () => {
    const first = mergeFeed([], [ins('goal', 1000), ins('x', 2000)], 0, true);
    const pulled = mergeFeed(first, [ins('x', 2000)], 100, false);
    const leaving = pulled.find((c) => c.insight_id === 'goal');
    expect(leaving?.status).toBe('leaving');
    expect(leaving?.leftAt).toBe(100);

    const still = mergeFeed(pulled, [ins('x', 2000)], 100 + LEAVE_MS - 1, false);
    expect(still.some((c) => c.insight_id === 'goal')).toBe(true);
    const gone = mergeFeed(still, [ins('x', 2000)], 100 + LEAVE_MS, false);
    expect(gone.map((c) => c.insight_id)).toEqual(['x']);
  });

  it('a restart replaces the feed with no exit animation', () => {
    const first = mergeFeed([], [ins('a', 1000), ins('b', 2000)], 0, true);
    const restarted = mergeFeed(first, [], 50, true);
    expect(restarted).toEqual([]);
  });
});
