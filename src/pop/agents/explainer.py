"""Explainer + Personaliser, with a verified fallback.

Flow for one moment:
  1. build a grounded draft from templates (numbers copied from facts, so it is true by construction);
  2. ask the model to rewrite the draft for the audience, club, player and language, using only the facts;
  3. verify the rewrite; if it fails, publish the template draft instead and record why.
The fallback is the failure-recovery path: the broadcast never shows an unverified claim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pop.agents.llm import LLM, StubLLM
from pop.agents.verifier import verify
from pop.schema import Audience, Fact, Insight, MatchInfo, Moment

SYSTEM = (
    "You are a football studio writer. Rewrite the DRAFT for the AUDIENCE using ONLY the FACTS given. "
    "Do not add any number, player, team or claim that is not in the FACTS. Keep it under 35 words. "
    "Analysts want the numbers and the tactical reason. Casual fans want the story in plain words. "
    "If a favourite club or player is given, frame the sentence from their point of view. "
    "Write in the requested LANGUAGE. Return only the sentence."
)


@dataclass(frozen=True)
class Viewer:
    audience: Audience = "fan"
    language: str = "en"
    club_id: str | None = None
    player_id: str | None = None

    @property
    def generic(self) -> bool:
        return self.club_id is None and self.player_id is None


GENERIC = Viewer()


def _names(info: MatchInfo) -> dict[str, str]:
    out = {info.home.team_id: info.home.name, info.away.team_id: info.away.name}
    for t in (info.home, info.away):
        for p in t.squad:
            out[p.player_id] = p.name
    return out


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.2f}" if v < 1 else f"{v:.1f}"
    return str(v)


TEMPLATES: dict[str, str] = {
    "goal": "Goal for {subject}.",
    "xg_player": "{subject}'s chance was worth {value} expected goals.",
    "xg_team": "{subject} have built {value} expected goals so far.",
    "shot_speed": "{subject}'s shot left the boot at {value} km/h.",
    "big_chance_missed": "{subject} missed a chance worth {value} expected goals.",
    "momentum_shift": "Momentum has swung towards {subject}.",
    "pressure_spike": "{subject} have turned up the press.",
    "control_to_chaos": "The match has turned chaotic.",
    "chaos_to_control": "{subject} have settled the game down.",
    "pass_streak": "{subject} strung together {value} passes in a row.",
    "player_top_speed_alert": "{subject} hit {value} km/h.",
    "player_distance_milestone": "{subject} has covered {value} metres.",
    "possession_swing": "{subject} are seeing more of the ball.",
    "red_card": "Red card for {subject}.",
    "var_overturn": "VAR has ruled out the goal by {subject}.",
}


def template_draft(facts: list[Fact], info: MatchInfo) -> str:
    names = _names(info)
    parts = []
    for f in facts:
        tpl = TEMPLATES.get(f.kind, "{subject}: {kind} {value}.")
        parts.append(tpl.format(subject=names.get(f.subject_id, "The match"), value=_fmt(f.value), kind=f.kind))
    return " ".join(parts[:2])


def explain(moment: Moment, facts: list[Fact], info: MatchInfo, viewer: Viewer = GENERIC,
            llm: LLM | None = None, minute: int | None = None) -> Insight:
    llm = llm or StubLLM()
    draft = template_draft(facts, info)
    names = _names(info)
    payload = {
        "draft": draft,
        "facts": [{"id": f.fact_id, "kind": f.kind, "subject": names.get(f.subject_id, f.subject_id),
                   "value": f.value, "unit": f.unit, "window": f.window} for f in facts],
        "audience": viewer.audience,
        "language": viewer.language,
        "favourite_club": names.get(viewer.club_id) if viewer.club_id else None,
        "favourite_player": names.get(viewer.player_id) if viewer.player_id else None,
    }
    text = llm.complete(SYSTEM, json.dumps(payload, ensure_ascii=False)) or draft
    ins = Insight(
        insight_id=f"{moment.moment_id}:{viewer.audience}:{viewer.language}:{viewer.club_id or '-'}:{viewer.player_id or '-'}",
        moment_id=moment.moment_id, audience=viewer.audience, language=viewer.language, text=text,
        fact_ids=[f.fact_id for f in facts], confidence=moment.importance,
        personalised_for={k: v for k, v in {"club": viewer.club_id, "player": viewer.player_id}.items() if v},
    )
    minutes = {minute} if minute is not None else set()
    v = verify(ins, facts, info, minutes)
    if v.ok:
        return ins.model_copy(update={"verified": True, "verifier_notes": "verified"})
    fallback = ins.model_copy(update={"text": draft})
    v2 = verify(fallback, facts, info, minutes)
    note = "model rewrite rejected (" + "; ".join(v.reasons) + "); published grounded draft"
    return fallback.model_copy(update={"verified": v2.ok, "verifier_notes": note,
                                       "status": "draft" if v2.ok else "rejected"})
