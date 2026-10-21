"""The agent team: Interpreter -> Writer -> Verifier -> (Editor -> Verifier) -> (Fallback). No network."""

import asyncio
import json

import pytest

from pop.agents import orchestrator
from pop.agents.explainer import Viewer, explain, template_draft
from pop.agents.orchestrator import TraceStep, run_moment
from pop.agents.verifier import verify
from pop.schema import Fact, MatchInfo, Moment, Player, Team


def _info():
    def squad(prefix, names):
        return [Player(player_id=f"{prefix}{i}", name=n, number=i + 1, position="FW") for i, n in enumerate(names)]
    home = Team(team_id="H", name="Kestrel Vale", short="KVA", style="high_press", colour="#123",
                squad=squad("h", ["Tomas Okafor"]))
    away = Team(team_id="A", name="Harbour Rovers", short="HRO", style="low_block", colour="#456",
                squad=squad("a", ["Ivo Brandt"]))
    return MatchInfo(match_id="m", seed=1, competition="Synthetic League", venue="Riverside", home=home, away=away)


FACTS = [
    Fact(fact_id="f1", seq_at=5, kind="big_chance_missed", subject_kind="player", subject_id="h0",
         value=0.48, evidence=["m:00005"], computed_by="engine v0.1"),
    Fact(fact_id="f2", seq_at=5, kind="xg_team", subject_kind="team", subject_id="H",
         value=1.7, evidence=["m:00005"], computed_by="engine v0.1"),
]
MOMENT = Moment(moment_id="mo1", seq_at=5, kind="big_chance", importance=0.8, facts=["f1", "f2"])
HONEST = "So close for Okafor: that chance was worth 0.48 expected goals."
LIE = "Okafor missed a sitter worth 0.48 xG, his 4th miss tonight, as Brandt watched."


class Scripted:
    """Fake model: one reply for Writer calls, another for Editor (repair) calls. Records every call."""

    def __init__(self, writer, editor="", name="scripted"):
        self.writer, self.editor, self.name = writer, editor, name
        self.calls: list[dict] = []

    def complete(self, system, user):
        p = json.loads(user)
        self.calls.append(p)
        reply = self.editor if p.get("task") == "repair" else self.writer
        if isinstance(reply, Exception):
            raise reply
        return reply


def _run(llm, viewer=None, minute=23):
    return run_moment(MOMENT, FACTS, _info(), viewer or Viewer(club_id="H"), llm, minute)


def _agents(trace):
    return [s.agent for s in trace]


def test_honest_writer_is_verified_first_time():
    llm = Scripted(HONEST)
    ins, trace = _run(llm)
    assert ins.verified and ins.text == HONEST
    assert ins.verifier_notes == "verified first time"
    assert ins.fact_ids == ["f1", "f2"] and ins.personalised_for == {"club": "H"}
    assert _agents(trace) == ["Interpreter", "Writer", "Verifier"]
    assert len(llm.calls) == 1  # the Editor never runs when the Writer is clean


def test_lying_writer_is_repaired_by_editor():
    llm = Scripted(LIE, editor=HONEST)
    ins, trace = _run(llm)
    assert ins.verified and ins.text == HONEST
    assert ins.verifier_notes.startswith("repaired by Editor after: writer rewrite rejected (")
    assert "number 4" in ins.verifier_notes and "Ivo Brandt" in ins.verifier_notes
    assert _agents(trace) == ["Interpreter", "Writer", "Verifier", "Editor", "Verifier"]
    assert [s.ok for s in trace] == [True, True, False, True, True]
    repair = llm.calls[1]
    assert repair["task"] == "repair" and repair["rejected_text"] == LIE
    assert any("number 4" in r for r in repair["reasons"])
    assert repair["draft"] == template_draft(FACTS, _info())  # the Editor still sees the grounded draft


def test_lying_writer_and_lying_editor_fall_back_to_draft():
    llm = Scripted(LIE, editor=LIE.replace("4th", "5th"))
    ins, trace = _run(llm)
    assert ins.verified and ins.text == template_draft(FACTS, _info())
    assert "4th" not in ins.text and "5th" not in ins.text and "Brandt" not in ins.text
    assert ins.verifier_notes.startswith("fell back to grounded draft after: writer rewrite rejected")
    assert "editor rewrite rejected" in ins.verifier_notes
    assert _agents(trace) == ["Interpreter", "Writer", "Verifier", "Editor", "Verifier", "Fallback"]
    assert len(llm.calls) == 2  # exactly ONE repair attempt


