import { useCallback, useMemo, useRef, useState } from 'react';
import { api, type Audience, type EvidenceResponse, type MatchEvent } from '../lib/api';
import type { DisplayCard } from '../lib/feed';
import { fill, labels } from '../lib/i18n';
import { Wordmark } from '../ui/Wordmark';
import { ControlChaos, Momentum } from './Gauges';
import { InsightFeed } from './InsightFeed';
import { Pitch } from './Pitch';
import { Scoreboard } from './Scoreboard';
import type { ViewerSession } from './session';
import { AnalystPanel, StatStrip } from './Stats';
import { useEngagement } from './useEngagement';
import { useLiveMatch } from './useLiveMatch';
import { WhyDialog } from './WhyDialog';

interface Props {
  session: ViewerSession;
  onSessionLost: () => void;
  onUpdate: (s: ViewerSession) => void;
}

interface Highlight {
  cardId: string;
  text: string;
  eventIds: string[];
}

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export function LiveScreen({ session, onSessionLost, onUpdate }: Props) {
  const t = labels(session.language);
  const live = useLiveMatch(session.session_id, onSessionLost);
  const engagement = useEngagement(session.session_id, live.tmsRef, onSessionLost);
  const { info, state, events, eventById, cards, finished, offline, feedReady } = live;

  const evidenceCache = useRef(new Map<string, Promise<EvidenceResponse>>());
  const getEvidence = useCallback((factIds: string[]) => {
    const key = factIds.join(',');
    let p = evidenceCache.current.get(key);
    if (!p) {
      p = api.evidence(factIds);
      p.catch(() => evidenceCache.current.delete(key));
      evidenceCache.current.set(key, p);
    }
    return p;
  }, []);

  // WHY? panel
  const [whyCard, setWhyCard] = useState<DisplayCard | null>(null);
  const [whyEvidence, setWhyEvidence] = useState<EvidenceResponse | null>(null);
  const [whyError, setWhyError] = useState<string | null>(null);

  const openWhy = useCallback(
    (c: DisplayCard) => {
      engagement.current?.track('why_tap');
      setWhyCard(c);
      setWhyEvidence(null);
      setWhyError(null);
      getEvidence(c.fact_ids)
        .then(setWhyEvidence)
        .catch(() => setWhyError(t.evidenceError));
    },
    [engagement, getEvidence, t],
  );

  // SHOW ME on the pitch
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const pitchRef = useRef<HTMLDivElement>(null);
  const showMe = useCallback(
    (c: DisplayCard, force = false) => {
      if (!force && highlight?.cardId === c.insight_id) {
        setHighlight(null);
        return;
      }
      engagement.current?.track('show_me_tap');
      getEvidence(c.fact_ids)
        .then((ev) => {
          const ids = Array.from(new Set(c.fact_ids.flatMap((id) => ev.evidence[id] ?? [])));
          setHighlight({ cardId: c.insight_id, text: c.text, eventIds: ids });
          const el = pitchRef.current;
          if (el && el.getBoundingClientRect().top < 0) {
            el.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' });
          }
        })
        .catch(() => setHighlight(null));
    },
    [engagement, getEvidence, highlight],
  );

  const highlighted = useMemo(
    () => (highlight ? highlight.eventIds.map((id) => eventById.get(id)).filter((e): e is MatchEvent => !!e) : []),
    // events in deps: eventById is a mutable map that grows with events
    [highlight, eventById, events],
  );
  const drawable = highlighted.filter((e) => e.x !== null && e.y !== null).length;

  const setMode = (mode: Audience) => {
    engagement.current?.track('mode_change');
    onUpdate({ ...session, mode });
  };

  const last = events.length ? events[events.length - 1]! : null;
  const phase: 'pre' | 'live' | 'half' | 'full' =
    finished || last?.type === 'full_time' ? 'full'
      : last?.type === 'half_time' ? 'half'
        : !state || state.seq === 0 ? 'pre' : 'live';

  if (!info) {
    return (
      <main className="join">
        <div className="join-inner">
          <Wordmark />
          <p className="fixture" style={{ marginTop: 24 }} role="status">
            {offline ? t.connectionLost : t.loading}
          </p>
        </div>
      </main>
    );
  }

  return (
    <div className="live">
      <Scoreboard info={info} state={state} clock={last?.clock ?? null} phase={phase} mode={session.mode} onMode={setMode} t={t} />
      {offline && (
        <p className="banner" role="alert">
          {t.connectionLost}
        </p>
      )}
      <main className="live-grid">
        <div className="area-pitch pitch-wrap" ref={pitchRef}>
            <Pitch info={info} events={events} highlight={highlighted} />
            <div className="pitch-ends" aria-hidden="true">
              <span>
                <i style={{ background: info.home.colour }} />
                {info.home.name}
              </span>
              <span>
                {info.away.name}
                <i style={{ background: info.away.colour }} />
              </span>
            </div>
            {highlight && (
              <div className="showme-bar" role="status">
                <p>
                  {t.showing} <q>{highlight.text}</q>
                  {highlighted.length > 0 && (
                    <>
                      {' '}
                      ({fill(t.onPitch, { n: drawable, m: highlight.eventIds.length })})
                    </>
                  )}
                </p>
                <button type="button" className="btn btn-small" onClick={() => setHighlight(null)}>
                  {t.clear}
                </button>
              </div>
            )}
        </div>

        <div className="area-stats col-main">
          {state && (
            <div className="readouts">
              <Momentum info={info} value={state.momentum} t={t} />
              <ControlChaos value={state.control_chaos} t={t} />
            </div>
          )}
          {state && <StatStrip info={info} state={state} mode={session.mode} t={t} />}
          {state && session.mode === 'analyst' && <AnalystPanel info={info} state={state} t={t} />}
        </div>

        <InsightFeed
          cards={cards}
          showingId={highlight?.cardId ?? null}
          onWhy={openWhy}
          onShowMe={(c) => showMe(c)}
          t={t}
          started={phase !== 'pre'}
          ready={feedReady}
        />
      </main>

      <WhyDialog
        card={whyCard}
        evidence={whyEvidence}
        error={whyError}
        info={info}
        eventById={eventById}
        onClose={() => setWhyCard(null)}
        onShowMe={(c) => showMe(c, true)}
        t={t}
      />
    </div>
  );
}
