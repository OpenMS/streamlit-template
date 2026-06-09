#!/usr/bin/env python3
"""Print the python-build-standalone download URL for a Python minor version.

Selects the relocatable arm64 macOS "install_only" build (ships pip + ensurepip,
so `pip install -r requirements.txt` works directly inside it).

Usage:
    find_pbs_url.py <minor e.g. 3.11> <releases-json-file>
"""
import json
import sys


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: find_pbs_url.py <minor> <releases-json-file>")
    minor = sys.argv[1]
    with open(sys.argv[2], encoding="utf-8") as f:
        data = json.load(f)
    candidates = [
        asset["browser_download_url"]
        for asset in data.get("assets", [])
        if asset["name"].startswith("cpython-" + minor + ".")
        and "aarch64-apple-darwin" in asset["name"]
        and asset["name"].endswith("install_only.tar.gz")
    ]
    if not candidates:
        sys.exit(f"no python-build-standalone install_only asset for {minor}")
    print(candidates[0])


if __name__ == "__main__":
    main()
