// Typed client for the Proof of Play API. Types mirror src/pop/schema.py and the
// response shapes in src/pop/api/app.py + broadcast.py. All calls are relative (/api),
// proxied to the Python server by Vite in dev.

export type EventType =
  | 'match_start' | 'kick_off' | 'half_time' | 'full_time'
  | 'pass' | 'carry' | 'shot' | 'tackle' | 'interception' | 'clearance' | 'foul'
  | 'pressure' | 'possession_change' | 'substitution'
  | 'var_review' | 'var_decision' | 'player_tracking';

export type Outcome = 'success' | 'fail' | 'goal' | 'saved' | 'off_target' | 'blocked' | 'won' | 'lost';

export interface Clock {
  period: 1 | 2;
  minute: number;
  second: number;
  added: number;
}

export interface MatchEvent {
  event_id: string;
  match_id: string;
  seq: number;
  clock: Clock;
  t_ms: number;
  type: EventType;
  team_id: string | null;
  player_id: string | null;
  x: number | null;
  y: number | null;
  end_x: number | null;
  end_y: number | null;
  outcome: Outcome | null;
  pressure: number | null;
  related: string[];
  meta: Record<string, unknown>;
}

export type Position = 'GK' | 'DF' | 'MF' | 'FW';

export interface Player {
  player_id: string;
  name: string;
  number: number;
  position: Position;
  starter: boolean;
}

export interface Team {
  team_id: string;
  name: string;
  short: string;
  style: 'high_press' | 'possession' | 'low_block' | 'direct';
  colour: string;
  squad: Player[];
}

export interface MatchInfo {
  match_id: string;
  seed: number;
  competition: string;
  venue: string;
  home: Team;
  away: Team;
}

export interface TeamStats {
  team_id: string;
  goals: number;
  possession_pct: number;
  territory_share: number;
  territory_pct: number;
  passes: number;
  passes_completed: number;
  pass_accuracy: number;
  shots: number;
  shots_on_target: number;
  xg: number;
  pressing_intensity: number;
  final_third_entries: number;
  yellow_cards: number;
  red_cards: number;
}

export interface PlayerStats {
  player_id: string;
  team_id: string;
  touches: number;
  passes: number;
  passes_completed: number;
  pass_difficulty_avg: number;
  shots: number;
  goals: number;
  xg: number;
  distance_m: number;
  top_speed_kmh: number;
  sprints: number;
  yellow_cards: number;
  red_card: boolean;
}

export interface MatchState {
  match_id: string;
  seq: number;
  t_ms: number;
  play_ms: number;
  period: number;
  minute: number;
  home_team_id: string;
  away_team_id: string;
  score: Record<string, number>;
  teams: Record<string, TeamStats>;
  players: Record<string, PlayerStats>;
  /** -1..1, positive favours home. */
  momentum: number;
  /** 0 controlled .. 1 chaotic. */
  control_chaos: number;
  max_ball_speed_kmh: number;
  facts_total: number;
  facts_retracted: number;
  moments_total: number;
  moments_retracted: number;
}

export type SubjectKind = 'team' | 'player' | 'match';

export interface Fact {
  fact_id: string;
  seq_at: number;
  kind: string;
  subject_kind: SubjectKind;
  subject_id: string;
  value: number | string;
  unit: string;
  window: string;
  evidence: string[];
  computed_by: string;
}

export type Audience = 'analyst' | 'fan';
export type Language = 'en' | 'zu' | 'sw' | 'es';

export type EngagementKind =
  | 'heartbeat' | 'why_tap' | 'show_me_tap' | 'replay_open' | 'mode_change'
  | 'visibility_hidden' | 'visibility_visible' | 'leave';

/** One item of GET /api/feed/{session_id}. insight_id is opaque to the viewer UI: never render it. */
export interface FeedInsight {
  insight_id: string;
  minute: number;
  t_ms: number;
  text: string;
  fact_ids: string[];
  importance: number;
  kind: string;
}

