from pop.agents.verifier import verify
from pop.schema import Fact, Insight, MatchInfo, Player, Team


def _info():
    def squad(prefix, names):
        return [Player(player_id=f"{prefix}{i}", name=n, number=i + 1, position="MF") for i, n in enumerate(names)]
    home = Team(team_id="H", name="Kestrel Vale", short="KVA", style="high_press", colour="#123",
                squad=squad("h", ["Tomas Okafor", "Lindiwe Mabaso"]))
    away = Team(team_id="A", name="Harbour Rovers", short="HRO", style="low_block", colour="#456",
                squad=squad("a", ["Ivo Brandt", "Samir Haddad"]))
    return MatchInfo(match_id="m", seed=1, competition="Synthetic League", venue="Riverside", home=home, away=away)


def _fact(fid, subject, value, kind="xg_player", sk="player"):
    return Fact(fact_id=fid, seq_at=10, kind=kind, subject_kind=sk, subject_id=subject, value=value,
                evidence=["m:00010"], computed_by="engine v0.1")


def _ins(text, ids):
    return Insight(insight_id="i", moment_id="mo", audience="fan", text=text, fact_ids=ids)


def test_grounded_insight_passes():
    f = _fact("f1", "h0", 0.42)
    v = verify(_ins("Okafor's chance was worth 0.42 expected goals.", ["f1"]), [f], _info())
    assert v.ok, v.reasons


def test_percentage_form_of_a_share_passes():
    f = _fact("f1", "H", 0.61, kind="possession", sk="team")
    v = verify(_ins("Kestrel Vale have had 61% of the ball.", ["f1"]), [f], _info())
    assert v.ok, v.reasons


def test_invented_number_is_rejected():
    f = _fact("f1", "h0", 0.42)
    v = verify(_ins("Okafor's chance was worth 0.42 xG, his 5th of the night.", ["f1"]), [f], _info())
    assert not v.ok and any("number 5" in r for r in v.reasons)


def test_uncited_player_is_rejected():
    f = _fact("f1", "h0", 0.42)
    v = verify(_ins("Okafor shot after a pass from Haddad.", ["f1"]), [f], _info())
    assert not v.ok and any("Samir Haddad" in r for r in v.reasons)


def test_uncited_team_is_rejected():
    f = _fact("f1", "h0", 0.42)
    v = verify(_ins("Harbour Rovers were cut open.", ["f1"]), [f], _info())
    assert not v.ok


def test_missing_and_unknown_fact_ids_are_rejected():
    assert not verify(_ins("A big moment.", []), [], _info()).ok
    assert not verify(_ins("A big moment.", ["nope"]), [], _info()).ok


def test_clock_minute_is_allowed_when_supplied():
    f = _fact("f1", "h0", 0.42)
    v = verify(_ins("In the 67th minute, Okafor's chance was worth 0.42.", ["f1"]), [f], _info(), minutes={67})
    assert v.ok, v.reasons
