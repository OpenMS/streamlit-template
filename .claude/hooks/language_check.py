#!/usr/bin/env python3
"""Stop hook: does the final message contain vocabulary the user never reads?

**Log-only for now. It blocks nothing.** The patterns it carries were measured
against saved build screens, not live messages, and every checker written for
this framework so far has needed two to five corrections before it stopped
misfiring. Doing that in front of a user is not acceptable, so the first
deployment records what it *would* have blocked and lets the turn through.

To enforce, set "enforce": true in .claude/language.json. The hook then exits 2
with the offending term, which feeds back to the model as a reason to restate --
it cannot rewrite the message silently, only ask for another.

Known false positive, unfixed on purpose: the rules govern volunteered
narration, and CONTEXT.md is explicit that "none of this governs what you say
when asked directly." A user who asks what the gate is should get an answer
containing the word. The log will show how often that happens before anything
starts blocking on it.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / ".claude" / "language.json"
LOG = ROOT / ".claude" / "language-violations.jsonl"


def last_assistant_text(transcript: Path) -> str:
    """The final assistant message, which is what the user just read."""
    text = ""
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "assistant":
            continue
        content = (event.get("message") or {}).get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = [b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
            if any(p.strip() for p in parts):
                text = "\n".join(parts)
    return text


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    transcript = payload.get("transcript_path")
    if not transcript or not Path(transcript).exists() or not CATALOG.exists():
        return 0

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    said = last_assistant_text(Path(transcript))
    if not said.strip():
        return 0

    hits = []
    for pattern, instead in catalog.get("case_insensitive", {}).items():
        for m in re.finditer(pattern, said, re.I):
            hits.append({"term": m.group(0), "instead": instead})
    for pattern, instead in catalog.get("case_sensitive", {}).items():
        for m in re.finditer(pattern, said):
            hits.append({"term": m.group(0), "instead": instead})

    if not hits:
        return 0

    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "at": datetime.now().isoformat(timespec="seconds"),
                "session": payload.get("session_id", ""),
                "hits": hits,
                "said": said[:400],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass

    if not catalog.get("enforce"):
        return 0

    terms = ", ".join(sorted({h["term"] for h in hits}))
    instead = "; ".join(sorted({h["instead"] for h in hits}))
    print(f"That turn used vocabulary the user never reads: {terms}. "
          f"Say instead: {instead}. Restate it in their terms.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
