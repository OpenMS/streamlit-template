#!/usr/bin/env bash
# Stages a relocatable CPython (python-build-standalone, the builds uv uses)
# with the app's requirements for the Electron app, the same way on all three
# platforms:
#   <out>/python-<version>/python.exe     (Windows)
#   <out>/python-<version>/bin/python3    (macOS, Linux)
# The interpreter has its development headers, so pip builds any native
# extension in place, and it ships tkinter (the local file dialog).
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
  MINGW*-x86_64|MSYS*-x86_64|CYGWIN*-x86_64) triple=x86_64-pc-windows-msvc ;;
  *) echo "::error::unsupported platform $(uname -s)-$(uname -m)"; exit 1 ;;
esac

tag="${PBS_RELEASE:-$(gh release view -R "$repo" --json tagName -q .tagName)}"
# The stripped build has no debug symbols (the Linux interpreter and
# libpython are about 70 MB smaller); the unstripped one is the fallback.
assets=$(gh release view "$tag" -R "$repo" --json assets -q '.assets[].name')
asset=""
for flavour in install_only_stripped install_only; do
  asset=$(grep -E "^cpython-${version//./\\.}\.[0-9]+\+${tag}-${triple}-${flavour}\.tar\.gz$" <<<"$assets" | head -n 1 || true)
  [[ -z "$asset" ]] || break
done
[[ -n "$asset" ]] || { echo "::error::no CPython ${version} for ${triple} in ${repo} ${tag}"; exit 1; }

dl=$(mktemp -d)
gh release download "$tag" -R "$repo" --pattern "$asset" --dir "$dl"
mkdir -p "$out"
tar -xzf "$dl/$asset" -C "$dl"
dest="$out/python-${version}"
rm -rf "$dest"
mv "$dl/python" "$dest"
if [[ $triple == *windows* ]]; then py="$dest/python.exe"; else py="$dest/bin/python3"; fi
echo "Staged $asset as $dest"

"$py" -m pip install --upgrade --no-warn-script-location --disable-pip-version-check -r "$requirements"

# DuckDB's extension wheels (pulled in by some dependencies) append DuckDB's
# own signature to a Mach-O file, which codesign rejects ("main executable
# failed strict validation") after the hours-long signing step. Without them,
# DuckDB downloads an extension on first use.
if [[ $triple == *apple-darwin ]]; then
  ext=$("$py" -m pip list --format freeze --disable-pip-version-check | cut -d= -f1 | grep -iE '^duckdb[-_]extension' || true)
  [[ -z "$ext" ]] || "$py" -m pip uninstall -y --disable-pip-version-check $ext
  left=$(find "$dest" -name '*.duckdb_extension' | head -n 5)
  [[ -z "$left" ]] || { echo "::error::DuckDB extensions would fail macOS signing: $left"; exit 1; }
fi

# Drop caches, test suites and files the app never loads.
site=$("$py" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
command -v cygpath >/dev/null && site=$(cygpath -u "$site")
find "$site" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$site" -type d \( -name tests -o -name test \) -prune -exec rm -rf {} +
# Jupyter extensions (plotly's) and Windows debug databases are never loaded.
rm -rf "$dest/share/jupyter"
find "$dest" -name '*.pdb' -type f -delete

# Compile the bytecode now on macOS and Linux: the shell runs Python with
# PYTHONDONTWRITEBYTECODE there, because the signed macOS bundle and the
# AppImage cannot be written to. unchecked-hash .pyc files stay valid whatever
# timestamps packaging gives the sources. The Windows install directory is
# writable and Python writes its bytecode on first use, which keeps the NSIS
# installer (limited to 2 GB) smaller.
if [[ $triple != *windows* ]]; then
  "$py" -m compileall -q -j 0 --invalidation-mode unchecked-hash "$dest/lib" >/dev/null || true
fi

# pyOpenMS and scikit-learn each bundle libomp.dylib. Two copies in one process
# abort it ("OMP: Error #15", or #179 when duplicates are allowed), so every
# other copy becomes a link to pyOpenMS's, which dyld then loads only once.
# pyOpenMS needs its own copy: an older libomp (scikit-learn's) lacks symbols
# it uses (___kmpc_dispatch_deinit). From 3.6 the wheel keeps it in .dylibs/.
if [[ $triple == *apple-darwin ]]; then
  keep=$(find "$site/pyopenms" -name libomp.dylib -type f 2>/dev/null | head -n 1)
  find "$site" -name libomp.dylib -type f | while read -r lib; do
    [[ -n $keep ]] || keep=$lib
    [[ $lib == "$keep" ]] && continue
    rel=$("$py" -c 'import os, sys; print(os.path.relpath(sys.argv[1], os.path.dirname(sys.argv[2])))' "$keep" "$lib")
    echo "$lib -> $rel"
    ln -sf "$rel" "$lib"
  done
fi
