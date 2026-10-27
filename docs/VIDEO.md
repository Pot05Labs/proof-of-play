# Demo video script

Under two minutes, read by Vuyani. Plain spoken English, unhurried. The rules require the video to be **less than** two minutes and judges need not watch past 2:00, so the cut ends at 1:56 and the problem and the hook land in the first 20 seconds.

## Before recording

- **Every session you create on the deployed app is a real experiment session.** It goes to Cosmos DB and comes back on restart. Capture the real readout shot first, before any recording sessions exist, or record the viewer shots on a separate deployment with a different seed and Cosmos container.
- **isiZulu shot:** needs the Foundry model, so it cannot be recorded on the offline stub. Before filming, check in the producer log that the isiZulu row is verified and is not the English fallback draft.
- **Chaos shot:** record locally only, with `POP_DEMO_CHAOS=0.3`. A separate revision of the deployed app shares the same engagement container, so it does not protect the experiment.
- **Holdout shot:** use the real readout once the watch-along is done. If you show the simulated toggle at all, keep the SIMULATED banner in frame and say no number from it.
- Run the match with the VAR overturn on (the default) so the retraction happens on screen.
- **Rules for the video (Official Rules 4.4):** under 2:00; shows the app actually running; public URL on YouTube or Vimeo (unlisted is not public: set it to public); no third-party trademarks and no copyrighted music. Use no music, or a track you hold a licence for. Nothing from the Premier League: no badge, logo or league name on screen.

## Main cut, 1:56

The story in three acts. **Act 1, the problem:** broadcasters want AI to explain the match to every fan, but AI can invent a number and nobody proves personalisation works. **Act 2, the match:** we follow a viewer through a live match, and the twist is the VAR overturn, where the truth changes mid-broadcast. **Act 3, the proof:** behind the screen, the Verifier catches the AI cheating, the experiment reports honestly, and it all runs on Azure, ready for a studio.

Every claim in the voiceover is shown on screen as it is said.

| Time | Act | On screen | Voiceover |
|---|---|---|---|
| 0:00 to 0:12 | 1 | Live viewer: pitch moving, scoreboard, an insight card sliding in | Every broadcaster wants AI to explain the match to every fan. Two things stop them. AI can invent a number. And nobody proves personalisation works. |
| 0:12 to 0:16 | 1 | Title card: Proof of Play wordmark | This is Proof of Play. It fixes both. |
| 0:16 to 0:28 | 2 | Join screen: choose Analyst, a club, a player, a language. Consent line in frame. Tap Join | You join in a few taps. Fan or analyst, your club, your player, your language. No names. And you're told you may see one of two versions. |
| 0:28 to 0:40 | 2 | Live pitch with play moving, momentum and control-versus-chaos gauges shifting | A fictional match plays live. Every event streams through Azure Event Hubs into a match engine, and the engine is the only thing allowed to produce a number. |
| 0:40 to 0:52 | 2 | Tap "Why?" on a card: facts, values, source events. Then "Show me": the events light up on the pitch | Six agents on Microsoft Agent Framework turn each moment into a sentence for you. Tap why, and you see the exact facts and events behind it. |
| 0:52 to 1:02 | 2 | Split screen: analyst card in English beside a casual fan's card in isiZulu, same moment | Same moment, two viewers. The analyst gets the numbers. The casual fan gets the story, in isiZulu, written on Microsoft Foundry. |
| 1:02 to 1:16 | 2 | The 53rd-minute goal by the viewer's favourite player, score 3-0. VAR review, then overturned: score back to 2-0, cards marked "Updated: VAR decision" leave | Fifty-three minutes. Goal. Then VAR rules it out for handball. The score corrects, and every insight built on that goal leaves every screen. Live. |
| 1:16 to 1:32 | 3 | Producer console: "Rewrites rejected" filter, the Verifier's reason readable, then one insight's agent trace step by step | Behind the screen, we made the writer cheat and invent stats. Our Verifier is plain code. It rejects any number the facts don't support, and the viewer gets the true version. Every step is traced. |
| 1:32 to 1:46 | 3 | Experiment panel with the real watch-along readout | Every viewer is also in an experiment: personalised against generic, assigned at random. We wrote the plan first. Seven joined our live match. Too few to call. We publish it anyway. |
| 1:46 to 1:56 | 3 | Azure resource group in South Africa North, then the closing card | One Bicep template on Azure. Five cents of model spend a match. Every broadcast says personalisation works. Ours proves it. |

