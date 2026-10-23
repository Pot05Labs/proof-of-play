# Pre-registration: live watch-along experiment

**Status: FROZEN** by the commit that adds this line, before the first real viewer joins on Saturday 24 October 2026. Any change after that commit is reported as a deviation in the results.

## Question
Does a personalised, verified insight layer change how long people watch a live football broadcast, compared with a generic insight layer on the same match?

## Design
- One synthetic match on Saturday 24 October 2026, streamed live at real speed (about 104 minutes including half-time), same seed, same engine facts, for every viewer. The kick-off time is the one in the invitation.
- The app runs on Azure with the engagement log in its own Cosmos DB container (`watchalong`), a fresh experiment seed, and the producer console closed to the public.
- Each consenting viewer session is assigned once at random (HMAC of a random session ID keyed by a server-side seed, p = 0.5) to:
  - **personalised**: insights in their chosen mode (analyst or fan), framed around their chosen club and player, in their chosen language;
  - **generic**: neutral insights in the same language, no mode, club or player framing.
- Viewers are told they may see one of two versions. They are not told which.
- Sessions are anonymous: a random ID, timestamps and taps. No names, emails, device fingerprints or location. Every record deletes itself after 30 days.

## Metrics
- **Primary:** watched minutes per session, from 15-second heartbeats sent while the page is visible.
- **Secondary:** "why?" and "show me" taps per watched minute.
- No other outcome will be reported as a finding.

## Analysis
- Difference in means, personalised minus generic, with a 95% percentile bootstrap interval over sessions (5,000 resamples, fixed RNG seed 0).
- Sessions with under one minute watched are kept (leaving early is an outcome, not noise).
- Simulated sessions (IDs starting `SIM-`) are excluded by construction and never shown as real.
- The result is published whatever it is, including a null or a wide interval.

## Sample
- Everyone who consents and joins during the match. There is no target to reach and no extension if few people come.
- We report sessions per arm with the result. The smallest difference the design can reliably detect (80% power, 5% two-sided, sd about 20 minutes) depends on that number:

| Sessions per arm | Smallest reliable difference |
|---|---|
| 30 | about 14 minutes |
| 75 | about 9 minutes |
| 150 | about 6 to 7 minutes |

- With a small turnout the most likely honest result is "no detectable difference". We will say so, and say that it is not evidence of no effect.

## What we will not do
- Stop early or extend the session because of the running result.
- Change the metric, the exclusions or the interval method after seeing data.
- Describe a directional read from one opt-in group as proof for all audiences.
