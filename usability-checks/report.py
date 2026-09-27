"""Summarise every <app>/results.json under OUT into OUT/report.md."""

import json
import re
import sys
from pathlib import Path

out = Path(sys.argv[1])


def short(msg: str) -> str:
    """First line of an error plus the deepest app frame that raised it."""
    first = msg.splitlines()[0][:300] if msg else ""
    frames = re.findall(r'File "([^"]+)", line (\d+)', msg)
    app = [f"{Path(f).name}:{n}" for f, n in frames if "site-packages" not in f and ("/content/" in f or "/src/" in f)]
    return first + (f" (at {app[-1]})" if app else "")

lines, summary = [], []
for res_file in sorted(out.glob("*/results.json")):
    r = json.loads(res_file.read_text())
    d = res_file.parent
    name = r.get("app", d.name)
    commit = (d / "commit.txt").read_text().strip() if (d / "commit.txt").exists() else ""
    if r.get("setupError"):
        summary.append(f"- **{name}**: could not start ({r['setupError']})")
        continue
    if r.get("unreachable"):
        summary.append(f"- **{name}**: not reachable from the check environment ({r.get('url')})")
        continue
    bad = [p for p in r["pages"] + r["scenarios"] if p["failures"]]
    warn = [p for p in r["pages"] + r["scenarios"] if p["warnings"] and not p["failures"]]
    state = "OK" if not bad else f"{len(bad)} failing"
    summary.append(
        f"- **{name}**: {state}, {len(r['pages'])} page visits, {len(r['scenarios'])} scenarios"
        + (f", {len(warn)} with warnings" if warn else "")
        + (f" (commit {commit[:8]})" if commit else "")
    )
    topp = sorted({t for p in r["pages"] for t in p.get("missingTopp", [])})
    if topp:
        summary[-1] += f"; TOPP-dependent pages not exercised (no {', '.join(topp)} in the check environment)"
    if bad or warn:
        lines.append(f"\n## {name}\n")
        for p in bad:
            where = p.get("page") or p.get("name") or p.get("label")
            lines.append(f"- FAIL [{p.get('workspace', 'scenario')}] {where}: " + "; ".join(short(f) for f in p["failures"]) + f" (`{d.name}/{p['screenshot']}`)")
        for p in warn:
            where = p.get("page") or p.get("name") or p.get("label")
            lines.append(f"- warn [{p.get('workspace', 'scenario')}] {where}: " + "; ".join(short(w) for w in p["warnings"]))

report = "# OpenMS web app usability check\n\n" + "\n".join(summary) + "\n" + "\n".join(lines) + "\n"
(out / "report.md").write_text(report)
print(report)
