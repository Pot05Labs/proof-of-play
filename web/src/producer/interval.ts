// Geometry for the difference-with-interval bar. Pure so it can be tested.

export interface IntervalScale {
  /** Half-width of the symmetric domain around zero. */
  span: number;
  x: (v: number) => number;
  ticks: number[];
}

function niceCeil(v: number): number {
  if (!(v > 0) || !Number.isFinite(v)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

export function intervalScale(values: (number | null)[], left: number, right: number): IntervalScale {
  const finite = values.filter((v): v is number => v !== null && Number.isFinite(v));
  const span = niceCeil(Math.max(0, ...finite.map(Math.abs)) * 1.1);
  const mid = (left + right) / 2;
  const half = (right - left) / 2;
  return {
    span,
    x: (v: number) => mid + (Math.max(-span, Math.min(span, v)) / span) * half,
    ticks: [-span, -span / 2, 0, span / 2, span],
  };
}

export const isNum = (v: number | null | undefined): v is number => typeof v === 'number' && Number.isFinite(v);

/** Null-safe fixed number for the readout: null/NaN -> "-". */
export const fixed = (v: number | null | undefined, digits: number): string => {
  if (!isNum(v)) return '-';
  const t = v.toFixed(digits);
  // -0.004 rounds to "-0.0"; a signed zero reads like a finding, so drop the sign.
  return Number(t) === 0 ? t.replace(/^-/, '') : t;
};

/** Null-safe signed number for the readout: null/NaN -> "-". */
export const signed = (v: number | null | undefined, digits: number): string => {
  if (!isNum(v)) return '-';
  const t = fixed(v, digits);
  return t !== '0' && Number(t) > 0 ? `+${t}` : t;
};

/**
 * The API now returns null (not NaN, not a 500) for means and interval when an arm has
 * fewer than two sessions. Treat that as "not enough sessions" rather than a readout.
 */
export function tooFewSessions(r: { n_personalised: number; n_generic: number; diff: number | null }): boolean {
  return !(r.n_personalised >= 2 && r.n_generic >= 2) || !isNum(r.diff);
}
