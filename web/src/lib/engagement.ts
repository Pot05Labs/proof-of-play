// Engagement reporting for the experiment. The primary metric (watched minutes) is built
// from these heartbeats, so the rules here are the measurement:
//   - "heartbeat" every 15 s, only while document.visibilityState === "visible";
//   - "visibility_hidden" / "visibility_visible" on change, and the heartbeat clock restarts
//     on return (no catch-up burst);
//   - taps and mode changes on demand;
//   - "leave" on pagehide through navigator.sendBeacon with an application/json Blob
//     (a plain string goes out as text/plain and the API rejects it).
// t_ms is always read at send time from getTms(), never captured at start.

import type { EngagementKind } from './api';

export const HEARTBEAT_MS = 15_000;
export const ENGAGE_URL = '/api/engage';

export interface EngagePayload {
  session_id: string;
  t_ms: number;
  kind: EngagementKind;
}

export interface EngagementDeps {
  sessionId: string;
  /** Current match clock in ms (from the latest /api/state). */
  getTms: () => number;
  /** Ordinary POST for everything except "leave". Rejections are reported to onError. */
  post: (payload: EngagePayload) => Promise<unknown>;
  /** navigator.sendBeacon, injectable for tests. */
  sendBeacon?: (url: string, data: Blob) => boolean;
  doc?: Document;
  win?: Window;
  intervalMs?: number;
  onError?: (err: unknown, payload: EngagePayload) => void;
}

export interface Engagement {
  start(): void;
  stop(): void;
  track(kind: Exclude<EngagementKind, 'heartbeat' | 'leave' | 'visibility_hidden' | 'visibility_visible'>): void;
  readonly running: boolean;
}

export function createEngagement(deps: EngagementDeps): Engagement {
  const doc = deps.doc ?? document;
  const win = deps.win ?? window;
  const intervalMs = deps.intervalMs ?? HEARTBEAT_MS;
  const beacon =
    deps.sendBeacon ??
    (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function'
      ? navigator.sendBeacon.bind(navigator)
      : undefined);

  let timer: ReturnType<typeof setInterval> | null = null;
  let running = false;
  let left = false;

  const payload = (kind: EngagementKind): EngagePayload => ({
    session_id: deps.sessionId,
    t_ms: Math.max(0, Math.round(deps.getTms())),
    kind,
  });

  const send = (kind: EngagementKind) => {
    const p = payload(kind);
    deps.post(p).catch((err: unknown) => deps.onError?.(err, p));
  };

  const startHeartbeat = () => {
    if (timer !== null) return;
    timer = setInterval(() => {
      // Belt and braces: a timer that fires while hidden never counts as watching.
      if (doc.visibilityState === 'visible') send('heartbeat');
    }, intervalMs);
  };

  const stopHeartbeat = () => {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };

  const onVisibility = () => {
    if (doc.visibilityState === 'visible') {
      send('visibility_visible');
      startHeartbeat();
    } else {
      stopHeartbeat();
      send('visibility_hidden');
    }
  };

  const onPageHide = () => {
    if (left) return;
    left = true;
    stopHeartbeat();
    const p = payload('leave');
    const blob = new Blob([JSON.stringify(p)], { type: 'application/json' });
    const queued = beacon ? beacon(ENGAGE_URL, blob) : false;
    if (!queued) {
      // Fallback when sendBeacon is missing or refuses: a keepalive fetch survives unload.
      fetch(ENGAGE_URL, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(p),
        keepalive: true,
      }).catch(() => undefined);
    }
  };

  const onPageShow = (e: Event) => {
    // Restored from the back/forward cache: the viewer is back.
    if ((e as PageTransitionEvent).persisted) {
      left = false;
      if (doc.visibilityState === 'visible') startHeartbeat();
    }
  };

  return {
    get running() {
      return running;
    },
    start() {
      if (running) return;
      running = true;
      left = false;
      doc.addEventListener('visibilitychange', onVisibility);
      win.addEventListener('pagehide', onPageHide);
      win.addEventListener('pageshow', onPageShow);
      if (doc.visibilityState === 'visible') startHeartbeat();
    },
    stop() {
      if (!running) return;
      running = false;
      stopHeartbeat();
      doc.removeEventListener('visibilitychange', onVisibility);
      win.removeEventListener('pagehide', onPageHide);
      win.removeEventListener('pageshow', onPageShow);
    },
    track(kind) {
      send(kind);
    },
  };
}