@pytest.mark.parametrize("failure", ["", RuntimeError("429 rate limited"), TimeoutError()])
def test_failing_model_falls_back_without_calling_editor(failure):
    llm = Scripted(failure, editor=failure)
    ins, trace = _run(llm)
    assert ins.verified and ins.text == template_draft(FACTS, _info())
    assert ins.verifier_notes == "fell back to grounded draft after: writer returned no text"
    assert _agents(trace) == ["Interpreter", "Writer", "Fallback"]
    assert trace[1].ok is False and len(llm.calls) == 1


def test_editor_failing_after_rejection_falls_back():
    ins, trace = _run(Scripted(LIE, editor=RuntimeError("boom")))
    assert ins.verified and ins.text == template_draft(FACTS, _info())
    assert "writer rewrite rejected" in ins.verifier_notes and "editor returned no text" in ins.verifier_notes
    assert _agents(trace) == ["Interpreter", "Writer", "Verifier", "Editor", "Fallback"]


def test_published_text_always_passes_verifier_and_matches_explain_semantics():
    info = _info()
    for llm in (Scripted(HONEST), Scripted(LIE, HONEST), Scripted(LIE, LIE), Scripted("")):
        ins, _ = _run(llm)
        assert ins.verified == verify(ins, FACTS, info, {23}).ok
        assert ins.fact_ids == [f.fact_id for f in FACTS]
        ref = explain(MOMENT, FACTS, info, Viewer(club_id="H"), llm=Scripted(LIE), minute=23)
        assert ins.insight_id == ref.insight_id and ins.confidence == ref.confidence
        assert ("rejected" in ins.verifier_notes) == ("rewrite rejected" in ins.verifier_notes)


def test_trace_steps_are_well_formed():
    _, trace = _run(Scripted(LIE, HONEST))
    assert all(isinstance(s, TraceStep) and s.ms >= 0 and s.action for s in trace)
    interp = trace[0]
    assert "lead=['f1', 'f2']" in interp.output_summary and "viewer's club Kestrel Vale" in interp.output_summary


def test_interpreter_angle_reaches_writer_without_dropping_facts():
    llm = Scripted(HONEST)
    _run(llm, viewer=Viewer(audience="analyst", player_id="h0"))
    p = llm.calls[0]
    assert "lead with the number" in p["angle"] and "Tomas Okafor" in p["angle"]
    assert [f["id"] for f in p["facts"]] == ["f1", "f2"] and p["lead_facts"] == ["f1", "f2"]


def test_default_stub_model_is_verified():
    ins, _trace = run_moment(MOMENT, FACTS, _info())
    assert ins.verified and ins.verifier_notes == "verified first time"


def test_runs_inside_a_running_event_loop():
    async def inside():
        return run_moment(MOMENT, FACTS, _info(), Viewer(), Scripted(HONEST), 23)
    ins, trace = asyncio.run(inside())
    assert ins.verified and ins.text == HONEST and _agents(trace) == ["Interpreter", "Writer", "Verifier"]


def test_workflow_crash_still_publishes_grounded_draft(monkeypatch):
    def broken(llm):
        raise RuntimeError("agent framework exploded")
    monkeypatch.setattr(orchestrator, "build_workflow", broken)
    ins, trace = _run(Scripted(HONEST))
    assert ins.verified and ins.text == template_draft(FACTS, _info())
    assert "orchestrator error (RuntimeError)" in ins.verifier_notes
    assert _agents(trace) == ["Orchestrator", "Fallback"] and trace[0].ok is False


def test_never_raises_even_if_fallback_cannot_build(monkeypatch):
    monkeypatch.setattr(orchestrator, "build_workflow", lambda llm: 1 / 0)
    monkeypatch.setattr(orchestrator, "template_draft", lambda facts, info: 1 / 0)
    ins, _trace = _run(Scripted(HONEST))
    assert not ins.verified and ins.status == "rejected" and "rejected" in ins.verifier_notes


def test_concurrent_moments_do_not_share_state():
    from concurrent.futures import ThreadPoolExecutor
    llms = [Scripted(HONEST) if i % 2 else Scripted(LIE, HONEST) for i in range(16)]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(_run, llms))
    for i, (ins, trace) in enumerate(results):
        assert ins.verified and ins.text == HONEST
        assert len(trace) == (3 if i % 2 else 5)
