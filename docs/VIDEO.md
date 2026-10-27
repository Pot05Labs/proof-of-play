# Demo video script

Under two minutes, read by Vuyani. Plain spoken English, unhurried. The rules require the video to be **less than** two minutes and judges need not watch past 2:00, so the cut ends at 1:56 and the problem and the hook land in the first 20 seconds.

## Before recording

- **Every session you create on the deployed app is a real experiment session.** It goes to Cosmos DB and comes back on restart. Capture the real readout shot first, before any recording sessions exist, or record the viewer shots on a separate deployment with a different seed and Cosmos container.
- **isiZulu shot:** needs the Foundry model, so it cannot be recorded on the offline stub. Before filming, check in the producer log that the isiZulu row is verified and is not the English fallback draft.
- **Chaos shot:** record locally only, with `POP_DEMO_CHAOS=0.3`. A separate revision of the deployed app shares the same engagement container, so it does not protect the experiment.
- **Holdout shot:** use the real readout once the watch-along is done. If you show the simulated toggle at all, keep the SIMULATED banner in frame and say no number from it.
- Run the match with the VAR overturn on (the default) so the retraction happens on screen.
- **Rules for the video (Official Rules 4.4):** under 2:00; shows the app actually running; public URL on YouTube or Vimeo (unlisted is not public: set it to public); no third-party trademarks and no copyrighted music. Use no music, or a track you hold a licence for. Nothing from the Premier League: no badge, logo or league name on screen.

## The brief on a page

- **Insight.** Every broadcaster wants AI talking to every fan in their own way. None of them wants to be the broadcaster that put a false number on air.
- **Tension.** Personalisation multiplies the sentences. Every extra sentence is another chance to be wrong, and nobody can prove the personalisation is worth it.
- **Idea.** Proof, not promises. Every sentence carries its receipts, the screen takes back what is no longer true, and we publish the result even when it doesn't flatter us.
- **The one thing to remember.** The most important agent is the one that says no.

## How the film works

- **Start with the drama, not the problem.** We open in the 53rd minute, on a goal for our viewer's favourite player, and VAR takes it away. Judges are only guaranteed the first two minutes, so we earn attention in the first seven seconds, then explain.
- **Characters, not users.** Two fictional fans carry the story: Leo, an analyst watching in English, and Thandi, a casual fan watching in isiZulu. We follow Leo's screen and meet Thandi beside him. They are illustrative personas, not real viewers.
- **Reframe the features.** The "Why?" button is the receipt. The Verifier is the agent that says no. Publishing a result too small to call is the costliest signal of honesty we can send. Proof you only share when it flatters you isn't proof.
- **Show, then say.** Every claim in the voiceover is on screen as it is said, and the voiceover leaves room to breathe: about 230 words in 1:56.
- **Sound carries the emotion.** A low stadium crowd bed throughout. It swells on the goal and cuts to silence the moment VAR rules it out, then comes back quietly. Use only audio you hold a licence for (Official Rules 4.4), for example a CC0 crowd recording, and keep its licence page. No music is better than unlicensed music.
- **Distinctive assets, every time.** The amber, the wordmark and the line "Every broadcast says personalisation works. Ours proves it." The line closes the film exactly as it opens the README.

## Main cut, 1:56

| Time | On screen | Voiceover | Sound |
|---|---|---|---|
| 0:00 to 0:07 | Leo's screen: the 53rd-minute goal card for his favourite player, 3-0 | Fifty-three minutes. Leo's favourite player scores, and his screen tells him why it matters. | Crowd swells |
| 0:07 to 0:14 | VAR overturned: the goal card struck through, "Updated: VAR decision", score back to 2-0 | Then VAR rules it out. And his screen takes it back too. Instantly. | Hard cut to silence on "VAR" |
| 0:14 to 0:24 | Live match moving, then the title card at 0:20 | Every broadcaster wants AI talking to every fan. None of them wants to be the one that put a false number on air. | Crowd returns, low |
| 0:24 to 0:34 | Join screen: Analyst, club, player, language, consent line, Join | So we built Proof of Play. Fans choose how they watch: analyst or casual, their club, their player, their language. No names. | |
| 0:34 to 0:46 | "Why?" panel with facts and source events, then "Show me" lighting them up on the pitch | Every sentence comes with its receipts. Tap why, and you see the exact facts and events behind it. Show me puts them on the pitch. | |
| 0:46 to 0:56 | Split screen: Leo's analyst card in English beside Thandi's casual card in isiZulu, same moment | Same moment, two fans. Leo gets the numbers. Thandi gets the story, in isiZulu, written by a model on Microsoft Foundry. | |
| 0:56 to 1:04 | Pitch and gauges: momentum, control versus chaos | Our rule: numbers come from code, words from AI. Only the match engine is allowed to count. | |
| 1:04 to 1:20 | Producer console: rejected rewrites, then one agent trace: Writer invents a number, Verifier rejects, Fallback publishes the true draft | Six agents on Microsoft Agent Framework write every sentence. The most important one says no. We made the writer cheat. Our Verifier, plain code, caught the invented number, and the true version went out instead. | |
| 1:20 to 1:42 | Experiment panel with the real watch-along readout | Does personalisation work? Everyone claims it. We tested it: fans split at random, personalised or generic, the plan written before kick-off. Seven came. Too few to call. We're publishing it anyway. Proof you only share when it flatters you isn't proof. | Crowd fades |
| 1:42 to 1:56 | Azure resource group in South Africa North, then the closing card at 1:50 | Built on Azure. About five cents a match, in any language. Every broadcast says personalisation works. Ours proves it. | Silence under the last line |

