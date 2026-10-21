import { useMemo, useState } from 'react';
import type { MatchInfo, ProducerRow } from '../lib/api';

type Filter = 'all' | 'rejected' | 'retracted' | 'personalised';

export const isRejectedRewrite = (r: ProducerRow) => r.notes.includes('rejected');
const isPersonalised = (r: ProducerRow) => r.club !== null || r.player !== null;

const FILTERS: { id: Filter; label: string; test: (r: ProducerRow) => boolean }[] = [
  { id: 'all', label: 'All', test: () => true },
  { id: 'rejected', label: 'Rewrites rejected', test: isRejectedRewrite },
  { id: 'retracted', label: 'Retracted', test: (r) => r.retracted },
  { id: 'personalised', label: 'Personalised', test: isPersonalised },
];

function nameOf(id: string, info: MatchInfo | null): string {
  if (!info) return id;
  for (const t of [info.home, info.away]) {
    if (t.team_id === id) return t.short;
    const p = t.squad.find((x) => x.player_id === id);
    if (p) return p.name;
  }
  return id;
}

export function InsightLog({ rows, info }: { rows: ProducerRow[]; info: MatchInfo | null }) {
  const [filter, setFilter] = useState<Filter>('all');
  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f.id, rows.filter(f.test).length])) as Record<Filter, number>,
    [rows],
  );
  const shown = useMemo(() => {
    const f = FILTERS.find((x) => x.id === filter)!;
    // rejected rewrites first, they are the safety story; then newest first
    return rows
      .filter(f.test)
      .slice()
      .reverse()
      .sort((a, b) => Number(isRejectedRewrite(b)) - Number(isRejectedRewrite(a)));
  }, [rows, filter]);

  return (
    <section className="panel" aria-labelledby="log-h" style={{ minWidth: 0 }}>
      <h2 id="log-h">Every insight written</h2>
      <div className="log-filter seg" role="group" aria-label="Filter insights" style={{ border: 0 }}>
        {FILTERS.map((f) => (
          <button key={f.id} type="button" className="btn btn-small" aria-pressed={filter === f.id}
            style={filter === f.id ? { background: 'var(--chalk)', color: 'var(--ink)' } : undefined}
            onClick={() => setFilter(f.id)}>
            {f.label} ({counts[f.id]})
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="empty">
          {rows.length === 0 ? 'No insights yet. Start the broadcast and they will appear here as they are written.' : 'Nothing matches this filter.'}
        </p>
      ) : (
        <div className="table-wrap table-scroll">
          <table className="log">
            <thead>
              <tr>
                <th scope="col">Min</th>
                <th scope="col">Insight</th>
                <th scope="col">Audience</th>
                <th scope="col">Lang</th>
                <th scope="col">Club / player</th>
                <th scope="col">Checks</th>
                <th scope="col">Latency</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const rej = isRejectedRewrite(r);
                return (
                  <tr key={r.insight_id} className={[rej ? 'rejected' : '', r.retracted ? 'pulled' : ''].join(' ')}>
                    <td className="min">{r.minute}&rsquo;</td>
                    <td className="text">
                      {r.text}
                      {r.notes && r.notes !== 'verified' && (
                        <div className={rej ? 'notes-bad' : 'verdict-note'} style={{ fontSize: 13, marginTop: 4 }}>
                          {r.notes}
                        </div>
                      )}
                    </td>
                    <td>{isPersonalised(r) || r.audience === 'analyst' ? r.audience : 'generic'}</td>
                    <td>{r.language}</td>
                    <td>{[r.club, r.player].filter((x): x is string => !!x).map((x) => nameOf(x, info)).join(' / ') || '–'}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {r.verified ? <span className="tag tag-ok">Verified</span> : <span className="tag tag-muted">Unverified</span>}
                        {rej && <span className="tag tag-bad">Rewrite rejected</span>}
                        {r.retracted && <span className="tag tag-var">Retracted</span>}
                      </div>
                    </td>
                    <td>{r.latency_ms.toFixed(1)} ms</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
