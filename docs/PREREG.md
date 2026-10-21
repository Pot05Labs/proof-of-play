# Pre-registration: live watch-along experiment

**Status: DRAFT.** Frozen by commit before the first real viewer joins. Any change after that commit is reported as a deviation in the results.

## Question
Does a personalised, verified insight layer change how long people watch a live football broadcast, compared with a generic insight layer on the same match?

## Design
- One synthetic match, streamed live at real speed, same seed, same engine facts, for every viewer.
- Each consenting viewer session is assigned once at random (HMAC of a random session ID keyed by a server-side seed, p = 0.5) to:
  - **personalised**: insights in their chosen mode (analyst or fan), framed around their chosen club and player, in their chosen language;
  - **generic**: neutral insights in the same language, no mode, club or player framing.
- Viewers are told they may see one of two versions. They are not told which.
- Sessions are anonymous: a random ID, timestamps and taps. No names, emails, device fingerprints or location. The log is deleted after judging.

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
- Target: at least 150 sessions per arm. Expected: a few hundred in total from an opt-in invitation.
- With sd about 20 minutes and 150 per arm, the smallest difference we can reliably detect is roughly 6 to 7 minutes. Smaller effects will show as "no detectable difference", and we will say so.

## What we will not do
- Stop early or extend the session because of the running result.
- Change the metric, the exclusions or the interval method after seeing data.
- Describe a directional read from a few hundred viewers as proof for all audiences.
