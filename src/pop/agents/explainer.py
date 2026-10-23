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
from pop.agents.style_guide import STYLE_GUIDE
from pop.agents.verifier import verify
from pop.schema import Audience, Fact, Insight, MatchInfo, Moment

SYSTEM = STYLE_GUIDE


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
        if v >= 1 and v.is_integer():
            return str(int(v))
        return f"{v:.2f}" if v < 1 else f"{v:.1f}"
    return str(v)


TEMPLATES: dict[str, str] = {
    "goal": "Goal for {subject}.",
    "score": "It is {value}.",
    "xg_player": "{subject} has built {value} expected goals in the match.",
    "xg_team": "{subject} have built {value} expected goals.",
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


XG_UNITS = {
    "xg_team": "xG, this team's total in the match so far",
    "xg_player": "xG, this player's total in the match so far",
    "big_chance_missed": "xG of this one missed chance",
}
RECAP_LEAD = {"recap_half_time": "Half-time.", "recap_full_time": "Full time."}


def _score_line(f: Fact, info: MatchInfo) -> str:
    """'2-1' is home-away. Name both teams so neither the reader nor the model has to guess who leads."""
    h, a = str(f.value).split("-")
    return f"{info.home.name} {h}, {info.away.name} {a}."


def fact_rows(facts: list[Fact], info: MatchInfo) -> list[dict]:
    """The facts as the model sees them. A score's subject names the teams in the order its digits follow."""
    names = _names(info)
    rows = []
    for f in facts:
        subject = names.get(f.subject_id, f.subject_id)
        unit = f.unit
        if f.kind == "score":
            subject, unit = f"{info.home.name} v {info.away.name}", "goals, home team first"
        elif f.kind in XG_UNITS:  # say whose xG it is, so a team total is never credited to one player
            unit = XG_UNITS[f.kind]
        value = f.value
        if f.kind == "momentum_shift" and isinstance(value, (int, float)):
            # The engine signs momentum home-positive. The model read "-0.375 for the away side" as "away from them".
            value, unit = abs(value), "size of the momentum swing; the subject team is the one GAINING momentum"
        rows.append({"id": f.fact_id, "kind": f.kind, "subject": subject, "value": value, "unit": unit,
                     "window": f.window})
    return rows


def template_draft(facts: list[Fact], info: MatchInfo, kind: str | None = None) -> str:
    names = _names(info)
    parts = []
    for f in facts:
        if f.kind == "score":
            parts.append(_score_line(f, info))
            continue
        tpl = TEMPLATES.get(f.kind, "{subject}: {kind} {value}.")
        parts.append(tpl.format(subject=names.get(f.subject_id, "The match"), value=_fmt(f.value), kind=f.kind))
    if kind in RECAP_LEAD:  # score plus both teams' xG, under a lead that says which break it is
        return " ".join([RECAP_LEAD[kind], *parts[:3]])
    return " ".join(parts[:2])


def explain(moment: Moment, facts: list[Fact], info: MatchInfo, viewer: Viewer = GENERIC,
            llm: LLM | None = None, minute: int | None = None) -> Insight:
    llm = llm or StubLLM()
    draft = template_draft(facts, info, moment.kind)
    names = _names(info)
    payload = {
        "draft": draft,
        "facts": fact_rows(facts, info),
        "audience": viewer.audience,
        "language": viewer.language,
        "favourite_club": names.get(viewer.club_id) if viewer.club_id else None,
        "favourite_player": names.get(viewer.player_id) if viewer.player_id else None,
        "minute": minute,
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
