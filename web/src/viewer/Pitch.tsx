import { memo, useMemo } from 'react';
import type { MatchEvent, MatchInfo } from '../lib/api';
import { legibleOn } from '../lib/colour';
import { ballAfter, ballTrail, eventEnd, eventStart, isBallEvent, PITCH_H, PITCH_W } from '../lib/pitch';

const TRAIL = 8;
const LINE = 'rgba(238,241,246,0.55)';
const GROUND = '#151c2e';

interface Props {
  info: MatchInfo;
  events: MatchEvent[];
  /** Evidence events to highlight (SHOW ME), in any order. */
  highlight: MatchEvent[];
}

function Markings() {
  const pa = { d: 16.5, w: 40.32 };
  const ga = { d: 5.5, w: 18.32 };
  const goalW = 7.32;
  const cy = PITCH_H / 2;
  const stripes = Array.from({ length: 10 }, (_, i) => i);
  return (
    <g>
      {stripes.map((i) => (
        <rect key={i} x={(PITCH_W / 10) * i} y={0} width={PITCH_W / 10} height={PITCH_H}
          fill={i % 2 ? '#18203a' : '#141b31'} />
      ))}
      <g fill="none" stroke={LINE} strokeWidth={0.35}>
        <rect x={0} y={0} width={PITCH_W} height={PITCH_H} />
        <line x1={PITCH_W / 2} y1={0} x2={PITCH_W / 2} y2={PITCH_H} />
        <circle cx={PITCH_W / 2} cy={cy} r={9.15} />
        {/* left */}
        <rect x={0} y={cy - pa.w / 2} width={pa.d} height={pa.w} />
        <rect x={0} y={cy - ga.w / 2} width={ga.d} height={ga.w} />
        <path d={`M ${pa.d} ${cy - 7.3} A 9.15 9.15 0 0 1 ${pa.d} ${cy + 7.3}`} />
        {/* right */}
        <rect x={PITCH_W - pa.d} y={cy - pa.w / 2} width={pa.d} height={pa.w} />
        <rect x={PITCH_W - ga.d} y={cy - ga.w / 2} width={ga.d} height={ga.w} />
        <path d={`M ${PITCH_W - pa.d} ${cy - 7.3} A 9.15 9.15 0 0 0 ${PITCH_W - pa.d} ${cy + 7.3}`} />
      </g>
      <g fill={LINE}>
        <circle cx={PITCH_W / 2} cy={cy} r={0.5} />
        <circle cx={11} cy={cy} r={0.4} />
        <circle cx={PITCH_W - 11} cy={cy} r={0.4} />
      </g>
      <rect x={-2} y={cy - goalW / 2} width={2} height={goalW} fill="none" stroke={LINE} strokeWidth={0.35} />
      <rect x={PITCH_W} y={cy - goalW / 2} width={2} height={goalW} fill="none" stroke={LINE} strokeWidth={0.35} />
    </g>
  );
}

function PitchView({ info, events, highlight }: Props) {
  const homeId = info.home.team_id;
  const homeTint = legibleOn(info.home.colour, GROUND, 3);
  const awayTint = legibleOn(info.away.colour, GROUND, 3);

  const trail = useMemo(() => ballTrail(events, homeId, TRAIL), [events, homeId]);
  const lastBall = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      if (e && isBallEvent(e)) return e;
    }
    return null;
  }, [events]);
  const ball = lastBall ? ballAfter(lastBall, homeId) : null;

  const marks = useMemo(
    () =>
      [...highlight]
        .sort((a, b) => a.seq - b.seq)
        .map((e) => ({ e, start: eventStart(e, homeId), end: eventEnd(e, homeId) }))
        .filter((m) => m.start !== null),
    [highlight, homeId],
  );

  const teamOf = (id: string | null) => (id === homeId ? homeTint : id === info.away.team_id ? awayTint : '#eef1f6');
  const actor = lastBall?.player_id
    ? [info.home, info.away].flatMap((t) => t.squad).find((p) => p.player_id === lastBall.player_id)
    : undefined;
  const label = ball
    ? `Pitch. Ball at ${Math.round(ball.x)} of ${PITCH_W} metres from the ${info.home.short} goal${
        lastBall ? `, after a ${lastBall.type.replace(/_/g, ' ')}` : ''
      }${actor ? ` by ${actor.name}` : ''}.`
    : 'Pitch. Waiting for kick-off.';

  return (
    <svg className="pitch-svg" viewBox={`-3 -3 ${PITCH_W + 6} ${PITCH_H + 6}`} role="img" aria-label={label}>
      <rect x={-3} y={-3} width={PITCH_W + 6} height={PITCH_H + 6} fill="#10172a" />
      <Markings />
      {/* goal ends tinted by the defending side */}
      <rect x={-2.8} y={PITCH_H / 2 - 3.66} width={0.8} height={7.32} fill={homeTint} />
      <rect x={PITCH_W + 2} y={PITCH_H / 2 - 3.66} width={0.8} height={7.32} fill={awayTint} />

      {marks.length === 0 && trail.length > 1 && (
        <g>
          {trail.slice(1).map((p, i) => {
            const prev = trail[i]!;
            const o = (i + 1) / trail.length;
            return (
              <line key={i} x1={prev.x} y1={prev.y} x2={p.x} y2={p.y}
                stroke="#ffc247" strokeOpacity={0.15 + o * 0.6} strokeWidth={0.25 + o * 0.45} strokeLinecap="round" />
            );
          })}
          {trail.slice(0, -1).map((p, i) => (
            <circle key={`d${i}`} cx={p.x} cy={p.y} r={0.55} fill="#ffc247" fillOpacity={0.2 + (i / trail.length) * 0.5} />
          ))}
        </g>
      )}

      {marks.length > 0 && (
        <g>
          <polyline
            points={marks.map((m) => `${m.start!.x},${m.start!.y}`).join(' ')}
            fill="none" stroke="#ffc247" strokeOpacity={0.45} strokeWidth={0.35} strokeDasharray="1 1"
          />
          {marks.map(({ e, start, end }, i) => (
            <g key={e.event_id}>
              {end && (
                <line x1={start!.x} y1={start!.y} x2={end.x} y2={end.y}
                  stroke={teamOf(e.team_id)} strokeWidth={0.5} strokeLinecap="round" />
              )}
              <circle cx={start!.x} cy={start!.y} r={2.3} fill="#ffc247" stroke="#0d1220" strokeWidth={0.4} />
              <text x={start!.x} y={start!.y + 0.95} textAnchor="middle" fontSize={2.6} fontWeight={800}
                fill="#2a1d00" fontFamily="Hanken Grotesk Variable, sans-serif">
                {i + 1}
              </text>
            </g>
          ))}
        </g>
      )}

      {ball && marks.length === 0 && (
        <g>
          <circle className="ball-ring" cx={ball.x} cy={ball.y} r={1.6} fill="none" stroke="#ffc247" strokeWidth={0.35} />
          <circle cx={ball.x} cy={ball.y} r={1.25} fill="#ffc247" stroke="#0d1220" strokeWidth={0.3} />
          {lastBall && (
            <circle cx={ball.x} cy={ball.y} r={0.45} fill={teamOf(lastBall.team_id)} />
          )}
        </g>
      )}
    </svg>
  );
}

export const Pitch = memo(PitchView);
