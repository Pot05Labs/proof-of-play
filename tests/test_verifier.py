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


def test_shared_surnames_do_not_cause_false_rejections():
    info = _info()
    info.home.squad.append(Player(player_id="h9", name="Mpho Okafor", number=9, position="FW"))
    f = _fact("f1", "h0", 0.42)
    assert verify(_ins("Tomas Okafor's chance was worth 0.42.", ["f1"]), [f], info).ok
    assert not verify(_ins("Mpho Okafor's chance was worth 0.42.", ["f1"]), [f], info).ok


def test_thousands_separators_are_one_number():
    f = _fact("f1", "h0", 10000.0, kind="player_distance_milestone")
    for text in ("Tomas Okafor has covered 10,000 metres.", "Tomas Okafor has covered 10 000 metres.",
                 "Tomas Okafor has covered 10 000 metres.", "Tomas Okafor has covered 10000 metres."):
        assert verify(_ins(text, ["f1"]), [f], _info()).ok, text
    assert not verify(_ins("Tomas Okafor has covered 12,000 metres.", ["f1"]), [f], _info()).ok
    g = _fact("g1", "h0", 0.42)
    assert verify(_ins("Tomas Okafor: 0,42 expected goals.", ["g1"]), [g], _info()).ok  # comma decimal still read


def test_template_writes_whole_numbers_cleanly():
    from pop.agents.explainer import template_draft
    f = _fact("f1", "h0", 10000.0, kind="player_distance_milestone")
    assert "10000 metres" in template_draft([f], _info()) and "10000.0" not in template_draft([f], _info())


def test_score_fact_admits_both_team_names_and_drafts_name_them_home_first():
    from pop.agents.explainer import fact_rows, template_draft
    info = _info()
    score = _fact("s", info.match_id, "2-1", kind="score", sk="match")
    text = f"{info.home.name} lead {info.away.name} 2-1."
    assert verify(_ins(text, ["s"]), [score], info).ok
    assert template_draft([score], info, "recap_full_time") == f"Full time. {info.home.name} 2, {info.away.name} 1."
    assert fact_rows([score], info)[0]["subject"] == f"{info.home.name} v {info.away.name}"


def test_team_short_code_matches_only_in_capitals():
    info = _info()
    info.home.short = "HAD"  # a real seed codes Harrowmere Dynamos as HAD
    f = _fact("p", "A", 0.92, kind="possession_swing", sk="team")
    assert verify(_ins("Harbour Rovers have had 92% of the ball.", ["p"]), [f], info).ok
    assert not verify(_ins("HAD are chasing, Harbour Rovers have 92% of the ball.", ["p"]), [f], info).ok


def test_momentum_index_is_never_a_percentage():
    info = _info()
    f = _fact("m", "A", 0.375, kind="momentum_shift", sk="team")  # engine: unsigned swing towards the subject
    assert verify(_ins("Momentum has swung to Harbour Rovers, a swing of 0.38.", ["m"]), [f], info).ok
    assert not verify(_ins("Harbour Rovers have 38% of the momentum.", ["m"]), [f], info).ok
