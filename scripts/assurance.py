"""Generate docs/ASSURANCE.md: every check, run fresh. A skipped test is a failure."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    p = subprocess.run(cmd, check=False, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> int:
    rows = []
    code, out = run(["uv", "run", "pytest", "-q", "-p", "no:warnings", "-rs",
                     "--junitxml", "data/out/junit.xml"])
    junit = (ROOT / "data/out/junit.xml").read_text() if (ROOT / "data/out/junit.xml").exists() else ""
    nums = dict(re.findall(r'(tests|failures|errors|skipped)="(\d+)"', junit))
    t, f, e, s = (int(nums.get(k, 0)) for k in ("tests", "failures", "errors", "skipped"))
    rows.append(("Python tests", code == 0 and s == 0, f"{t} run, {f} failed, {e} errors, {s} skipped"))

    code, out = run(["uv", "run", "ruff", "check", "src", "tests", "scripts"])
    rows.append(("Lint (ruff)", code == 0, out.splitlines()[-1] if out else "clean"))

    secrets = run(["git", "grep", "-nIE", r"(AccountKey=|SharedAccessKey=|-----BEGIN|sk-[A-Za-z0-9]{20}|eyJhbGci)", "--", ".", ":!scripts/assurance.py"])[1]
    rows.append(("No secrets in tracked files", not secrets, "none found" if not secrets else secrets[:200]))

    deny = ["arsenal", "chelsea", "liverpool", "tottenham", "manchester", "newcastle", "everton", "fulham",
            "brentford", "bournemouth", "wolverhampton", "nottingham", "aston villa", "crystal palace",
            "brighton", "west ham", "leicester", "ipswich", "southampton", "sunderland", "leeds", "burnley"]
    hits = run(["git", "grep", "-nIiwE", "|".join(deny), "--", "src", "web/src"])[1]
    rows.append(("No real Premier League clubs in product code", not hits, "none found" if not hits else hits[:200]))

    web = ROOT / "web"
    if (web / "package.json").exists():
        code, out = run(["npm", "test", "--silent", "--", "--run"], cwd=web)
        rows.append(("Web tests (vitest)", code == 0, out.splitlines()[-1] if out else ""))
        code, out = run(["npm", "run", "build", "--silent"], cwd=web)
        rows.append(("Web production build", code == 0, "built" if code == 0 else out[-200:]))

    ok = all(r[1] for r in rows)
    commit = run(["git", "rev-parse", "--short", "HEAD"])[1]
    lines = [
        "# Assurance report", "",
        f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} at commit `{commit}` by `scripts/assurance.py`.",
        "Every check is run fresh. A skipped test counts as a failure. The builder of a component never certifies it.",
        "", f"**Overall: {'PASS' if ok else 'FAIL'}**", "", "| Check | Result | Detail |", "|---|---|---|",
    ]
    lines += [f"| {n} | {'PASS' if p else 'FAIL'} | {d.replace('|', '/')} |" for n, p, d in rows]
    (ROOT / "docs/ASSURANCE.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"overall": ok, "checks": [(n, p) for n, p, _ in rows]}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
