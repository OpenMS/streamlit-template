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
BEAT = ROOT / ".claude" / "language-check-ran"


# The evaluation harness interviews a finished build about how it went. Those
# answers are addressed to the harness, not to the user, and discuss the
# framework's own mechanics by design -- the first violation this hook ever
# logged was a debrief answer naming `interview` and `preflight`, which is
# correct English for what it was doing. Enforcing here would have blocked every
# debrief and read as the model failing to comply.
#
# The harness writes this marker into the session before it asks anything, so
# the boundary is already in the transcript. Real users never see it.
DEBRIEF_MARKER = "DEBRIEF-BEGIN-8f2c1a"


def in_debrief(transcript: Path) -> bool:
    """Has the harness started interviewing this session?"""
    try:
        return DEBRIEF_MARKER in transcript.read_text(encoding="utf-8",
                                                      errors="replace")
    except OSError:
        return False


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


def beat() -> None:
    """Record that the hook ran, before anything can return early.

    This is proof of invocation, so it must not sit behind a check that can
    skip it. Placed after the transcript checks it recorded one turn out of
    eight -- the other seven returned early and looked identical to the hook
    never having run, which is the exact ambiguity it exists to remove. That
    was diagnosed once and left in place; this is the correction.
    """
    try:
        n = 0
        if BEAT.exists():
            n = int(BEAT.read_text(encoding="utf-8").split()[0] or 0)
        BEAT.write_text(f"{n + 1} turns checked, last "
                        f"{datetime.now().isoformat(timespec='seconds')}\n",
                        encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    beat()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    transcript = payload.get("transcript_path")
    if not transcript or not Path(transcript).exists() or not CATALOG.exists():
        return 0

    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if in_debrief(Path(transcript)):
        return 0          # answers to the harness, not to the user

    said = last_assistant_text(Path(transcript))
    if not said.strip():
        return 0

    hits = []
    for flags, key in ((re.I, "case_insensitive"), (0, "case_sensitive")):
        for pattern, instead in catalog.get(key, {}).items():
            try:
                found = list(re.finditer(pattern, said, flags))
            except re.error:
                continue          # one bad pattern must not silence the rest
            for m in found:
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
    # A hook that raises fires on every turn. This one guards the session; it
    # must not be able to damage it. A bad regex, an unreadable catalog, a
    # transcript in an unexpected shape -- none of those are reasons to
    # interrupt the user, so anything unhandled means "allow" rather than
    # "crash". The only non-zero exit this file may produce is the deliberate
    # 2 from an enforced violation.
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        sys.exit(0)
