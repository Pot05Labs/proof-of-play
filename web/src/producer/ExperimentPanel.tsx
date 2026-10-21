import { useEffect, useState } from 'react';
import { api, ApiError, type Metric, type Readout } from '../lib/api';
import { fixed, intervalScale, isNum, signed, tooFewSessions } from './interval';

const READOUT_MS = 5000;

const METRICS: { metric: Metric; title: string; unit: string; digits: number }[] = [
  { metric: 'watched_minutes', title: 'Watched minutes per session (primary)', unit: 'min', digits: 1 },
  { metric: 'taps_per_minute', title: 'Why and show-me taps per watched minute (secondary)', unit: 'taps/min', digits: 2 },
];

type Result = { kind: 'ok'; r: Readout } | { kind: 'too_few' } | { kind: 'error'; message: string } | { kind: 'loading' };

function useReadout(key: string, metric: Metric, simulated: boolean): Result {
  const [res, setRes] = useState<Result>({ kind: 'loading' });
  useEffect(() => {
    let alive = true;
    setRes({ kind: 'loading' });
    const load = () =>
      api
        .readout(key, metric, simulated)
        .then((r) => alive && setRes({ kind: 'ok', r }))
        .catch((e: unknown) => {
          if (!alive) return;
          // Older API builds could not serialise a "too few sessions" readout (NaN means) and
          // returned 500. Current builds return 200 with nulls, handled in ReadoutBlock.
          if (e instanceof ApiError && e.status === 500 && !simulated) setRes({ kind: 'too_few' });
          else setRes({ kind: 'error', message: e instanceof Error ? e.message : 'Readout failed' });
        });
    void load();
    const id = setInterval(load, READOUT_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [key, metric, simulated]);
  return res;
}

const levelPct = (level: number | null | undefined) => (isNum(level) ? `${Math.round(level * 100)}%` : '95%');

function IntervalBar({ r, unit, digits }: { r: Readout; unit: string; digits: number }) {
  const W = 440, L = 22, R = 418;
  const s = intervalScale([r.ci_low, r.ci_high, r.diff], L, R);
  const has = isNum(r.ci_low) && isNum(r.ci_high);
  const fmt = (v: number) => signed(v, digits);
  const desc = has && isNum(r.diff)
    ? `Difference ${fmt(r.diff)} ${unit}, ${levelPct(r.level)} interval ${fmt(r.ci_low!)} to ${fmt(r.ci_high!)}.`
    : 'No interval yet.';
  return (
    <svg className="interval" viewBox={`0 0 ${W} 112`} role="img" aria-label={desc}>
      <line x1={L} y1={46} x2={R} y2={46} stroke="#2a3550" strokeWidth={2} />
      {s.ticks.map((tk) => (
        <g key={tk}>
          <line x1={s.x(tk)} y1={40} x2={s.x(tk)} y2={52} stroke="#2a3550" strokeWidth={2} />
          <text x={s.x(tk)} y={74} textAnchor="middle" fontSize={15} fill="#9ba6bd"
            fontFamily="Hanken Grotesk Variable, sans-serif">{tk === 0 ? '0' : fmt(tk)}</text>
        </g>
      ))}
      <line x1={s.x(0)} y1={30} x2={s.x(0)} y2={62} stroke="#eef1f6" strokeWidth={2.5} />
      {has && (
        <>
          <line x1={s.x(r.ci_low!)} y1={46} x2={s.x(r.ci_high!)} y2={46} stroke="#ffc247" strokeWidth={12} strokeLinecap="butt" />
          <line x1={s.x(r.ci_low!)} y1={34} x2={s.x(r.ci_low!)} y2={58} stroke="#ffc247" strokeWidth={3} />
          <line x1={s.x(r.ci_high!)} y1={34} x2={s.x(r.ci_high!)} y2={58} stroke="#ffc247" strokeWidth={3} />
        </>
      )}
      {isNum(r.diff) && (
        <g transform={`translate(${s.x(r.diff)} 46)`}>
          <rect x={-8} y={-8} width={16} height={16} transform="rotate(45)" fill="#eef1f6" stroke="#0d1220" strokeWidth={3} />
          <text y={-18} textAnchor="middle" fontSize={21} fontWeight={800} fill="#eef1f6"
            fontFamily="Big Shoulders Display, sans-serif">{fmt(r.diff)} {unit}</text>
        </g>
      )}
      <text x={L} y={102} fontSize={15} fill="#9ba6bd" fontFamily="Hanken Grotesk Variable, sans-serif">Generic ahead</text>
      <text x={R} y={102} fontSize={15} fill="#9ba6bd" textAnchor="end" fontFamily="Hanken Grotesk Variable, sans-serif">Personalised ahead</text>
    </svg>
  );
}

function ReadoutBlock({ pkey, metric, title, unit, digits, simulated }: {
  pkey: string; metric: Metric; title: string; unit: string; digits: number; simulated: boolean;
}) {
  const res = useReadout(pkey, metric, simulated);
  const mean = (v: number | null) => fixed(v, digits);
  return (
    <div className="readout">
      <h3>{title}</h3>
      {res.kind === 'loading' && <p className="verdict-note">Loading readout</p>}
      {res.kind === 'error' && <p className="verdict-note" style={{ color: 'var(--alert)' }}>{res.message}</p>}
      {res.kind === 'too_few' && (
        <>
          <p className="verdict">Not enough sessions yet.</p>
          <p className="verdict-note">The server returned no readout because an arm has fewer than two sessions.</p>
        </>
      )}
      {res.kind === 'ok' && tooFewSessions(res.r) && (
        <>
          <p className="verdict">Not enough sessions yet.</p>
          <p className="verdict-note">
            {res.r.n_personalised} personalised and {res.r.n_generic} generic sessions so far. Each arm needs at
            least two before the console can draw an interval.
          </p>
        </>
      )}
      {res.kind === 'ok' && !tooFewSessions(res.r) && (
        <>
          <div className="arms">
            <div className="arm">
              <div className="k">Personalised</div>
              <div className="n">{mean(res.r.mean_personalised)}</div>
              <div className="s">n = {res.r.n_personalised}</div>
            </div>
            <div className="arm">
              <div className="k">Generic</div>
              <div className="n">{mean(res.r.mean_generic)}</div>
              <div className="s">n = {res.r.n_generic}</div>
            </div>
            <div className="arm">
              <div className="k">Difference</div>
              <div className="n">{signed(res.r.diff, digits)}</div>
              <div className="s">
                {isNum(res.r.ci_low) && isNum(res.r.ci_high)
                  ? `${levelPct(res.r.level)}: ${fixed(res.r.ci_low, digits)} to ${fixed(res.r.ci_high, digits)}`
                  : 'no interval'}
              </div>
            </div>
          </div>
          <IntervalBar r={res.r} unit={unit} digits={digits} />
          {res.r.verdict && <p className="verdict">{res.r.verdict}</p>}
        </>
      )}
    </div>
  );
}

export function ExperimentPanel({ pkey }: { pkey: string }) {
  const [simulated, setSimulated] = useState(false);
  return (
    <section className="panel experiment" aria-labelledby="exp-h">
      {simulated && (
        <div className="watermark" aria-hidden="true">
          <span>SIMULATED</span>
        </div>
      )}
      <div className="experiment-head">
        <h2 id="exp-h">
          Does personalisation change viewing? {simulated && <span className="sim-badge">Simulated audience</span>}
        </h2>
        <label className="toggle">
          <input type="checkbox" checked={simulated} onChange={(e) => setSimulated(e.target.checked)} />
          Simulated audience (demo)
        </label>
      </div>
      <p className="prereg">
        Personalised minus generic, {simulated ? '400 simulated sessions, never mixed with real data' : 'real sessions only'}.
        95% bootstrap interval over sessions. If the bar crosses the white zero line, we cannot tell the versions apart.
      </p>
      {METRICS.map((m) => (
        <ReadoutBlock key={`${m.metric}-${simulated}`} pkey={pkey} simulated={simulated} {...m} />
      ))}
    </section>
  );
}
