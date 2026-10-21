import { describe, expect, it } from 'vitest';
import type { Usage } from '../lib/api';
import {
  DASH, cacheShare, estimateUsd, failureShare, fmtInt, fmtMs, fmtShare, fmtTokens, fmtUsd, splitModel, storeAlarm,
} from './meters';

const usage = (over: Partial<Usage> = {}): Usage => ({
  calls: 0, failures: 0, input_tokens: 0, output_tokens: 0, cached_input_tokens: 0, ...over,
});

describe('estimateUsd', () => {
  it('bills uncached input, cached input and output at gpt-4.1-mini list prices', () => {
    // 1M fresh in = $0.40, 1M out = $1.60
    expect(estimateUsd(usage({ input_tokens: 1_000_000, output_tokens: 1_000_000 }))).toBeCloseTo(2.0, 10);
  });

  it('treats cached tokens as a subset of input, billed once at the cached rate', () => {
    // all 1M input cached = $0.10, not $0.50
    expect(estimateUsd(usage({ input_tokens: 1_000_000, cached_input_tokens: 1_000_000 }))).toBeCloseTo(0.1, 10);
  });

  it('matches a hand calculation on live-shaped numbers', () => {
    const u = usage({ input_tokens: 187_275, cached_input_tokens: 145_024, output_tokens: 3_836 });
    const expected = (42_251 * 0.4 + 145_024 * 0.1 + 3_836 * 1.6) / 1e6;
    expect(estimateUsd(u)).toBeCloseTo(expected, 12);
    expect(fmtUsd(estimateUsd(u))).toBe('US$0.0375');
  });

  it('never bills more cached tokens than input tokens', () => {
    expect(estimateUsd(usage({ input_tokens: 10, cached_input_tokens: 50 }))).toBeCloseTo((10 * 0.1) / 1e6, 15);
  });

  it('is null without usage and zero for an idle client', () => {
    expect(estimateUsd(null)).toBeNull();
    expect(estimateUsd(undefined)).toBeNull();
    expect(estimateUsd(usage())).toBe(0);
  });
});

describe('cacheShare', () => {
  it('is cached / input', () => {
    expect(cacheShare(usage({ input_tokens: 200, cached_input_tokens: 150 }))).toBe(0.75);
    expect(fmtShare(cacheShare(usage({ input_tokens: 187_275, cached_input_tokens: 145_024 })))).toBe('77%');
  });

  it('is null, not NaN, when there is no input yet', () => {
    expect(cacheShare(usage())).toBeNull();
    expect(cacheShare(null)).toBeNull();
    expect(fmtShare(cacheShare(usage()))).toBe(DASH);
  });

  it('clamps to 100%', () => {
    expect(cacheShare(usage({ input_tokens: 10, cached_input_tokens: 20 }))).toBe(1);
  });
});

describe('failureShare', () => {
  it('is failures / calls, null with no calls', () => {
    expect(failureShare(usage({ calls: 4, failures: 1 }))).toBe(0.25);
    expect(failureShare(usage())).toBeNull();
  });
});

describe('null-safe formatting', () => {
  const missing = [null, undefined, NaN, Infinity];

  it.each(missing)('renders %s as a dash everywhere', (v) => {
    for (const f of [fmtMs, fmtInt, fmtTokens, fmtUsd, fmtShare]) {
      expect(f(v as number | null)).toBe(DASH);
    }
  });

  it('formats write lag in whole ms', () => {
    expect(fmtMs(4213.9)).toBe('4,214 ms');
    expect(fmtMs(12218.5)).toBe('12,219 ms');
    expect(fmtMs(0)).toBe('0 ms');
  });

  it('formats counts and tokens', () => {
    expect(fmtInt(2971)).toBe('2,971');
    expect(fmtTokens(3836)).toBe('3,836');
    expect(fmtTokens(187_275)).toBe('187.3k');
    expect(fmtTokens(2_500_000)).toBe('2.50M');
  });

  it('formats money with enough digits for small spends', () => {
    expect(fmtUsd(0)).toBe('US$0');
    expect(fmtUsd(0.000412)).toBe('US$0.000412');
    expect(fmtUsd(1.234)).toBe('US$1.23');
  });
});

describe('storeAlarm', () => {
  it('warns on any failed write', () => {
    expect(storeAlarm({ written: 10, failed: 1, pending: 0 })).toBe(true);
  });

  it('warns only when pending exceeds 100', () => {
    expect(storeAlarm({ written: 10, failed: 0, pending: 100 })).toBe(false);
    expect(storeAlarm({ written: 10, failed: 0, pending: 101 })).toBe(true);
  });

  it('warns when writes were dropped on a full queue', () => {
    expect(storeAlarm({ written: 10, failed: 0, pending: 0, dropped_queue_full: 3 })).toBe(true);
    expect(storeAlarm({ written: 10, failed: 0, pending: 0, dropped_queue_full: 0 })).toBe(false);
  });

  it('is quiet with no store', () => {
    expect(storeAlarm(null)).toBe(false);
  });
});

describe('splitModel', () => {
  it('splits provider from model name', () => {
    expect(splitModel('foundry:gpt-4.1-mini')).toEqual({ provider: 'foundry', name: 'gpt-4.1-mini' });
    expect(splitModel('stub')).toEqual({ provider: null, name: 'stub' });
    expect(splitModel(null)).toEqual({ provider: null, name: DASH });
  });
});
