#!/usr/bin/env python3
"""Copy the canonical application payload into a destination directory.

Reads installer/common/app_payload.txt (the shared list of app files/dirs) and
copies each entry into <dest>. Used by both the Windows and macOS installer
workflows so the bundled app payload is identical across platforms.

Directories are merged into <dest> (existing destination is fine); files are
copied verbatim. Platform-specific pieces (Python, OpenMS binaries, share/, the
launcher) are added separately by each workflow and are intentionally not part
of the payload list.

Usage:
    python installer/common/collect_payload.py <dest>
"""
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_LIST = REPO_ROOT / "installer" / "common" / "app_payload.txt"


def read_entries() -> list[str]:
    entries = []
    for line in PAYLOAD_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    return entries


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: collect_payload.py <dest>")
    dest = Path(sys.argv[1])
    dest.mkdir(parents=True, exist_ok=True)

    for entry in read_entries():
        src = REPO_ROOT / entry
        target = dest / entry
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=True)
            print(f"copied dir  {entry}")
        elif src.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            print(f"copied file {entry}")
        else:
            sys.exit(f"payload entry not found: {entry}")


if __name__ == "__main__":
    main()
