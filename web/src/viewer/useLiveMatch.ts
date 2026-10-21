import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, type MatchEvent, type MatchInfo, type MatchState } from '../lib/api';
import { LEAVE_MS, mergeFeed, type DisplayCard } from '../lib/feed';

export const POLL_MS = 2000;
const MIN_GAP_MS = 400;          // throttle for SSE-triggered refreshes
const FIRST_LOAD_LIMIT = 10000;  // SHOW ME needs early-match events too
const MAX_EVENTS = 12000;

export interface LiveMatch {
  info: MatchInfo | null;
  state: MatchState | null;
  events: MatchEvent[];
  eventById: Map<string, MatchEvent>;
  cards: DisplayCard[];
  finished: boolean;
  offline: boolean;
  /** False until the first feed snapshot has rendered (keeps aria-live quiet for the backlog). */
  feedReady: boolean;
  /** Latest match clock in ms, readable at any time (for engagement). */
  tmsRef: React.MutableRefObject<number>;
}

export function useLiveMatch(sessionId: string, onSessionLost: () => void): LiveMatch {
  const [info, setInfo] = useState<MatchInfo | null>(null);
  const [state, setState] = useState<MatchState | null>(null);
  const [events, setEvents] = useState<MatchEvent[]>([]);
  const [cards, setCards] = useState<DisplayCard[]>([]);
  const [finished, setFinished] = useState(false);
  const [offline, setOffline] = useState(false);
  const [feedReady, setFeedReady] = useState(false);

  const since = useRef(0);
  const matchId = useRef<string | null>(null);
  const eventsRef = useRef<MatchEvent[]>([]);
  const byId = useRef(new Map<string, MatchEvent>());
  const cardsRef = useRef<DisplayCard[]>([]);
  const firstFeed = useRef(true);
  const tmsRef = useRef(0);
  const inFlight = useRef(false);
  const lastRun = useRef(0);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lostRef = useRef(onSessionLost);
  lostRef.current = onSessionLost;

  const reset = () => {
    since.current = 0;
    eventsRef.current = [];
    byId.current = new Map();
    firstFeed.current = true;
    setFeedReady(false);
    setFinished(false);
  };

  // Refresher A: state + events. Cheap, keeps the clock (and heartbeat t_ms) moving.
  const refreshMatch = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    lastRun.current = Date.now();
    try {
      const [st, ev] = await Promise.all([
        api.state(),
        api.events(since.current, since.current === 0 ? FIRST_LOAD_LIMIT : 2000),
      ]);

      // A broadcast restart (new match, or the clock went backwards) resets everything,
      // and the old feed leaves without the VAR animation.
      let restarted = false;
      if (matchId.current !== null && matchId.current !== st.match_id) restarted = true;
      if (ev.seq < since.current) restarted = true;
      if (restarted) {
        reset();
        const again = await api.events(0, FIRST_LOAD_LIMIT);
        ev.events = again.events;
        ev.seq = again.seq;
        api.match().then(setInfo).catch(() => undefined);
      }
      matchId.current = st.match_id;

      if (ev.events.length) {
        const merged = eventsRef.current.concat(ev.events.filter((e) => !byId.current.has(e.event_id)));
        const trimmed = merged.length > MAX_EVENTS ? merged.slice(merged.length - MAX_EVENTS) : merged;
        eventsRef.current = trimmed;
        for (const e of ev.events) byId.current.set(e.event_id, e);
        setEvents(trimmed);
      }
      since.current = ev.seq;
      tmsRef.current = st.t_ms;
      setState(st);
      if (ev.events.some((e) => e.type === 'full_time')) setFinished(true);
      setOffline(false);
    } catch {
      setOffline(true);
    } finally {
      inFlight.current = false;
    }
  }, []);

  // Refresher B: the insight feed. Can be slow (insights are written on demand), so it never
  // blocks the clock. Owns the "session lost" path.
  const feedInFlight = useRef(false);
  const refreshFeed = useCallback(async () => {
    if (feedInFlight.current) return;
    feedInFlight.current = true;
    try {
      const feed = await api.feed(sessionId);
      const next = mergeFeed(cardsRef.current, feed.insights, Date.now(), firstFeed.current);
      firstFeed.current = false;
      cardsRef.current = next;
      setCards(next);
      setFeedReady(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) lostRef.current();
    } finally {
      feedInFlight.current = false;
    }
  }, [sessionId]);

  const refresh = useCallback(async () => {
    await Promise.all([refreshMatch(), refreshFeed()]);
  }, [refreshMatch, refreshFeed]);

  const schedule = (fn: () => Promise<void>, slot: React.MutableRefObject<ReturnType<typeof setTimeout> | null>) => {
    if (slot.current) return;
    const wait = Math.max(0, MIN_GAP_MS - (Date.now() - lastRun.current));
    slot.current = setTimeout(() => {
      slot.current = null;
      void fn();
    }, wait);
  };
  const pendingFeed = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestMatch = useCallback(() => schedule(refreshMatch, pending), [refreshMatch]);
  const requestBoth = useCallback(() => {
    schedule(refreshMatch, pending);
    schedule(refreshFeed, pendingFeed);
  }, [refreshMatch, refreshFeed]);

  // Match info once.
  useEffect(() => {
    api.match().then(setInfo).catch(() => setOffline(true));
  }, []);

  // Poll every 2 s regardless of SSE, so a dropped stream never freezes the screen.
  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), POLL_MS);
    return () => {
      clearInterval(id);
      if (pending.current) clearTimeout(pending.current);
      if (pendingFeed.current) clearTimeout(pendingFeed.current);
      pending.current = null;
      pendingFeed.current = null;
    };
  }, [refresh]);

  // Leaving cards need a clock of their own to expire when nothing else changes.
  useEffect(() => {
    if (!cards.some((c) => c.status === 'leaving')) return;
    const id = setTimeout(() => {
      const next = mergeFeed(cardsRef.current, cardsRef.current.filter((c) => c.status === 'live'), Date.now(), false);
      cardsRef.current = next;
      setCards(next);
    }, LEAVE_MS + 50);
    return () => clearTimeout(id);
  }, [cards]);

  // Server-sent events: refresh immediately on tick, moment, retraction, finished.
  useEffect(() => {
    if (typeof EventSource === 'undefined') return;
    const es = new EventSource('/api/stream');
    const onFinished = () => {
      setFinished(true);
      requestBoth();
    };
    es.addEventListener('tick', requestMatch);
    es.addEventListener('moment', requestBoth);
    es.addEventListener('retraction', requestBoth);
    es.addEventListener('finished', onFinished);
    return () => es.close();
  }, [requestMatch, requestBoth]);

  return { info, state, events, eventById: byId.current, cards, finished, offline, feedReady, tmsRef };
}
