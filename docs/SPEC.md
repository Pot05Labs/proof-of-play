# Proof of Play: system spec (v0.1, 21 Oct 2026)

Working name. "Every broadcast says personalisation works. Ours proves it."

Hackathon: Microsoft x Premier League, Inside the Game: Developer Hackathon. Challenge: The Synthetic Match Insights Engine for Premier League Studio. Submission closes **Tue 27 Oct 2026, 23:59 PT**.

## 0. Hard rules (read before writing any code)

1. **Synthetic only.** Fictional clubs, players, competitions and venues. No real Premier League names, badges, player names, data or footage anywhere in the repo, the UI or the video.
2. **Written fresh.** No code, constants, docs or method text copied from any other Pot05Labs repository. The measurement is a textbook randomised experiment written from scratch.
3. **Public at submission.** Treat every commit as public. No secrets, no keys, no tenant IDs, no personal data. Config through environment variables, documented in `.env.example`.
4. **Numbers come from code, words come from AI.** Every figure shown to a viewer is produced by the deterministic engine. Language models only phrase facts they are handed, and every sentence carries the IDs of the facts it uses.
5. **A skipped test is a failing test.** The builder of a component never certifies it; a separate checker does.

## 1. Pipeline

```
simulator ──events──▶ stream ──▶ engine (state + facts) ──▶ agents ──▶ insights ──▶ renderer (overlays) ──▶ viewer
                                                                     │                                    │
                                                                     └──────────▶ producer console ◀──────┘
                                                                                         ▲
                                         viewer sessions ──engagement events──▶ experiment ─┘
```

| Stage | Module | Cloud target |
|---|---|---|
| Ingest | `pop.sim` streams events; `pop.stream` abstracts transport | Azure Event Hubs |
| Interpret | `pop.engine` incremental state, stats, facts | Azure Container Apps |
| Explain | `pop.agents` Interpreter, Explainer, Personaliser, Verifier, Producer | Microsoft Foundry + Agent Framework |
| Render | `pop.render` timed overlay JSON | Azure Web PubSub / SignalR |
| Personalise | viewer modes, club, player, language | Azure AI Translator + Speech |
| Measure | `pop.experiment` assignment, engagement log, readout | Azure Cosmos DB |

Every stage must also run fully offline on a laptop (in-memory stream, stub language model) so tests never need the cloud.

## 2. Match event schema (`pop.schema.MatchEvent`)

One JSON object per event, JSON Lines on disk, ordered by `seq`.

| Field | Type | Notes |
|---|---|---|
| `event_id` | str | `"{match_id}:{seq:05d}"`, unique, stable across replays of the same seed |
| `match_id` | str | |
| `seq` | int | strictly increasing from 1 |
| `clock` | object | `{"period": 1|2, "minute": int, "second": int, "added": int}`; match time, monotonic non-decreasing within a period |
| `t_ms` | int | milliseconds since kick-off of period 1, used to time overlays |
| `type` | enum | see below |
| `team_id` | str or null | team performing the action |
| `player_id` | str or null | |
| `x`, `y` | float or null | 0..100 pitch coordinates, attacking left to right for `team_id` |
| `end_x`, `end_y` | float or null | for pass, carry, shot |
| `outcome` | enum or null | `success`, `fail`, `goal`, `saved`, `off_target`, `blocked`, `won`, `lost` |
| `pressure` | float or null | 0..1, opponent pressure on the actor at the moment of the action |
| `related` | list[str] | event_ids this event refers to (e.g. a VAR overturn refers to the goal) |
| `meta` | object | type-specific extras, see below |

Event `type` values and required `meta`:

- `match_start` `{home_team_id, away_team_id, competition, venue, seed}`
- `kick_off`, `half_time`, `full_time`
- `pass` `{receiver_id, length_m, angle_deg, body_part}` outcome `success|fail`
- `carry` `{distance_m}`
- `shot` `{body_part, situation: open_play|set_piece|penalty|counter}` outcome `goal|saved|off_target|blocked`; engine computes xG, the simulator must NOT put xG in the event
- `tackle` outcome `won|lost`; `interception`; `clearance`; `foul` `{card: none|yellow|red}`
- `pressure` an off-ball pressing action on an opponent, `{target_player_id}`
- `possession_change` `{from_team_id, to_team_id, cause}` emitted whenever possession switches
- `substitution` `{player_out_id, player_in_id}`
- `var_review` `{subject_event_id, check}` then `var_decision` `{subject_event_id, decision: stands|overturned, reason}`; an overturned goal must be removed from the score and every fact or insight built on it must be retracted downstream

