"""CLI: uv run python -m pop.sim --seed 7 --out data/out/match_7"""

from __future__ import annotations

import argparse
from collections import Counter

from .io import write_match
from .match import generate
from .styles import STYLES


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pop.sim", description="Generate a synthetic match.")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True, help="output directory for match.json and events.jsonl")
    ap.add_argument("--home-style", default="high_press", choices=sorted(STYLES))
    ap.add_argument("--away-style", default="low_block", choices=sorted(STYLES))
    ap.add_argument("--var-overturn", action="store_true", help="include a goal that VAR overturns")
    args = ap.parse_args(argv)
    info, events = generate(args.seed, args.home_style, args.away_style, var_overturn=args.var_overturn)
    match_path, events_path = write_match(info, events, args.out)
    counts = Counter(e.type.value for e in events)
    print(f"{info.match_id}: {info.home.name} v {info.away.name} at {info.venue} ({info.competition})")
    print(f"{len(events)} events -> {events_path}; squads -> {match_path}")
    print(", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
