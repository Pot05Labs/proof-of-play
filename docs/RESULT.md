# Watch-along result

Run on Saturday 24 October 2026, as planned in [PREREG.md](PREREG.md), which was frozen before kick-off and is unchanged.

One full fictional match, seed 7, real speed, kick-off 15:00 SAST, played to full time on the live Azure deployment. Sessions went to their own Cosmos DB container (`watchalong`), separate from load tests and judging.

## The experiment

7 real sessions: 4 personalised, 3 generic. The smallest row in the plan's detectable-difference table is 30 per arm, so this run is underpowered and was always going to be.

| Metric | Personalised | Generic | Difference | 95% interval |
|---|---|---|---|---|
| Watched minutes per session (primary) | 1.31 | 14.83 | -13.52 | -38.13 to 0.81 |
| Why and show-me taps per watched minute (secondary) | 3.88 | 0.48 | 3.40 | 0.24 to 6.52 |

The primary interval includes zero. We cannot tell the two versions apart on watch time, and we do not claim a result either way. The secondary interval excludes zero, but a rate per watched minute is inflated when sessions are short, and the plan does not let a secondary metric override the primary. We report both as they came out.

What this run does show is that the holdout works end to end on live traffic: consent, random assignment that never reaches the browser, server-timed heartbeats, durable logging and the readout. A studio would run the same thing with thousands of viewers.

## The system

| Measure | Result |
|---|---|
| Match events | 4,267, all delivered through Azure Event Hubs, 0 by the fallback |
| Insights written | 152 |
| Rewrites rejected by the Verifier | 0 |
| Insights retracted on the VAR overturn | 3 |
| Model calls | 152, 0 failed |
| Model input served from cache | 75% |
| Model spend for the full match | about US$0.05 at gpt-4.1-mini list price |
| Database writes | 281, 0 failed, 0 dropped |
| Write lag | p50 1.29 s, p95 1.63 s |
