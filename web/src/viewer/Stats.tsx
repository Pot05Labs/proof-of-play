import type { Audience, MatchInfo, MatchState, TeamStats } from '../lib/api';
import { legibleOn } from '../lib/colour';
import { num, pct } from '../lib/format';
import { fill, type Labels } from '../lib/i18n';

const GROUND = '#151c2e';

interface Row {
  label: string;
  home: number;
  away: number;
  fmt: (v: number, s: TeamStats) => string;
}

export function StatStrip({ info, state, mode, t }: { info: MatchInfo; state: MatchState; mode: Audience; t: Labels }) {
  const h = state.teams[info.home.team_id];
  const a = state.teams[info.away.team_id];
  if (!h || !a) return null;
  const homeTint = legibleOn(info.home.colour, GROUND, 3);
  const awayTint = legibleOn(info.away.colour, GROUND, 3);

  const all: (Row & { casual: boolean })[] = [
    { label: t.possession, home: h.possession_pct, away: a.possession_pct, fmt: (v) => `${Math.round(v)}%`, casual: true },
    { label: t.xg, home: h.xg, away: a.xg, fmt: (v) => num(v, 2), casual: false },
    { label: `${t.shots} (${t.onTarget})`, home: h.shots, away: a.shots, fmt: (v, s) => `${v} (${s.shots_on_target})`, casual: true },
    { label: t.passAcc, home: h.pass_accuracy, away: a.pass_accuracy, fmt: (v) => pct(v), casual: false },
  ];
  const rows = mode === 'analyst' ? all : all.filter((r) => r.casual);

  return (
    <section className="panel" aria-label="Team stats">
      <div className="stats">
        {rows.map((r) => {
          const total = r.home + r.away;
          const hp = total > 0 ? r.home / total : 0.5;
          return (
            <div className="stat-row" key={r.label}>
              <span className="v">{r.fmt(r.home, h)}</span>
              <div className="stat-mid">
                <div className="stat-label">{r.label}</div>
                <div className="stat-bars" aria-hidden="true">
                  <span style={{ flexGrow: hp, background: homeTint }} />
                  <span style={{ flexGrow: 1 - hp, background: awayTint }} />
                </div>
              </div>
              <span className="v r">{r.fmt(r.away, a)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function AnalystPanel({ info, state, t }: { info: MatchInfo; state: MatchState; t: Labels }) {
  const h = state.teams[info.home.team_id];
  const a = state.teams[info.away.team_id];
  if (!h || !a) return null;
  const names = new Map([info.home, info.away].flatMap((tm) => tm.squad.map((p) => [p.player_id, `${p.name}`] as const)));
  const players = Object.values(state.players);
  const threat = players.reduce((best, p) => (p.xg > (best?.xg ?? 0) ? p : best), undefined as (typeof players)[number] | undefined);
  const fastest = players.reduce((best, p) => (p.top_speed_kmh > (best?.top_speed_kmh ?? 0) ? p : best), undefined as (typeof players)[number] | undefined);
  const pair = (x: string, y: string) => `${x} / ${y}`;

  const metrics: { k: string; n: string; s?: string }[] = [
    { k: t.territory, n: pair(`${Math.round(h.territory_pct)}%`, `${Math.round(a.territory_pct)}%`) },
    { k: t.pressing, n: pair(num(h.pressing_intensity, 2), num(a.pressing_intensity, 2)), s: t.perOppPass },
    { k: t.entries, n: pair(String(h.final_third_entries), String(a.final_third_entries)) },
    { k: t.passes, n: pair(String(h.passes_completed), String(a.passes_completed)), s: fill(t.ofTotal, { a: h.passes, b: a.passes }) },
    { k: t.cards, n: pair(`${h.yellow_cards + h.red_cards}`, `${a.yellow_cards + a.red_cards}`) },
    { k: t.fastestBall, n: num(state.max_ball_speed_kmh, 1), s: 'km/h' },
    { k: t.topThreat, n: threat && threat.xg > 0 ? num(threat.xg, 2) : '–', s: threat && threat.xg > 0 ? `xG, ${names.get(threat.player_id) ?? ''}` : undefined },
    { k: t.topSpeed, n: fastest && fastest.top_speed_kmh > 0 ? num(fastest.top_speed_kmh, 1) : '–', s: fastest && fastest.top_speed_kmh > 0 ? `km/h, ${names.get(fastest.player_id) ?? ''}` : undefined },
  ];

  return (
    <section className="panel" aria-labelledby="an-h">
      <h2 id="an-h">
        {info.home.short} / {info.away.short}
      </h2>
      <div className="analyst-grid">
        {metrics.map((m) => (
          <div className="metric" key={m.k}>
            <div className="k">{m.k}</div>
            <div className="n">
              {m.n}
              {m.s && <small>{m.s}</small>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
