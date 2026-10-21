import { useEffect, useState } from 'react';
import type { DisplayCard } from '../lib/feed';
import { humanKind } from '../lib/format';
import type { Labels } from '../lib/i18n';

interface Props {
  cards: DisplayCard[];
  showingId: string | null;
  onWhy: (c: DisplayCard) => void;
  onShowMe: (c: DisplayCard) => void;
  t: Labels;
  started: boolean;
  /** True once the first snapshot has rendered; the live region stays silent for the backlog. */
  ready: boolean;
}

export function InsightFeed({ cards, showingId, onWhy, onShowMe, t, started, ready }: Props) {
  const [announce, setAnnounce] = useState(false);
  useEffect(() => {
    if (!ready) {
      setAnnounce(false);
      return;
    }
    const id = setTimeout(() => setAnnounce(true), 1000);
    return () => clearTimeout(id);
  }, [ready]);
  const newestLive = cards.find((c) => c.status === 'live');
  return (
    <section className="area-feed col-feed" aria-labelledby="feed-h">
      <div className="feed-head">
        <h2 id="feed-h">{t.insights}</h2>
        {started && (
          <span className="on-air">
            <i aria-hidden="true" />
            {t.live}
          </span>
        )}
      </div>
      {cards.length === 0 ? (
        <p className="empty">{started ? t.noInsights : t.waiting}</p>
      ) : null}
      {/* polite live region: screen readers hear each new lower-third once */}
      <ol className="feed" aria-live={announce ? 'polite' : 'off'} aria-relevant="additions text">
        {cards.map((c) => {
          const cls = [
            'card',
            c === newestLive ? 'newest' : '',
            c.fresh ? 'fresh' : '',
            c.status === 'leaving' ? 'leaving' : '',
            showingId === c.insight_id ? 'showing' : '',
          ]
            .filter(Boolean)
            .join(' ');
          const leaving = c.status === 'leaving';
          return (
            <li key={c.insight_id} className={cls}>
              <div className="card-min" aria-label={`Minute ${c.minute}`}>
                {c.minute}&rsquo;
              </div>
              <div className="card-body">
                <p className="card-kind">{humanKind(c.kind)}</p>
                <p className="card-text">{c.text}</p>
                {leaving ? (
                  <p className="var-note" role="status">
                    {t.updatedVar}
                  </p>
                ) : (
                  <div className="card-actions">
                    <button type="button" className="btn btn-small" onClick={() => onWhy(c)}>
                      {t.why}
                    </button>
                    <button
                      type="button"
                      className="btn btn-small btn-ghost"
                      aria-pressed={showingId === c.insight_id}
                      onClick={() => onShowMe(c)}
                    >
                      {t.showMe}
                    </button>
                    <span className="card-cites">
                      {c.fact_ids.length} {c.fact_ids.length === 1 ? t.factOne : t.factMany}
                    </span>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
