// Pitch geometry. Event coordinates are 0..100 on both axes from the ACTING team's
// attacking perspective (attacking left to right). The viewer draws a single fixed frame
// in which the home team attacks left to right, so away-team actions are rotated 180°.
// The drawing surface is 105 x 68 (metres), y = 0 at the top touchline.

import type { MatchEvent } from './api';

export const PITCH_W = 105;
export const PITCH_H = 68;

export interface Point {
  x: number;
  y: number;
}

/** Map a 0..100 point in the actor's frame to the home frame (still 0..100). */
export function toHomeFrame(x: number, y: number, teamId: string | null, homeTeamId: string): Point {
  const mirror = teamId !== null && teamId !== homeTeamId;
  return mirror ? { x: 100 - x, y: 100 - y } : { x, y };
}

/** 0..100 home-frame point to pitch metres. */
export function toPitch(p: Point): Point {
  return { x: (p.x / 100) * PITCH_W, y: (p.y / 100) * PITCH_H };
}

/** Where the event starts on the drawn pitch, or null when it has no location. */
export function eventStart(e: MatchEvent, homeTeamId: string): Point | null {
  if (e.x === null || e.y === null) return null;
  return toPitch(toHomeFrame(e.x, e.y, e.team_id, homeTeamId));
}

/** Where the event ends on the drawn pitch, or null when it has no end point. */
export function eventEnd(e: MatchEvent, homeTeamId: string): Point | null {
  if (e.end_x === null || e.end_y === null) return null;
  return toPitch(toHomeFrame(e.end_x, e.end_y, e.team_id, homeTeamId));
}

/** The ball's position after the event: its end point if it has one, else its start. */
export function ballAfter(e: MatchEvent, homeTeamId: string): Point | null {
  return eventEnd(e, homeTeamId) ?? eventStart(e, homeTeamId);
}

/** Event types that move or touch the ball (others, e.g. off-ball pressure, are not the ball). */
const BALL_TYPES = new Set([
  'pass', 'carry', 'shot', 'tackle', 'interception', 'clearance', 'foul', 'possession_change', 'kick_off',
]);

export function isBallEvent(e: MatchEvent): boolean {
  return BALL_TYPES.has(e.type) && e.x !== null && e.y !== null;
}

/** The last `n` ball positions, oldest first, for the trail. */
export function ballTrail(events: MatchEvent[], homeTeamId: string, n: number): Point[] {
  const out: Point[] = [];
  for (let i = events.length - 1; i >= 0 && out.length < n; i--) {
    const e = events[i];
    if (!e || !isBallEvent(e)) continue;
    const p = ballAfter(e, homeTeamId);
    if (p) out.push(p);
  }
  return out.reverse();
}