export interface FeedResponse {
  seq: number;
  t_ms: number;
  insights: FeedInsight[];
}

export interface EventsResponse {
  seq: number;
  events: MatchEvent[];
}

export interface EvidenceResponse {
  facts: Record<string, Fact>;
  evidence: Record<string, string[]>;
}

export interface ProducerRow {
  insight_id: string;
  minute: number;
  text: string;
  verified: boolean;
  notes: string;
  retracted: boolean;
  audience: Audience;
  language: string;
  club: string | null;
  player: string | null;
  latency_ms: number;
}

/** Model token accounting (src/pop/agents/llm.py Usage.as_dict). cached_input_tokens is a subset of input_tokens. */
export interface Usage {
  calls: number;
  failures: number;
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
}

/** Database writer counters (src/pop/experiment/store.py stats()). */
export interface StoreStats {
  written: number;
  failed: number;
  pending: number;
  /** Present on Cosmos-backed builds. */
  database?: string;
  container?: string;
  /** Writes dropped because the in-memory write queue was full. */
  dropped_queue_full?: number;
}

export interface ProducerView {
  /** e.g. "foundry:gpt-4.1-mini" or "stub". */
  model: string;
  llm_calls: number;
  rejected_rewrites: number;
  retracted: number;
  /** All insights written; `insights` below is capped at the latest 500. */
  total: number;
  queue_depth: number;
  /** Distinct viewer profiles being written for. */
  profiles: number;
  write_lag_ms_p50: number | null;
  write_lag_ms_p95: number | null;
  /** null when the model client keeps no usage (the stub). */
  usage: Usage | null;
  /** null when no database is configured. */
  store: StoreStats | null;
  insights: ProducerRow[];
}

export type Metric = 'watched_minutes' | 'taps_per_minute';

export interface Readout {
  simulated: boolean;
  metric: Metric;
  n_personalised: number;
  n_generic: number;
  mean_personalised: number | null;
  mean_generic: number | null;
  diff: number | null;
  ci_low: number | null;
  ci_high: number | null;
  level: number;
  verdict: string;
}

export interface SessionRequest {
  consent: true;
  mode: Audience;
  club_id: string | null;
  player_id: string | null;
  language: Language;
}

export interface StartRequest {
  seed: number;
  speed: number;
  var_overturn: boolean;
}

export interface Health {
  ok: boolean;
  running: boolean;
  finished: boolean;
  seq: number;
  model: string;
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* body was not JSON; keep the status text */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

const json = (body: unknown, headers: Record<string, string> = {}): RequestInit => ({
  method: 'POST',
  headers: { 'content-type': 'application/json', ...headers },
  body: JSON.stringify(body),
});

const keyed = (key: string): RequestInit => ({ headers: { 'x-pop-key': key } });

export const api = {
  health: () => request<Health>('/api/health'),
  match: () => request<MatchInfo>('/api/match'),
  state: () => request<MatchState>('/api/state'),
  events: (since: number, limit = 200) =>
    request<EventsResponse>(`/api/events?since=${since}&limit=${limit}`),
  createSession: (body: SessionRequest) =>
    request<{ session_id: string }>('/api/session', json(body)),
  feed: (sessionId: string) => request<FeedResponse>(`/api/feed/${encodeURIComponent(sessionId)}`),
  evidence: (factIds: string[]) =>
    request<EvidenceResponse>(`/api/evidence?fact_ids=${factIds.map(encodeURIComponent).join(',')}`),
  engage: (body: { session_id: string; t_ms: number; kind: EngagementKind }) =>
    request<{ ok: boolean }>('/api/engage', json(body)),
  producer: (key: string) => request<ProducerView>('/api/producer', keyed(key)),
  readout: (key: string, metric: Metric, simulated: boolean) =>
    request<Readout>(`/api/readout?metric=${metric}&simulated=${simulated}`, keyed(key)),
  start: (key: string, body: StartRequest) =>
    request<{ started: boolean; match_id: string }>('/api/admin/start', json(body, { 'x-pop-key': key })),
};
