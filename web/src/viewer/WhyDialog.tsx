import { useEffect, useRef } from 'react';
import type { EvidenceResponse, MatchEvent, MatchInfo } from '../lib/api';
import type { DisplayCard } from '../lib/feed';
import { factValue, humanKind, subjectName } from '../lib/format';
import { fill, type Labels } from '../lib/i18n';

interface Props {
  card: DisplayCard | null;
  evidence: EvidenceResponse | null;
  error: string | null;
  info: MatchInfo | null;
  eventById: Map<string, MatchEvent>;
  onClose: () => void;
  onShowMe: (c: DisplayCard) => void;
  t: Labels;
}

export function WhyDialog({ card, evidence, error, info, eventById, onClose, onShowMe, t }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (card && !d.open) {
      if (typeof d.showModal === 'function') d.showModal();
      else d.setAttribute('open', '');
    } else if (!card && d.open) {
      if (typeof d.close === 'function') d.close();
      else d.removeAttribute('open');
    }
  }, [card]);

  const facts = card && evidence ? card.fact_ids.map((id) => evidence.facts[id]).filter((f) => f !== undefined) : [];

  return (
    <dialog
      ref={ref}
      className="why"
      aria-labelledby="why-h"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose(); // backdrop click
      }}
    >
      {card && (
        <>
          <div className="why-head">
            <h2 id="why-h">{t.evidenceTitle}</h2>
            <button type="button" className="btn btn-small" onClick={onClose} autoFocus>
              {t.close}
            </button>
          </div>
          <div className="why-body">
            <blockquote className="why-quote">{card.text}</blockquote>
            <p className="why-intro">{t.evidenceIntro}</p>
            {error && <p className="form-error" role="alert">{error}</p>}
            {!evidence && !error && <p className="why-intro">{t.loading}</p>}
            {facts.map((f) => (
              <article className="fact" key={f.fact_id}>
                <h3>{humanKind(f.kind)}</h3>
                <dl>
                  <dt>{t.fact}</dt>
                  <dd>{subjectName(f, info)}</dd>
                  <dt>{t.value}</dt>
                  <dd>{factValue(f)}</dd>
                  <dt>{t.window}</dt>
                  <dd>{f.window}</dd>
                  <dt>{t.computedBy}</dt>
                  <dd>{f.computed_by}</dd>
                  <dt>{t.events}</dt>
                  <dd>
                    <ul className="ev-list">
                      {(evidence?.evidence[f.fact_id] ?? f.evidence).map((id) => {
                        const ev = eventById.get(id);
                        return (
                          <li key={id}>
                            {ev ? `${ev.clock.minute}:${String(ev.clock.second).padStart(2, '0')} ${ev.type.replace(/_/g, ' ')} ` : ''}
                            <code>{id}</code>
                          </li>
                        );
                      })}
                    </ul>
                  </dd>
                </dl>
              </article>
            ))}
            {evidence && facts.length < card.fact_ids.length && (
              <p className="why-intro">
                {fill(t.missingFacts, { n: card.fact_ids.length - facts.length })}
              </p>
            )}
            {facts.length > 0 && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  onShowMe(card);
                  onClose();
                }}
              >
                {t.showMe}
              </button>
            )}
          </div>
        </>
      )}
    </dialog>
  );
}
