"""PostToolUse hook: check the license of every dependency an edit adds.

Runs after Edit, MultiEdit, Write and NotebookEdit. When the edited file is a
dependency file (requirements*.txt, conda-requirements.txt, package.json), it
compares the file with HEAD, looks up the license of each new or re-pinned
dependency and tells Claude where to attribute it. A license that is not
plainly permissive and has no reviewed entry in dependency-licenses.json is
reported as a block: the edit stays, and Claude is asked to read the license
and record the decision, or to pick another package.

The same check runs in CI on every pull request (dependency-licenses.yml), so
a dependency added another way (``npm install``, a hand edit) is caught there.

Standard library only; reads the hook payload from stdin. Never fails the
tool call on its own error: a broken check prints nothing and exits 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root(path: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(out.stdout.strip())


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return 0

    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".")
    path = Path(file_path)
    if not path.is_absolute():
        path = (Path(payload.get("cwd") or project) / path).resolve()

    sys.path.insert(0, str(project))
    try:
        from utils import dependency_licenses as dl
    except ImportError:
        return 0
    if not dl.is_dependency_file(path.as_posix()):
        return 0

    root = _repo_root(path) or project
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        findings = dl.run(root, files=[rel])
    except Exception:  # noqa: BLE001 - a hook must never break the edit
        return 0
    if not findings:
        return 0

    report = dl.render(findings)
    if any(f.fails for f in findings):
        out = {
            "decision": "block",
            "reason": (
                f"{rel} adds dependencies whose license needs a decision.\n\n{report}"
            ),
        }
    else:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"Dependency licenses for the change to {rel}:\n\n{report}\n\n"
                    "Make sure each one is attributed where it says, and mention "
                    "the new dependencies and their licenses in the pull request."
                ),
            }
        }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