The simulator also writes a `match.json` with teams, squads (fictional names, shirt numbers, positions), tactical style per team and the seed.

## 3. Engine outputs (`pop.engine`)

The engine consumes events one at a time (`engine.ingest(event)`) and is the only source of numbers.

- `State` snapshot at any `seq`: score, possession % (time-weighted), territory (share of actions in the final third), passes and pass accuracy per team, xG per team, shots and on target, pressing intensity (pressures per opponent pass, rolling 5 minutes), momentum (rolling 5-minute xG and final-third entries difference, -1..+1), control-vs-chaos index (0..1, from possession-change rate, pass length variance and pressure), per-player touches, passes, pass difficulty average, xG, distance proxy.
- `Fact`: an atomic, checkable statement the engine asserts.
  `{fact_id, seq_at, kind, subject (team/player/match), value, unit, window, evidence: [event_id...], computed_by: "engine vX"}`
  Examples: `xg_team`, `goal`, `momentum_shift`, `pressure_spike`, `control_to_chaos`, `pass_streak`, `big_chance_missed`, `player_milestone`.
- `Moment`: a detected key moment with `{moment_id, seq_at, kind, importance 0..1, facts: [fact_id...]}`; importance thresholds and minimum sample sizes are config values, never hard-coded in prose.
- Retraction: on `var_decision overturned`, the engine emits `Retraction{subject_event_id, retracted_fact_ids, retracted_moment_ids}`.

Pass difficulty and xG are simple, documented geometric models (distance, angle, pressure, body part, situation), written here from first principles and covered by tests (monotonic in distance, bounded 0..1).

## 4. Insight and overlay (`pop.agents`, `pop.render`)

`Insight {insight_id, moment_id, audience: analyst|fan, language, text, fact_ids: [...], verified: bool, verifier_notes, confidence, status: draft|approved|published|retracted}`

`Overlay {overlay_id, insight_id, show_at_t_ms, hide_at_t_ms, slot: lower_third|corner|full, template, payload}` machine-readable, timed to match clock.

The Verifier rejects any insight whose text contains a number, player, team or claim not present in its `fact_ids`.

## 5. Viewer and experiment (`pop.experiment`)

Built on day 1 into the schema so the live watch-along cannot slip.

- `Session {session_id (random, anonymous), started_at, arm: personalised|generic, assignment_seed, consent: true, mode: analyst|fan, club_id|null, player_id|null, language}`. No names, emails or device fingerprints.
- Assignment: independent Bernoulli(p=0.5) per session from a server-side seed, recorded once, never re-randomised. Same match, same clock, same facts for both arms; only the insight layer differs (generic arm gets neutral, non-personalised insights).
- `EngagementEvent {session_id, t_ms (match clock), kind, meta}` with kinds `heartbeat` (every 15 s while visible), `why_tap`, `show_me_tap`, `replay_open`, `mode_change`, `visibility_hidden`, `visibility_visible`, `leave`.
- Primary metric (pre-registered before the session in `docs/PREREG.md`): watched minutes per session from heartbeats. Secondary: why/show-me taps per watched minute.
- Readout: difference in means personalised minus generic, 95% interval by bootstrap over sessions, n per arm, shown live; plus a clearly labelled simulated-audience mode for the demo that never mixes with real data.

## 6. Invariants every test suite enforces

- Replaying a seed yields byte-identical events.
- `seq` strictly increasing; `event_id` unique; clock non-decreasing within a period.
- Score from the engine equals goals minus overturned goals.
- Possession % for the two teams sums to 100 (±0.01).
- xG, pass difficulty, importance, control-vs-chaos all in [0,1]; momentum in [-1,1].
- Every `Fact.evidence` id and every `Insight.fact_ids` id exists.
- After a VAR overturn, no published insight references a retracted fact.
- Arm assignment is stable per session and balanced within tolerance over 10,000 simulated sessions.

## 7. Repo layout

```
src/pop/{schema.py, sim/, engine/, agents/, render/, experiment/, api/}
web/            viewer app + producer console
tests/
docs/{SPEC.md, PREREG.md, ARCHITECTURE.md, ASSURANCE.md}
infra/          Bicep for Azure
```
Python 3.12, `uv`, `pytest`, `ruff`. Frontend: Vite + React + TypeScript.
