import type { Audience, Clock, MatchInfo, MatchState } from '../lib/api';
import { textOn } from '../lib/colour';
import { clockText } from '../lib/format';
import type { Labels } from '../lib/i18n';

interface Props {
  info: MatchInfo;
  state: MatchState | null;
  clock: Clock | null;
  phase: 'pre' | 'live' | 'half' | 'full';
  mode: Audience;
  onMode: (m: Audience) => void;
  t: Labels;
}

export function Scoreboard({ info, state, clock, phase, mode, onMode, t }: Props) {
  const hs = state?.score[info.home.team_id] ?? 0;
  const as = state?.score[info.away.team_id] ?? 0;
  const period =
    phase === 'pre' ? t.preMatch : phase === 'half' ? t.halfTime : phase === 'full' ? t.fullTime
      : (state?.period ?? 1) === 1 ? t.firstHalf : t.secondHalf;
  const added = clock && clock.added > 0 ? ` +${clock.added}` : '';

  return (
    <header className="bug">
      <div className="bug-inner">
        <div
          className="score"
          role="group"
          aria-label={`${info.home.name} ${hs}, ${info.away.name} ${as}`}
        >
          <span className="stripe" style={{ background: info.home.colour }} aria-hidden="true" />
          <span className="side" aria-hidden="true">{info.home.short}</span>
          <span className="goals" aria-hidden="true">
            <span>{hs}</span>
            <span style={{ opacity: 0.4 }}>:</span>
            <span>{as}</span>
          </span>
          <span className="side" aria-hidden="true">{info.away.short}</span>
          <span className="stripe" style={{ background: info.away.colour }} aria-hidden="true" />
        </div>
        <div className="bug-meta">
          <span className="clock" aria-label={`Match clock ${clockText(clock, state?.minute ?? 0)}`}>
            {clockText(clock, state?.minute ?? 0)}
            {added && <small style={{ fontSize: '0.6em' }}>{added}</small>}
          </span>
          <span className="period">{period}</span>
        </div>
        <div className="bug-tools">
          <div className="seg" role="group" aria-label={t.mode}>
            {(['fan', 'analyst'] as const).map((m) => (
              <button key={m} type="button" aria-pressed={mode === m} onClick={() => mode !== m && onMode(m)}>
                {m === 'fan' ? t.casual : t.analyst}
              </button>
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}

/** Small swatch with legible text, used for team keys. */
export function TeamKey({ colour, label }: { colour: string; label: string }) {
  return (
    <span style={{ background: colour, color: textOn(colour), padding: '0 6px', borderRadius: 2, fontWeight: 700 }}>
      {label}
    </span>
  );
}
