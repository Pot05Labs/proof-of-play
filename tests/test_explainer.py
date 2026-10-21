from pop.agents.explainer import Viewer, explain
from pop.schema import Fact, MatchInfo, Moment, Player, Team


def _info():
    def squad(prefix, names):
        return [Player(player_id=f"{prefix}{i}", name=n, number=i + 1, position="FW") for i, n in enumerate(names)]
    home = Team(team_id="H", name="Kestrel Vale", short="KVA", style="high_press", colour="#123",
                squad=squad("h", ["Tomas Okafor"]))
    away = Team(team_id="A", name="Harbour Rovers", short="HRO", style="low_block", colour="#456",
                squad=squad("a", ["Ivo Brandt"]))
    return MatchInfo(match_id="m", seed=1, competition="Synthetic League", venue="Riverside", home=home, away=away)


FACT = Fact(fact_id="f1", seq_at=5, kind="big_chance_missed", subject_kind="player", subject_id="h0",
            value=0.48, evidence=["m:00005"], computed_by="engine v0.1")
MOMENT = Moment(moment_id="mo1", seq_at=5, kind="big_chance", importance=0.8, facts=["f1"])


class LyingLLM:
    name = "liar"

    def complete(self, system, user):
        return "Okafor missed a sitter worth 0.48 xG, his 4th miss tonight, as Brandt watched."


class HonestLLM:
    name = "honest"

    def complete(self, system, user):
        return "So close for Okafor: that chance was worth 0.48 expected goals."


def test_stub_publishes_verified_template():
    ins = explain(MOMENT, [FACT], _info())
    assert ins.verified and "0.48" in ins.text and ins.fact_ids == ["f1"]


def test_honest_rewrite_is_kept():
    ins = explain(MOMENT, [FACT], _info(), Viewer(audience="fan", club_id="H"), llm=HonestLLM())
    assert ins.verified and ins.text.startswith("So close") and ins.personalised_for == {"club": "H"}


def test_hallucinating_rewrite_falls_back_to_grounded_draft():
    ins = explain(MOMENT, [FACT], _info(), llm=LyingLLM())
    assert ins.verified
    assert "4th" not in ins.text and "Brandt" not in ins.text
    assert "rejected" in ins.verifier_notes


def test_chaos_inventions_are_always_caught():
    from pop.agents.llm import ChaosLLM, StubLLM
    chaos = ChaosLLM(StubLLM(), rate=1.0, seed=1)
    for _ in range(20):
        ins = explain(MOMENT, [FACT], _info(), llm=chaos)
        assert ins.verified and "rejected" in ins.verifier_notes
        assert not any(x in ins.text for x in ChaosLLM.INVENTIONS)
