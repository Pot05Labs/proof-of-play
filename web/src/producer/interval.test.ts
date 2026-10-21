import { describe, expect, it } from 'vitest';
import { intervalScale } from './interval';

describe('intervalScale', () => {
  it('is symmetric around zero so the zero line sits in the middle', () => {
    const s = intervalScale([-0.5, 3.7, 8.0], 0, 600);
    expect(s.x(0)).toBe(300);
    expect(s.x(s.span)).toBe(600);
    expect(s.x(-s.span)).toBe(0);
  });

  it('domain covers the interval with a nice round span', () => {
    const s = intervalScale([-0.52, 3.7, 8.01], 0, 600);
    expect(s.span).toBe(10);
    expect(s.x(8.01)).toBeLessThan(600);
    expect(s.x(-0.52)).toBeLessThan(300);
  });

  it('ignores missing values and falls back to a unit span', () => {
    const s = intervalScale([null, NaN], 0, 100);
    expect(s.span).toBe(1);
    expect(s.ticks).toEqual([-1, -0.5, 0, 0.5, 1]);
  });

  it('clamps values outside the domain', () => {
    const s = intervalScale([1], 0, 100);
    expect(s.x(1000)).toBe(100);
  });
});

import { fixed, signed, tooFewSessions } from './interval';

describe('readout null safety', () => {
  it('formats nulls and NaN as a dash', () => {
    expect(signed(null, 1)).toBe('-');
    expect(signed(NaN, 1)).toBe('-');
    expect(fixed(null, 2)).toBe('-');
    expect(signed(0.04, 2)).toBe('+0.04');
    expect(signed(-1.25, 1)).toBe('-1.3');
    expect(fixed(1.63, 1)).toBe('1.6');
    expect(fixed(-0.0064, 1)).toBe('0.0');
    expect(signed(-0.0064, 1)).toBe('0.0');
    expect(signed(0.0004, 2)).toBe('0.00');
  });

  it('calls a readout too thin when an arm has fewer than two sessions or no difference', () => {
    expect(tooFewSessions({ n_personalised: 1, n_generic: 5, diff: null })).toBe(true);
    expect(tooFewSessions({ n_personalised: 5, n_generic: 5, diff: null })).toBe(true);
    expect(tooFewSessions({ n_personalised: 184, n_generic: 216, diff: 0.04 })).toBe(false);
  });
});
