import { describe, expect, it } from 'vitest';
import type { MatchEvent } from './api';
import { ballAfter, ballTrail, eventEnd, eventStart, PITCH_H, PITCH_W, toHomeFrame, toPitch } from './pitch';

const HOME = 'home';
const AWAY = 'away';

function ev(over: Partial<MatchEvent>): MatchEvent {
  return {
    event_id: 'm:00001', match_id: 'm', seq: 1,
    clock: { period: 1, minute: 0, second: 0, added: 0 }, t_ms: 0,
    type: 'pass', team_id: HOME, player_id: null,
    x: null, y: null, end_x: null, end_y: null,
    outcome: null, pressure: null, related: [], meta: {},
    ...over,
  };
}

describe('toHomeFrame', () => {
  it('leaves home-team coordinates unchanged', () => {
    expect(toHomeFrame(80, 20, HOME, HOME)).toEqual({ x: 80, y: 20 });
  });

  it('rotates away-team coordinates 180 degrees', () => {
    expect(toHomeFrame(80, 20, AWAY, HOME)).toEqual({ x: 20, y: 80 });
  });

  it('an away attack near its target goal lands near the home goal (left side)', () => {
    const p = toHomeFrame(95, 50, AWAY, HOME);
    expect(p.x).toBe(5);
    expect(p.y).toBe(50);
  });

  it('keeps the centre spot fixed for both teams', () => {
    expect(toHomeFrame(50, 50, AWAY, HOME)).toEqual({ x: 50, y: 50 });
    expect(toHomeFrame(50, 50, HOME, HOME)).toEqual({ x: 50, y: 50 });
  });

  it('does not mirror events with no team', () => {
    expect(toHomeFrame(10, 30, null, HOME)).toEqual({ x: 10, y: 30 });
  });

  it('mirroring twice is the identity', () => {
    const once = toHomeFrame(33.3, 71.2, AWAY, HOME);
    expect(toHomeFrame(once.x, once.y, AWAY, HOME)).toEqual({ x: 33.3, y: 71.2 });
  });
});

describe('toPitch', () => {
  it('maps 0..100 onto 105 x 68', () => {
    expect(toPitch({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 });
    expect(toPitch({ x: 100, y: 100 })).toEqual({ x: PITCH_W, y: PITCH_H });
    expect(toPitch({ x: 50, y: 50 })).toEqual({ x: 52.5, y: 34 });
  });
});

describe('event positions', () => {
  it('mirrors both start and end for away events', () => {
    const e = ev({ team_id: AWAY, x: 10, y: 20, end_x: 60, end_y: 70 });
    expect(eventStart(e, HOME)).toEqual(toPitch({ x: 90, y: 80 }));
    expect(eventEnd(e, HOME)).toEqual(toPitch({ x: 40, y: 30 }));
  });

  it('ball position is the end point when present, else the start', () => {
    expect(ballAfter(ev({ x: 10, y: 10, end_x: 20, end_y: 30 }), HOME)).toEqual(toPitch({ x: 20, y: 30 }));
    expect(ballAfter(ev({ x: 10, y: 10 }), HOME)).toEqual(toPitch({ x: 10, y: 10 }));
    expect(ballAfter(ev({}), HOME)).toBeNull();
  });

  it('an away clearance end and the home-frame possession change agree', () => {
    // From the API sample: away clears to (56.9, 62.7) and the away team then has the ball at (56.9, 62.7).
    const clearance = ev({ type: 'clearance', team_id: AWAY, x: 11.5, y: 31, end_x: 56.9, end_y: 62.7 });
    const change = ev({ type: 'possession_change', team_id: AWAY, x: 56.9, y: 62.7 });
    expect(ballAfter(clearance, HOME)).toEqual(ballAfter(change, HOME));
  });
});

describe('ballTrail', () => {
  it('returns the last n ball positions oldest first and skips off-ball events', () => {
    const events = [
      ev({ seq: 1, x: 10, y: 10 }),
      ev({ seq: 2, type: 'pressure', x: 90, y: 90 }),
      ev({ seq: 3, x: 20, y: 20 }),
      ev({ seq: 4, type: 'player_tracking' }),
      ev({ seq: 5, team_id: AWAY, x: 30, y: 30 }),
    ];
    expect(ballTrail(events, HOME, 2)).toEqual([toPitch({ x: 20, y: 20 }), toPitch({ x: 70, y: 70 })]);
  });
});
