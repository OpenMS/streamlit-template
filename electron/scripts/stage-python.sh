#!/usr/bin/env bash
# Stages a relocatable CPython (python-build-standalone, the builds uv uses)
# with the app's requirements for the macOS or Linux Electron app:
#   <out>/python-<version>/bin/python3
# The Windows build uses python.org's embeddable zip instead; there is no such
# distribution for macOS and Linux.
#
#   stage-python.sh <python minor version, e.g. 3.11> <out dir> <requirements.txt>
# Needs gh (GH_TOKEN). PBS_RELEASE pins a python-build-standalone release tag
# (default: the latest release).
set -euo pipefail

version="$1"
out="$2"
requirements="$3"
repo=astral-sh/python-build-standalone

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) triple=aarch64-apple-darwin ;;
  Linux-x86_64) triple=x86_64-unknown-linux-gnu ;;
  *) echo "::error::unsupported platform $(uname -s)-$(uname -m)"; exit 1 ;;
esac

tag="${PBS_RELEASE:-$(gh release view -R "$repo" --json tagName -q .tagName)}"
asset=$(gh release view "$tag" -R "$repo" --json assets -q '.assets[].name' |
  grep -E "^cpython-${version//./\\.}\.[0-9]+\+${tag}-${triple}-install_only\.tar\.gz$" | head -n 1 || true)
[[ -n "$asset" ]] || { echo "::error::no CPython ${version} for ${triple} in ${repo} ${tag}"; exit 1; }

dl=$(mktemp -d)
gh release download "$tag" -R "$repo" --pattern "$asset" --dir "$dl"
mkdir -p "$out"
tar -xzf "$dl/$asset" -C "$dl"
dest="$out/python-${version}"
rm -rf "$dest"
mv "$dl/python" "$dest"
py="$dest/bin/python3"
echo "Staged $asset as $dest"

"$py" -m pip install --upgrade --no-warn-script-location --disable-pip-version-check -r "$requirements"

# Same clean-up as the Windows build, then compile the bytecode now: the shell
# runs Python with PYTHONDONTWRITEBYTECODE because the signed macOS bundle and
# the AppImage cannot be written to. unchecked-hash .pyc files stay valid
# whatever timestamps packaging gives the sources.
site=$("$py" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
find "$site" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$site" -type d \( -name tests -o -name test \) -prune -exec rm -rf {} +
"$py" -m compileall -q -j 0 --invalidation-mode unchecked-hash "$dest/lib" >/dev/null || true
