# Demo video script

Two minutes, read by Vuyani. Plain spoken English, unhurried. Judges are only guaranteed the first two minutes, so the problem and the hook land in the first 20 seconds.

## Before recording

- **Every session you create on the deployed app is a real experiment session.** It goes to Cosmos DB and comes back on restart. Capture the real readout shot first, before any recording sessions exist, or record the viewer shots on a separate deployment with a different seed and Cosmos container.
- **isiZulu shot:** needs the Foundry model, so it cannot be recorded on the offline stub. Before filming, check in the producer log that the isiZulu row is verified and is not the English fallback draft.
- **Chaos shot:** record locally only, with `POP_DEMO_CHAOS=0.3`. A separate revision of the deployed app shares the same engagement container, so it does not protect the experiment.
- **Holdout shot:** use the real readout once the watch-along is done. If you show the simulated toggle at all, keep the SIMULATED banner in frame and say no number from it.
- Run the match with the VAR overturn on (the default) so the retraction happens on screen.

## Main cut, 2:00

| Time | On screen | Voiceover |
|---|---|---|
| 0:00 to 0:08 | Black, then the live viewer: pitch, scoreboard, an insight card sliding in | Every broadcast now says personalisation works. Nobody shows you the proof. |
| 0:08 to 0:20 | Close on the insight card, then the "Why?" button | And when AI writes the stats, nobody shows you they're true. Proof of Play does both. Every number is checked, and every viewer is part of an experiment. |
| 0:20 to 0:32 | Join screen: pick Casual fan, a club, a player, a language. Consent line visible. Tap Join | You join with a few taps. How you watch, your club, your player, your language. No names. You're told you might see one of two versions. |
| 0:32 to 0:46 | Live pitch with events playing, gauges moving: momentum, control versus chaos | This is a fictional match, simulated live. A match engine turns every event into stats and key moments. The numbers only ever come from code. |
| 0:46 to 0:58 | Tap "Why?" on a card. The panel lists facts, values and source events. Tap "Show me": the events light up on the pitch | Every insight cites its facts. Tap why, and you see the numbers and the exact events behind them. Show me puts them on the pitch. |
| 0:58 to 1:06 | Switch to an isiZulu viewer. An insight card in isiZulu | The words are written by a model on Microsoft Foundry, in your language. Here it is in isiZulu. |
| 1:06 to 1:20 | A goal card on screen. VAR overturn: the score corrects, the card shows "Updated: VAR decision" and leaves | Now VAR rules the goal out. The engine takes it off the score and the expected goals, and every insight built on that goal comes off the screen. Live. |
| 1:20 to 1:36 | Producer console, insight log. Filter to "Rewrites rejected". Hold on the Verifier note, for example "number 41 is not in the cited facts" | This is the producer console. For this demo we switched on a setting that makes the model invent a stat. Our Verifier is plain code. It caught it, rejected the sentence, and published the grounded version instead. |
| 1:36 to 1:52 | Experiment panel: personalised minus generic, watched minutes, the interval chart. Real result only | Last part. Viewers were randomly split between personalised and generic insights. Seven joined our live watch-along. Far too few to tell the versions apart, and we're publishing that. |
| 1:52 to 2:00 | Azure portal: the resource group in South Africa North, then the wordmark and the line | It runs on Azure in South Africa North. Proof of Play. Every broadcast says personalisation works. Ours proves it. |

About 245 spoken words.

### The real watch-along result

From [RESULT.md](RESULT.md), 24 October, 7 sessions: 4 personalised, 3 generic. Personalised minus generic watched minutes: **-13.52** minutes, 95% interval **-38.13 to 0.81**. The interval includes zero.

Line for 1:36 to 1:52 (about 25 words):

> Viewers were randomly split between personalised and generic insights. Seven joined our live watch-along. Far too few to tell the versions apart, and we're publishing that.

Line for the 30-second cut (one short clause):

> With seven viewers on our live run, too few to call, and we publish it anyway.

Do not round the interval into a claim it does not make, do not mention the secondary metric, and do not use the simulated readout here.

## Recording order

The experiment panel reads whichever Cosmos container the deployment is on, so the order matters.

1. **Now, on the current deployment (`watchalong`):** open the producer console and record shot 10 (experiment panel, real readout). Do not join as a viewer on this deployment: every join is a new watch-along session.
2. **Locally, `POP_DEMO_CHAOS=0.3`:** record shot 9 (rejected rewrite with the Verifier note).
3. **Switch to judging:** `scripts/deploy.sh v2 engagement 30 judging`. From here on, sessions land in `engagement`, not `watchalong`.
4. **On the judging deployment:** record shots 1 to 8 and 12. Matches replay back to back at 10x with the VAR overturn on, so the goal and retraction (shot 8) come round every few minutes. Check the isiZulu row is verified in the producer log before shot 7.
5. **Azure portal:** shot 11.

## Shot list

1. Viewer, live screen with an insight card arriving (desktop, 1440 wide).
2. Insight card close-up with "Why?" and "Show me" buttons.
3. Join screen: mode, club, player, language, consent line, Join.
4. Live pitch and gauges over a passage of play.
5. "Why?" panel: facts, values, windows, "Computed by", evidence events.
6. "Show me": highlighted events on the pitch.
7. isiZulu viewer with a model-written isiZulu insight (deployed app).
8. Goal, then VAR overturn: score correction and the "Updated: VAR decision" card.
9. Producer console insight log, filtered to a rejected rewrite, Verifier note readable (chaos run).
10. Producer experiment panel with the real readout.
11. Azure portal: the resource group overview with region South Africa North and the resources listed.
12. Closing card: pot/labs wordmark and "Every broadcast says personalisation works. Ours proves it."

## 30-second cut

| Time | On screen | Voiceover |
|---|---|---|
| 0:00 to 0:08 | Live viewer, insight card arriving | Every broadcast says personalisation works. Nobody shows you the proof. |
| 0:08 to 0:16 | "Why?" panel, then the VAR overturn card leaving | Proof of Play checks every AI-written stat against the match engine, and pulls it the moment VAR changes the facts. |
| 0:16 to 0:25 | Experiment panel, real readout | And every viewer is part of a randomised experiment. With seven viewers on our live run, too few to call, and we publish it anyway. |
| 0:25 to 0:30 | Azure resource group, then the closing card | Built on Azure. Ours proves it. |

About 65 spoken words.
