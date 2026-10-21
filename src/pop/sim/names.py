"""Fictional clubs, players, competitions and venues.

Every name here is invented. Club names deliberately avoid suffixes that identify real
English top-flight clubs (United, City, Albion, Hotspur, Palace, Forest, Villa, Wanderers).
"""

from __future__ import annotations

import numpy as np

from pop.schema import Player, Team

CLUB_PLACES = [
    "Kestrel Bay",
    "Ashvale",
    "Port Elandra",
    "Riverhaven",
    "Calder Heights",
    "Marlow Fen",
    "Saltmere",
    "Ember Vale",
    "Highcliff",
    "Lindenmoor",
    "Greywater",
    "Stormhaven",
    "Brackenridge",
    "Copperton",
    "Falconridge",
    "Harrowmere",
    "Kopanong Ridge",
    "Umzali",
    "Lake Nyanza Shore",
    "Tamarind Coast",
    "Sable Point",
    "Juniper Hollow",
    "Ostrava Quay",
    "Cedar Narrows",
]
CLUB_SUFFIXES = ["FC", "Athletic", "Rovers", "Town", "Harriers", "Dynamos", "Sporting", "Mariners", "Comets"]
VENUE_KINDS = ["Arena", "Park", "Ground", "Stadium", "Fields"]
COMPETITIONS = [
    "Meridian Super League",
    "Atlas Continental Cup",
    "Halcyon First Division",
    "Solstice Champions Series",
]
COLOURS = [
    "#1f4e9c",
    "#b3202a",
    "#0f7a4a",
    "#f2b705",
    "#6a2c91",
    "#e86a10",
    "#0b0b0b",
    "#ffffff",
    "#2bb3c0",
    "#7a1f3d",
]

FIRST_NAMES = [
    "Sipho",
    "Thabo",
    "Lwazi",
    "Themba",
    "Kagiso",
    "Tshepo",
    "Mpho",
    "Kwame",
    "Kofi",
    "Yaw",
    "Chidi",
    "Emeka",
    "Tunde",
    "Amadou",
    "Moussa",
    "Ismaila",
    "Abdou",
    "Tendai",
    "Farai",
    "Youssef",
    "Hakim",
    "Juma",
    "Baraka",
    "Otieno",
    "Mateus",
    "Diego",
    "Thiago",
    "Santiago",
    "Mateo",
    "Andres",
    "Rafael",
    "Jonas",
    "Lars",
    "Henrik",
    "Mikkel",
    "Tomasz",
    "Piotr",
    "Luka",
    "Marko",
    "Dario",
    "Julien",
    "Hugo",
    "Elias",
    "Finn",
    "Oisin",
    "Callum",
    "Ethan",
    "Kenji",
    "Haruto",
    "Arjun",
    "Rohan",
    "Omar",
    "Tariq",
    "Selim",
    "Emre",
    "Kaan",
    "Noah",
    "Aiden",
    "Samir",
    "Ruben",
]
SURNAMES = [
    "Mokoena",
    "Dlamini",
    "Nkosi",
    "Ndlovu",
    "Khumalo",
    "Mahlangu",
    "Sithole",
    "Molefe",
    "Mensah",
    "Asante",
    "Owusu",
    "Okonkwo",
    "Nwosu",
    "Adebayo",
    "Okeke",
    "Ndiaye",
    "Sow",
    "Camara",
    "Mwangi",
    "Otieno",
    "Moyo",
    "Chikwanha",
    "Haddad",
    "Benali",
    "Mansouri",
    "Carvalho",
    "Moreira",
    "Castillo",
    "Herrera",
    "Paredes",
    "Quintero",
    "Ibarra",
    "Lindqvist",
    "Halvorsen",
    "Bergstrom",
    "Nyberg",
    "Kowalski",
    "Zielinski",
    "Horvat",
    "Petrovic",
    "Marchetti",
    "Ricci",
    "Moreau",
    "Girard",
    "Fontaine",
    "O'Connell",
    "Brennan",
    "Whitlock",
    "Ashworth",
    "Tanaka",
    "Watanabe",
    "Demir",
    "Aydin",
    "Yilmaz",
    "Iyer",
    "Rao",
    "Vasquez",
    "Achterberg",
    "Okello",
    "Banda",
]

# Squad shape: 11 starters (4-3-3) then a 7-player bench.
STARTER_SHAPE = ["GK", "DF", "DF", "DF", "DF", "MF", "MF", "MF", "FW", "FW", "FW"]
BENCH_SHAPE = ["GK", "DF", "DF", "MF", "MF", "FW", "FW"]
NUMBERS = {
    "GK": [1, 13, 31],
    "DF": [2, 3, 4, 5, 6, 12, 15, 22],
    "MF": [8, 10, 14, 16, 18, 21, 23],
    "FW": [7, 9, 11, 17, 19, 20, 27],
}


def _pick(rng: np.random.Generator, pool: list[str]) -> str:
    return pool[int(rng.integers(0, len(pool)))]


def _player_names(rng: np.random.Generator, n: int, taken: set[str]) -> list[str]:
    out: list[str] = []
    while len(out) < n:
        name = f"{_pick(rng, FIRST_NAMES)} {_pick(rng, SURNAMES)}"
        if name not in taken:
            taken.add(name)
            out.append(name)
    return out


def _squad(rng: np.random.Generator, team_code: str, taken: set[str]) -> list[Player]:
    shape = STARTER_SHAPE + BENCH_SHAPE
    names = _player_names(rng, len(shape), taken)
    used: dict[str, int] = {"GK": 0, "DF": 0, "MF": 0, "FW": 0}
    squad = []
    for i, (pos, name) in enumerate(zip(shape, names, strict=True)):
        number = NUMBERS[pos][used[pos]]
        used[pos] += 1
        squad.append(
            Player(
                player_id=f"{team_code}-{number:02d}",
                name=name,
                number=number,
                position=pos,  # type: ignore[arg-type]
                starter=i < len(STARTER_SHAPE),
            )
        )
    return squad


def build_teams(rng: np.random.Generator, home_style: str, away_style: str) -> tuple[Team, Team, str, str]:
    """Return (home, away, competition, venue), all fictional and seeded."""
    places = rng.permutation(len(CLUB_PLACES))[:2]
    colours = rng.permutation(len(COLOURS))[:2]
    taken: set[str] = set()
    teams = []
    for k, style in enumerate((home_style, away_style)):
        place = CLUB_PLACES[int(places[k])]
        suffix = _pick(rng, CLUB_SUFFIXES)
        letters = "".join(ch for ch in place.upper() if ch.isalpha())
        short = (letters[:2] + suffix[0]).upper()
        if k == 1 and short == teams[0].short:
            short = letters[:3]
        team_code = ("h" if k == 0 else "a") + short.lower()
        teams.append(
            Team(
                team_id=team_code,
                name=f"{place} {suffix}",
                short=short,
                style=style,  # type: ignore[arg-type]
                colour=COLOURS[int(colours[k])],
                squad=_squad(rng, team_code, taken),
            )
        )
    home_place = teams[0].name.rsplit(" ", 1)[0]
    venue = f"{home_place} {_pick(rng, VENUE_KINDS)}"
    competition = _pick(rng, COMPETITIONS)
    return teams[0], teams[1], competition, venue