About 240 spoken words: a calm 2.1 words a second.

### The real watch-along result

From [RESULT.md](RESULT.md), 24 October, 7 sessions: 4 personalised, 3 generic. Personalised minus generic watched minutes: **-13.52** minutes, 95% interval **-38.13 to 0.81**. The interval includes zero.

The line at 1:32 to 1:46 reports it as: seven joined, too few to call, published anyway.

Line for the 30-second cut (one short clause):

> With seven viewers on our live run, too few to call, and we publish it anyway.

Do not round the interval into a claim it does not make, do not mention the secondary metric, and do not use the simulated readout here.

## Footage

Most of the cut is already recorded: Playwright drove the app locally at 1920x1080 and 133% zoom, seed 7, VAR overturn on, with the offline stub model. The stub publishes the grounded English draft, so these shots show true template sentences, not model prose. The voiceover only names Foundry over the isiZulu shot, which is filmed on Azure.

| Clip | Covers | Source |
|---|---|---|
| A_join | 0:16 to 0:28 | Local, clean server |
| B_live_opening | 0:00 to 0:12 | Local, clean server |
| C_why_showme | 0:40 to 0:52 | Local, clean server |
| D_pitch_gauges | 0:28 to 0:40 | Local, clean server |
| E_goal_var_retraction | 1:02 to 1:16 | Local, clean server. Goal at about 6 s, overturn and "Updated: VAR decision" at about 20 s |
| F_producer_verifier_trace | 1:16 to 1:32 | Local, `POP_DEMO_CHAOS=0.3`. Labelled "stub+chaos" on screen. The trace shows the Writer's invented "7th time this month", two rejections and the Fallback |
| G_title_card, H_closing_card | 0:12 to 0:16, 1:50 to 1:56 | Rendered in the app's fonts and colours |

`rough_cut.mp4` lays these out on the timings above at exactly 1:56, with labelled placeholders for the three shots below. Record the voiceover over it and drop the three shots in.

## Still to film, in this order

The experiment panel reads whichever Cosmos container the deployment is on, so the order matters.

1. **Readout (1:32 to 1:46), on the current deployment (`watchalong`), before anything else.** Open the producer console and hold on the experiment panel. Do not join as a viewer on this deployment: every join is a new watch-along session.
2. **Switch to judging:** `scripts/deploy.sh v2 engagement 30 judging`. From here on, sessions land in `engagement`, not `watchalong`.
3. **isiZulu split (0:52 to 1:02), on the judging deployment.** Two browser windows side by side: an analyst in English and a casual fan in isiZulu, both following the same club. Hold on a moment both cards cover. Check in the producer log that the isiZulu row is verified, not the English fallback draft.
4. **Azure portal (1:46 to 1:50):** the resource group overview, region South Africa North, resources listed.

## 30-second cut

| Time | On screen | Voiceover |
|---|---|---|
| 0:00 to 0:08 | Live viewer, insight card arriving | Every broadcast says personalisation works. Nobody shows you the proof. |
| 0:08 to 0:16 | "Why?" panel, then the VAR overturn card leaving | Proof of Play checks every AI-written stat against the match engine, and pulls it the moment VAR changes the facts. |
| 0:16 to 0:25 | Experiment panel, real readout | And every viewer is part of a randomised experiment. With seven viewers on our live run, too few to call, and we publish it anyway. |
| 0:25 to 0:30 | Azure resource group, then the closing card | Built on Azure. Ours proves it. |

About 65 spoken words.