### The real watch-along result

From [RESULT.md](RESULT.md), 24 October, 7 sessions: 4 personalised, 3 generic. Personalised minus generic watched minutes: **-13.52** minutes, 95% interval **-38.13 to 0.81**. The interval includes zero.

The line at 1:20 to 1:42 reports it as: seven came, too few to call, published anyway.

Line for the 30-second cut (one short clause):

> With seven viewers on our live run, too few to call, and we publish it anyway.

Do not round the interval into a claim it does not make, do not mention the secondary metric, and do not use the simulated readout here.

## Footage

Most of the cut is already recorded: Playwright drove the app locally at 1920x1080 and 133% zoom, seed 7, VAR overturn on, with the offline stub model. The stub publishes the grounded English draft, so these shots show true template sentences, not model prose. The voiceover only names Foundry over the isiZulu shot, which is filmed on Azure.

| Clip | Covers | Source |
|---|---|---|
| A_join | 0:24 to 0:34 | Local, clean server |
| B_live_opening | 0:14 to 0:20 | Local, clean server |
| C_why_showme | 0:34 to 0:46 | Local, clean server |
| D_pitch_gauges | 0:56 to 1:04 | Local, clean server |
| E_goal_var_retraction | 0:00 to 0:14, the cold open | Local, clean server. Goal at about 6 s, overturn and "Updated: VAR decision" at about 20 s |
| F_producer_verifier_trace | 1:04 to 1:20 | Local, `POP_DEMO_CHAOS=0.3`. Labelled "stub+chaos" on screen. The trace shows the Writer's invented "7th time this month", two rejections and the Fallback |
| G_title_card, H_closing_card | 0:20 to 0:24, 1:50 to 1:56 | Rendered in the app's fonts and colours |

`rough_cut.mp4` lays these out on the timings above at exactly 1:56, with labelled placeholders for the three shots below. Record the voiceover over it and drop the three shots in.

## Still to film, in this order

The experiment panel reads whichever Cosmos container the deployment is on, so the order matters.

1. **Readout (1:20 to 1:42), on the current deployment (`watchalong`), before anything else.** Open the producer console and hold on the experiment panel. Do not join as a viewer on this deployment: every join is a new watch-along session.
2. **Switch to judging:** `scripts/deploy.sh v2 engagement 30 judging`. From here on, sessions land in `engagement`, not `watchalong`.
3. **Leo and Thandi split (0:46 to 0:56), on the judging deployment.** Two browser windows side by side: Leo, an analyst in English, and Thandi, a casual fan in isiZulu, both following Harrowmere Dynamos and Tshepo Okonkwo. Hold on a moment both cards cover. Check in the producer log that the isiZulu row is verified, not the English fallback draft.
4. **Azure portal (1:42 to 1:50):** the resource group overview, region South Africa North, resources listed.

## 30-second cut

| Time | On screen | Voiceover |
|---|---|---|
| 0:00 to 0:08 | Live viewer, insight card arriving | Every broadcast says personalisation works. Nobody shows you the proof. |
| 0:08 to 0:16 | "Why?" panel, then the VAR overturn card leaving | Proof of Play checks every AI-written stat against the match engine, and pulls it the moment VAR changes the facts. |
| 0:16 to 0:25 | Experiment panel, real readout | And every viewer is part of a randomised experiment. With seven viewers on our live run, too few to call, and we publish it anyway. |
| 0:25 to 0:30 | Azure resource group, then the closing card | Built on Azure. Ours proves it. |

About 65 spoken words.
