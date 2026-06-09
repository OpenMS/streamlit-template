#!/usr/bin/env python3
"""Shrink a bundled Python site-packages directory.

Removes __pycache__ directories and test/tests directories, mirroring the
clean-up the Windows installer used to do inline in PowerShell. Shared by both
installer workflows; each passes its own platform-specific site-packages path
(Windows: python-<ver>/Lib/site-packages, macOS: python/lib/python3.X/site-packages).

Usage:
    python installer/common/prune_site_packages.py <site-packages-dir>
"""
import shutil
import sys
from pathlib import Path

PRUNE_DIR_NAMES = {"__pycache__", "test", "tests"}


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: prune_site_packages.py <site-packages-dir>")
    root = Path(sys.argv[1])
    if not root.is_dir():
        sys.exit(f"not a directory: {root}")

    removed = 0
    # Collect first, then delete: mutating the tree while walking is unsafe.
    targets = [p for p in root.rglob("*")
               if p.is_dir() and p.name in PRUNE_DIR_NAMES]
    for path in targets:
        if path.exists():  # a parent may already have been removed
            shutil.rmtree(path, ignore_errors=True)
            removed += 1

    remaining = sum(1 for _ in root.rglob("*") if _.is_file())
    print(f"Pruned {removed} directories; {remaining} files remain in {root}")


if __name__ == "__main__":
    main()
