"""Verifier: deterministic grounding check. No model involved.

An insight passes only if every number, every player and every team it mentions can be
traced to the facts it cites (or to the match roster for names). Anything else is rejected
with a reason a producer can read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pop.schema import Fact, Insight, MatchInfo

# Thousands written with a comma or (non-breaking) space are one number: "10,000" and "10 000" mean 10000.
# The style guide reserves the full stop for decimals, so a comma followed by exactly three digits is grouping.
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:[,\u00a0\u202f ]\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)(?:\s?%)?")
_GROUPED = re.compile(r"^\d{1,3}(?:[,\u00a0\u202f ]\d{3})+(?:\.\d+)?$")


def _normalise(raw: str) -> str:
    if _GROUPED.match(raw):
        return re.sub(r"[,\u00a0\u202f ]", "", raw)
    return raw.replace(",", ".")
# Numbers allowed without a fact: ordinals and small counting words rendered as digits are not used;
# we only whitelist match-clock minutes that appear in fact windows or seq-derived minutes.


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reasons: tuple[str, ...]


def _fact_numbers(facts: list[Fact]) -> set[str]:
    out: set[str] = set()
    for f in facts:
        if isinstance(f.value, (int, float)):
            v = float(f.value)
            for fmt in ("{:.0f}", "{:.1f}", "{:.2f}"):
                out.add(fmt.format(v))
                out.add(fmt.format(abs(v)))  # signed indices (momentum) are spoken as a size
            if 0 <= abs(v) <= 1:  # shares and indices may be spoken as percentages
                v = abs(v)
                for fmt in ("{:.0f}", "{:.1f}"):
                    out.add(fmt.format(v * 100))
        for m in _NUM.findall(f"{f.window} {f.unit} {f.value}"):
            out.add(m.replace(",", "."))
    return out


def verify(insight: Insight, cited: list[Fact], info: MatchInfo, minutes: set[int] | None = None) -> Verdict:
    reasons: list[str] = []
    known_ids = {f.fact_id for f in cited}
    missing = [fid for fid in insight.fact_ids if fid not in known_ids]
    if missing:
        reasons.append(f"cites unknown facts: {', '.join(missing)}")
    if not insight.fact_ids:
        reasons.append("cites no facts")

    allowed = _fact_numbers(cited) | {str(m) for m in (minutes or set())}
    for raw in _NUM.findall(insight.text):
        n = _normalise(raw)
        if n not in allowed and str(round(float(n))) not in allowed:
            reasons.append(f"number {raw} is not in the cited facts")

    cited_subjects = {f.subject_id for f in cited}
    if any(f.kind == "score" for f in cited):  # a score is about both teams: it names them home first
        cited_subjects |= {info.home.team_id, info.away.team_id}
    players = {p.player_id: p for t in (info.home, info.away) for p in t.squad}
    teams = {info.home.team_id: info.home, info.away.team_id: info.away}
    text = insight.text.lower()
    cited_players = [players[s] for s in cited_subjects if s in players]
    cited_surnames = {p.name.split()[-1].lower() for p in cited_players}
    cited_team_ids = {s for s in cited_subjects if s in teams}
    for pid, p in players.items():
        if pid in cited_subjects:
            continue
        team_of = next((t.team_id for t in (info.home, info.away) if p in t.squad), None)
        if team_of in cited_team_ids:
            continue
        full = p.name.lower()
        surname = full.split()[-1]
        if re.search(rf"\b{re.escape(full)}\b", text) or re.search(rf"\b{re.escape(surname)}\b", text) and surname not in cited_surnames:
            reasons.append(f"mentions {p.name}, who is not a subject of any cited fact")
    for tid, t in teams.items():
        # The full name matches in any case. A short code matches only in capitals, as written on a scoreboard:
        # otherwise a club coded HAD is "mentioned" by every sentence with the word "had".
        named = re.search(rf"\b{re.escape(t.name.lower())}\b", text) \
            or re.search(rf"\b{re.escape(t.short.upper())}\b", insight.text)
        if named and tid not in cited_subjects \
                and not any(players[s].player_id in {p.player_id for p in t.squad}
                            for s in cited_subjects if s in players):
            reasons.append(f"mentions {t.name}, which is not a subject of any cited fact")
    return Verdict(ok=not reasons, reasons=tuple(dict.fromkeys(reasons)))
