#!/usr/bin/env bash
# Turns the OpenMS packages an app's desktop build ran on into installers of
# the command line tools, one per platform, named so a release lists them
# apart from the app's own installers (src/common/installers.py):
#   <app>-command-line-tools-Windows-x86_64.exe   per-user installer, tools on PATH
#   <app>-command-line-tools-macOS-arm64.pkg      installs to /Applications/OpenMS-<version>
#   <app>-command-line-tools-Linux-x86_64.deb     apt install ./<file>
#
#   package-tools.sh <app name> <in dir> <out dir> [label]
# <in dir> holds one folder per platform (openms-Windows-x86_64/, ...), as
# actions/download-artifact leaves the openms-<platform> artifacts of
# .github/workflows/openms.yml: openms-package.zip on Windows (its
# openms-package/{bin,share}), the .pkg on macOS, the .deb on Linux. A folder
# may hold a released installer instead (OpenMS-<version>-Win64.exe), which is
# renamed only. <label> says what was built (owner/repo@commit) and goes into
# the Windows installer. Needs unzip and makensis (apt install nsis) for the
# Windows installer; runs on Linux.
set -euo pipefail

app="$1"
in="$2"
out="$3"
label="${4:-OpenMS}"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
nsi="$here/../tools/command-line-tools.nsi"
mkdir -p "$out"
# makensis runs in the .nsi's folder, so the installer path must be absolute.
out=$(cd "$out" && pwd)
made=0

first() { find "$1" -maxdepth 2 -type f -name "$2" 2>/dev/null | head -n 1; }

for dir in "$in"/*/; do
  dir=${dir%/}
  platform=${dir##*/}
  platform=${platform#openms-}
  target="$out/$app-command-line-tools-$platform"
  case "$platform" in
    Windows-x86_64)
      if zip=$(first "$dir" '*.zip') && [[ -n "$zip" ]]; then
        tmp=$(mktemp -d)
        unzip -q "$zip" -d "$tmp"
        src=$(dirname "$(find "$tmp" -maxdepth 3 -type d -name bin | head -n 1)")
        [[ -d "$src/bin" && -d "$src/share/OpenMS" ]] || { echo "::error::$zip has no bin/ and share/OpenMS/"; exit 1; }
        n=$(find "$src/bin" -maxdepth 1 -name '*.exe' | wc -l)
        echo "Windows: $n programs from $(basename "$zip")"
        makensis -V2 -INPUTCHARSET UTF8 \
          "-DAPP_NAME=$app" "-DSRC=$src" "-DOUT=$target.exe" "-DLABEL=$label" "$nsi"
        rm -rf "$tmp"
      elif exe=$(first "$dir" '*.exe') && [[ -n "$exe" ]]; then
        cp "$exe" "$target.exe"
      else
        echo "::error::no OpenMS package for Windows in $dir"; exit 1
      fi
      ;;
    macOS-arm64)
      pkg=$(first "$dir" '*.pkg')
      [[ -n "$pkg" ]] || { echo "::error::no .pkg in $dir"; exit 1; }
      cp "$pkg" "$target.pkg"
      ;;
    Linux-x86_64)
      deb=$(first "$dir" '*.deb')
      [[ -n "$deb" ]] || { echo "::error::no .deb in $dir"; exit 1; }
      cp "$deb" "$target.deb"
      ;;
    *) echo "skipping $dir: no installer for $platform"; continue ;;
  esac
  made=$((made + 1))
done

[[ $made -gt 0 ]] || { echo "::error::no OpenMS packages in $in"; exit 1; }
ls -lh "$out"
