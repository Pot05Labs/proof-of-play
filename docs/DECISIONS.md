# Decisions log

## 2026-10-21: engine v0.1 spec questions (answers from the lead)
1. An overturned goal's shot is annulled: removed from score, shots, on target and xG. Yes.
2. Pass `angle_deg`: 0 degrees points at the opponent goal. Accepted.
3. `body_part` mapping (head / foot / other, missing = foot). Accepted.
4. Territory: keep both `territory_share` and `territory_pct`; the UI shows `territory_pct`.
5. Time base is play clock (`t_ms` between kick-off and half/full time). Accepted.
6. Display precision: the engine keeps 3 decimals. The Verifier already accepts a fact's value at 0, 1 or 2 decimals and as a rounded percentage for shares, so "70%" is valid for 69.718 share points expressed as a percentage only when the fact is a 0..1 share; percentage facts in 0..100 are matched by rounding. Render shows display precision.
7. Moment floor: engine default stays 0.0 (complete record). The broadcast layer filters at importance >= 0.25 and caps distance milestones and pass streaks.
8. Known gaps after an overturn (regime state not re-asserted, touch and territory counts of the annulled shot kept, ball-speed record baseline): accepted for v0.1, logged as follow-ups.
9. `score` as a match-level "h-a" fact and `goal` with the scorer as subject: accepted.
10. A shot with no coordinates defaults to the penalty spot: accepted; the simulator always provides coordinates.

## 2026-10-21: simulator realism
Engine measured median shot distance 9.9 m, 12.25 shots and 1.5 penalties per match. Sent back to the simulator builder: median 13-20 m, 20-30 shots, under 0.6 penalties per match, team xG mostly 0.8-2.2.
