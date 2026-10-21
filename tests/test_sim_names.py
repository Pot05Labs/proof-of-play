"""pop.sim must only use fictional names: no real Premier League clubs or grounds."""

from __future__ import annotations

from functools import cache

from pop.sim import generate

# Superset of recent top-flight clubs plus well-known grounds.
DENYLIST = [
    "Arsenal",
    "Aston Villa",
    "Bournemouth",
    "Brentford",
    "Brighton",
    "Burnley",
    "Chelsea",
    "Crystal Palace",
    "Everton",
    "Fulham",
    "Leeds",
    "Liverpool",
    "Manchester City",
    "Manchester United",
    "Man City",
    "Man United",
    "Newcastle",
    "Nottingham Forest",
    "Sunderland",
    "Tottenham",
    "Hotspur",
    "West Ham",
    "Wolverhampton",
    "Wolves",
    "Leicester",
    "Ipswich",
    "Southampton",
    "Luton",
    "Sheffield United",
    "Premier League",
    "Anfield",
    "Old Trafford",
    "Emirates",
    "Etihad",
    "Stamford Bridge",
    "Goodison",
    "Villa Park",
    "St James' Park",
    "Selhurst",
    "Craven Cottage",
    "London Stadium",
    "Molineux",
    "Elland Road",
    "Turf Moor",
    "Gtech",
    "Amex",
    "Vitality Stadium",
    "City Ground",
    "Stadium of Light",
]
FORBIDDEN_SUFFIXES = (" United", " City", " Albion", " Hotspur", " Palace", " Forest", " Villa", " Wanderers")


@cache
def match(seed: int, home: str, away: str):
    return generate(seed, home, away, var_overturn=seed % 2 == 0)


def _texts():
    styles = ["high_press", "possession", "low_block", "direct"]
    for seed in range(40):
        info, events = match(seed, styles[seed % 4], styles[(seed + 1) % 4])
        yield info.model_dump_json()
        if seed < 4:
            yield "\n".join(e.model_dump_json() for e in events)


def test_no_real_club_or_ground_names():
    for text in _texts():
        low = text.lower()
        for name in DENYLIST:
            assert name.lower() not in low, name


def test_club_names_avoid_real_club_suffixes():
    for seed in range(40):
        info, _ = match(seed, "high_press", "low_block")
        for team in (info.home, info.away):
            assert not team.name.endswith(FORBIDDEN_SUFFIXES), team.name


def test_squads_are_well_formed_and_varied():
    info, _ = match(1, "high_press", "low_block")
    assert info.home.team_id != info.away.team_id and info.home.name != info.away.name
    names = [p.name for t in (info.home, info.away) for p in t.squad]
    assert len(set(names)) == len(names) == 36
    for team in (info.home, info.away):
        assert len(team.squad) == 18
        assert sum(p.starter for p in team.squad) == 11
        assert [p.position for p in team.squad if p.starter].count("GK") == 1
        assert len({p.number for p in team.squad}) == 18
        assert len({p.player_id for p in team.squad}) == 18
    surnames = {
        n.split(" ", 1)[1]
        for s in range(10)
        for t in match(s, "direct", "possession")[0].model_dump()["home"]["squad"]
        for n in [t["name"]]
    }
    african = {
        "Mokoena",
        "Dlamini",
        "Nkosi",
        "Ndlovu",
        "Khumalo",
        "Mensah",
        "Osei",
        "Okonkwo",
        "Mwangi",
        "Moyo",
        "Ndiaye",
        "Banda",
        "Okello",
    }
    assert surnames & african
