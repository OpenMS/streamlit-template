#!/usr/bin/env python3
"""Set the app version and force offline deployment in settings.json.

Shared by the Windows (build-windows-executable-app) and macOS
(build-macos-dmg-app) installer workflows so the two pipelines stay in sync.
Uses only the standard library so it runs under the runner's system Python on
every platform.

Examples:
    python installer/common/set_app_version.py --version "1.2.3"
    python installer/common/set_app_version.py --offline
    python installer/common/set_app_version.py --version "1.2.3" --offline
"""
import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", default="settings.json",
                        help="Path to settings.json (default: settings.json)")
    parser.add_argument("--version", default="",
                        help="Version string to write (e.g. a release tag). "
                             "Ignored when empty so non-release builds keep the "
                             "version already in settings.json.")
    parser.add_argument("--offline", action="store_true",
                        help="Set online_deployment to false for a local build.")
    args = parser.parse_args()

    with open(args.settings, "r", encoding="utf-8") as f:
        settings = json.load(f)

    if args.version:
        settings["version"] = args.version
    if args.offline:
        settings["online_deployment"] = False

    with open(args.settings, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)
        f.write("\n")


if __name__ == "__main__":
    main()
