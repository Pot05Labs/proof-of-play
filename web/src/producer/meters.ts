// Pure maths and null-safe formatting for the producer console's "Live system" panel.
// Kept free of React so every number on screen can be unit tested.

import type { StoreStats, Usage } from '../lib/api';

/** Shown wherever a value is missing. One character, the same everywhere in the panel. */
export const DASH = '-';

/** gpt-4.1-mini list prices, US$ per 1M tokens. */
export const PRICE_PER_M = { input: 0.4, cachedInput: 0.1, output: 1.6 } as const;

/** Thresholds for the database write meter. */
export const STORE_PENDING_ALARM = 100;

const finite = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v);

/**
 * Share of input tokens served from the prompt cache, 0..1.
 * null when there is no usage or no input yet (never 0/0).
 */
export function cacheShare(u: Usage | null | undefined): number | null {
  if (!u || !finite(u.input_tokens) || u.input_tokens <= 0 || !finite(u.cached_input_tokens)) return null;
  return Math.min(1, Math.max(0, u.cached_input_tokens / u.input_tokens));
}

/**
 * Estimated spend in US$. cached_input_tokens is a SUBSET of input_tokens (OpenAI's
 * prompt_tokens includes the cached ones), so cached tokens are billed once, at the cached rate.
 */
export function estimateUsd(u: Usage | null | undefined): number | null {
  if (!u) return null;
  const input = finite(u.input_tokens) ? Math.max(0, u.input_tokens) : 0;
  const cached = finite(u.cached_input_tokens) ? Math.min(input, Math.max(0, u.cached_input_tokens)) : 0;
  const output = finite(u.output_tokens) ? Math.max(0, u.output_tokens) : 0;
  return ((input - cached) * PRICE_PER_M.input + cached * PRICE_PER_M.cachedInput + output * PRICE_PER_M.output) / 1e6;
}

/** "US$0.0375", "US$1.24", "US$0"; small values keep three significant digits. */
export function fmtUsd(v: number | null | undefined): string {
  if (!finite(v)) return DASH;
  if (v === 0) return 'US$0';
  if (Math.abs(v) >= 1) return `US$${v.toFixed(2)}`;
  return `US$${Number(v.toPrecision(3))}`;
}

/** Integer with thin grouping: 187275 -> "187,275". */
export function fmtInt(v: number | null | undefined): string {
  return finite(v) ? Math.round(v).toLocaleString('en-US') : DASH;
}

/** Compact token count: 187275 -> "187.3k", 3836 -> "3,836". */
export function fmtTokens(v: number | null | undefined): string {
  if (!finite(v)) return DASH;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e3).toFixed(1)}k`;
  return fmtInt(v);
}

/** Milliseconds, always in ms so p50 and p95 read on one unit. null -> "-". */
export function fmtMs(v: number | null | undefined): string {
  return finite(v) ? `${Math.round(v).toLocaleString('en-US')} ms` : DASH;
}

/** 0..1 share as a percentage. null -> "-". */
export function fmtShare(v: number | null | undefined, digits = 0): string {
  return finite(v) ? `${(v * 100).toFixed(digits)}%` : DASH;
}

/** The database meter needs attention when any write failed or was dropped, or the queue is backing up. */
export function storeAlarm(s: StoreStats | null | undefined): boolean {
  if (!s) return false;
  return (finite(s.failed) && s.failed > 0) || (finite(s.pending) && s.pending > STORE_PENDING_ALARM)
    || (finite(s.dropped_queue_full) && s.dropped_queue_full > 0);
}

/** Failed model calls as a share of all calls, or null. */
export function failureShare(u: Usage | null | undefined): number | null {
  if (!u || !finite(u.calls) || u.calls <= 0 || !finite(u.failures)) return null;
  return Math.min(1, Math.max(0, u.failures / u.calls));
}

/** "foundry:gpt-4.1-mini" -> { provider: "foundry", name: "gpt-4.1-mini" }. */
export function splitModel(model: string | null | undefined): { provider: string | null; name: string } {
  if (!model) return { provider: null, name: DASH };
  const i = model.indexOf(':');
  return i > 0 ? { provider: model.slice(0, i), name: model.slice(i + 1) } : { provider: null, name: model };
}
