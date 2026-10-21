import type { MatchInfo } from '../lib/api';
import { legibleOn } from '../lib/colour';
import type { Labels } from '../lib/i18n';

const GROUND = '#151c2e';

export function Momentum({ info, value, t }: { info: MatchInfo; value: number; t: Labels }) {
  const v = Math.max(-1, Math.min(1, value));
  const homeTint = legibleOn(info.home.colour, GROUND, 3);
  const awayTint = legibleOn(info.away.colour, GROUND, 3);
  const lead = Math.abs(v) < 0.1 ? null : v > 0 ? info.home : info.away;
  const width = `${Math.abs(v) * 50}%`;
  return (
    <section className="panel" aria-labelledby="mom-h">
      <h2 id="mom-h">{t.momentum}</h2>
      <p className="momentum-read" aria-live="polite">
        {lead ? `${lead.name} ${t.pushing}` : t.level}
      </p>
      <div
        className="momentum-track"
        role="meter"
        aria-valuemin={-1}
        aria-valuemax={1}
        aria-valuenow={Number(v.toFixed(2))}
        aria-valuetext={lead ? `${lead.name}, ${Math.abs(v).toFixed(2)}` : t.level}
        aria-label={`${t.momentum}: positive favours ${info.home.name}`}
      >
        <div
          className="momentum-fill"
          style={v >= 0 ? { right: '50%', width, background: homeTint } : { left: '50%', width, background: awayTint }}
        />
        <div className="momentum-zero" />
      </div>
      <div className="momentum-labels" aria-hidden="true">
        <span>{info.home.short}</span>
        <span>{info.away.short}</span>
      </div>
    </section>
  );
}

const SEGMENTS = 12;

export function ControlChaos({ value, t }: { value: number; t: Labels }) {
  const v = Math.max(0, Math.min(1, value));
  const cx = 50, cy = 50, r = 40;
  const angle = Math.PI * (1 - v);
  const nx = cx + Math.cos(angle) * (r - 6);
  const ny = cy - Math.sin(angle) * (r - 6);
  const word = v < 0.4 ? t.control : v > 0.6 ? t.chaos : `${t.control} / ${t.chaos}`;
  return (
    <section className="panel" aria-labelledby="cc-h">
      <h2 id="cc-h">{t.controlChaos}</h2>
      <svg className="gauge" viewBox="0 0 100 70" role="meter" aria-valuemin={0} aria-valuemax={1}
        aria-valuenow={Number(v.toFixed(2))} aria-valuetext={`${v.toFixed(2)}, ${word}`} aria-label={t.controlChaos}>
        {Array.from({ length: SEGMENTS }, (_, i) => {
          const a0 = Math.PI * (1 - i / SEGMENTS) - 0.03;
          const a1 = Math.PI * (1 - (i + 1) / SEGMENTS) + 0.03;
          const p = (a: number, rr: number) => `${cx + Math.cos(a) * rr} ${cy - Math.sin(a) * rr}`;
          const lit = (i + 0.5) / SEGMENTS <= v;
          return (
            <path key={i}
              d={`M ${p(a0, r)} A ${r} ${r} 0 0 1 ${p(a1, r)} L ${p(a1, r - 7)} A ${r - 7} ${r - 7} 0 0 0 ${p(a0, r - 7)} Z`}
              fill={lit ? (i / SEGMENTS > 0.6 ? '#ff8a7a' : '#eef1f6') : '#2a3550'} />
          );
        })}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#ffc247" strokeWidth={2} strokeLinecap="round"
          style={{ transition: 'all 600ms ease' }} />
        <circle cx={cx} cy={cy} r={3} fill="#ffc247" />
        <text x={cx} y={cy + 17} textAnchor="middle" fontSize={13} fontWeight={800}
          fontFamily="Big Shoulders Display, sans-serif" fill="#eef1f6">{v.toFixed(2)}</text>
      </svg>
      <div className="gauge-legend" aria-hidden="true">
        <span>{t.control}</span>
        <span>{t.chaos}</span>
      </div>
    </section>
  );
}
