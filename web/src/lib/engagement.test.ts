import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createEngagement, ENGAGE_URL, HEARTBEAT_MS, type EngagePayload } from './engagement';

let visibility: DocumentVisibilityState = 'visible';

function setVisibility(v: DocumentVisibilityState) {
  visibility = v;
  document.dispatchEvent(new Event('visibilitychange'));
}

function setup(over: Partial<Parameters<typeof createEngagement>[0]> = {}) {
  const sent: EngagePayload[] = [];
  const post = vi.fn((p: EngagePayload) => {
    sent.push(p);
    return Promise.resolve({ ok: true });
  });
  const beacon = vi.fn((_url: string, _data: Blob) => true);
  let tms = 0;
  const eng = createEngagement({
    sessionId: 'S1',
    getTms: () => tms,
    post,
    sendBeacon: beacon,
    ...over,
  });
  return { eng, post, beacon, sent, setTms: (v: number) => (tms = v) };
}

function readBlob(b: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsText(b);
  });
}

const kinds = (sent: EngagePayload[]) => sent.map((p) => p.kind);

beforeEach(() => {
  vi.useFakeTimers();
  visibility = 'visible';
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('heartbeats', () => {
  it('sends one heartbeat every 15 s while visible', () => {
    const { eng, sent } = setup();
    eng.start();
    vi.advanceTimersByTime(HEARTBEAT_MS - 1);
    expect(sent).toHaveLength(0);
    vi.advanceTimersByTime(1);
    vi.advanceTimersByTime(HEARTBEAT_MS * 2);
    expect(kinds(sent)).toEqual(['heartbeat', 'heartbeat', 'heartbeat']);
    eng.stop();
  });

  it('stops heartbeats while hidden and restarts the clock on return', () => {
    const { eng, sent } = setup();
    eng.start();
    vi.advanceTimersByTime(HEARTBEAT_MS);
    setVisibility('hidden');
    vi.advanceTimersByTime(HEARTBEAT_MS * 10);
    expect(kinds(sent)).toEqual(['heartbeat', 'visibility_hidden']);

    setVisibility('visible');
    expect(kinds(sent)).toEqual(['heartbeat', 'visibility_hidden', 'visibility_visible']);
    // No catch-up burst: the next heartbeat comes a full interval after returning.
    vi.advanceTimersByTime(HEARTBEAT_MS - 1);
    expect(kinds(sent).filter((k) => k === 'heartbeat')).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(kinds(sent).filter((k) => k === 'heartbeat')).toHaveLength(2);
    eng.stop();
  });

  it('does not start heartbeats if the page starts hidden', () => {
    visibility = 'hidden';
    const { eng, sent } = setup();
    eng.start();
    vi.advanceTimersByTime(HEARTBEAT_MS * 4);
    expect(sent).toHaveLength(0);
    eng.stop();
  });

  it('reads t_ms at send time, not at start', () => {
    const { eng, sent, setTms } = setup();
    setTms(1000);
    eng.start();
    setTms(61_000);
    vi.advanceTimersByTime(HEARTBEAT_MS);
    setTms(122_500);
    vi.advanceTimersByTime(HEARTBEAT_MS);
    expect(sent.map((p) => p.t_ms)).toEqual([61_000, 122_500]);
    expect(sent.every((p) => p.session_id === 'S1')).toBe(true);
    eng.stop();
  });

  it('is idempotent: double start does not double heartbeats (React StrictMode)', () => {
    const { eng, sent } = setup();
    eng.start();
    eng.start();
    vi.advanceTimersByTime(HEARTBEAT_MS);
    expect(sent).toHaveLength(1);
    eng.stop();
    eng.stop();
    vi.advanceTimersByTime(HEARTBEAT_MS * 3);
    expect(sent).toHaveLength(1);
  });

  it('stop removes listeners: visibility changes after stop send nothing', () => {
    const { eng, sent } = setup();
    eng.start();
    eng.stop();
    setVisibility('hidden');
    setVisibility('visible');
    window.dispatchEvent(new Event('pagehide'));
    vi.advanceTimersByTime(HEARTBEAT_MS * 2);
    expect(sent).toHaveLength(0);
  });
});

describe('taps', () => {
  it('sends the exact kinds for why, show me and mode change', () => {
    const { eng, sent, setTms } = setup();
    eng.start();
    setTms(5000);
    eng.track('why_tap');
    eng.track('show_me_tap');
    eng.track('mode_change');
    expect(sent).toEqual([
      { session_id: 'S1', t_ms: 5000, kind: 'why_tap' },
      { session_id: 'S1', t_ms: 5000, kind: 'show_me_tap' },
      { session_id: 'S1', t_ms: 5000, kind: 'mode_change' },
    ]);
    eng.stop();
  });

  it('reports post failures to onError instead of throwing', async () => {
    const onError = vi.fn();
    const { eng } = setup({ post: () => Promise.reject(new Error('down')), onError });
    eng.start();
    eng.track('why_tap');
    await Promise.resolve();
    await Promise.resolve();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0]?.[1]).toMatchObject({ kind: 'why_tap' });
    eng.stop();
  });
});

describe('leave', () => {
  it('sends leave on pagehide through sendBeacon as an application/json Blob', async () => {
    const { eng, beacon, post, setTms } = setup();
    eng.start();
    setTms(42_000);
    window.dispatchEvent(new Event('pagehide'));
    expect(beacon).toHaveBeenCalledTimes(1);
    const [url, data] = beacon.mock.calls[0]!;
    expect(url).toBe(ENGAGE_URL);
    expect(data).toBeInstanceOf(Blob);
    expect(data.type).toBe('application/json');
    vi.useRealTimers(); // FileReader completes on a real task
    const body = JSON.parse(await readBlob(data)) as EngagePayload;
    expect(body).toEqual({ session_id: 'S1', t_ms: 42_000, kind: 'leave' });
    // leave never goes through the ordinary POST
    expect(post).not.toHaveBeenCalled();
    eng.stop();
  });

  it('sends leave only once and stops heartbeats after pagehide', () => {
    const { eng, beacon, sent } = setup();
    eng.start();
    window.dispatchEvent(new Event('pagehide'));
    window.dispatchEvent(new Event('pagehide'));
    vi.advanceTimersByTime(HEARTBEAT_MS * 3);
    expect(beacon).toHaveBeenCalledTimes(1);
    expect(sent).toHaveLength(0);
    eng.stop();
  });

  it('falls back to a keepalive fetch when sendBeacon refuses', () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response('{}')));
    vi.stubGlobal('fetch', fetchMock);
    const { eng } = setup({ sendBeacon: () => false });
    eng.start();
    window.dispatchEvent(new Event('pagehide'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(ENGAGE_URL);
    expect(init.keepalive).toBe(true);
    expect((init.headers as Record<string, string>)['content-type']).toBe('application/json');
    expect(JSON.parse(init.body as string)).toMatchObject({ kind: 'leave' });
    eng.stop();
    vi.unstubAllGlobals();
  });
});
