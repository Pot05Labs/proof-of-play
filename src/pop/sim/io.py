"""Write a simulated match to disk: match.json plus events.jsonl (one event per line)."""

from __future__ import annotations

from pathlib import Path

from pop.schema import MatchEvent, MatchInfo


def write_match(info: MatchInfo, events: list[MatchEvent], out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    match_path = out / "match.json"
    events_path = out / "events.jsonl"
    match_path.write_text(info.model_dump_json(indent=2) + "\n", encoding="utf-8")
    with events_path.open("w", encoding="utf-8", newline="\n") as fh:
        for ev in events:
            fh.write(ev.model_dump_json() + "\n")
    return match_path, events_path
