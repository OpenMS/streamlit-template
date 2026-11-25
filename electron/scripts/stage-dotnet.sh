#!/usr/bin/env bash
# Stages a .NET runtime for the Electron app on Windows, macOS and Linux:
#   <out>/dotnet/   host/fxr/<version>/, shared/Microsoft.NETCore.App/<version>/
# OpenMS's FileConverter reads Thermo .raw files with its built-in reader
# (openms-thermo-bridge), which starts .NET in the tool's own process and needs
# a .NET 8 or newer runtime. CommandExecutor.convert_to_mzml() names that
# reader on every platform (Windows defaults to ThermoRawFileParser, whose mzML
# differs slightly), so the same .raw file gives the same mzML everywhere.
# Users rarely have such a runtime, so the app ships it and payload.js points
# DOTNET_ROOT at it.
#
#   stage-dotnet.sh <out dir>
# Run after stage-openms.sh. Does nothing when the staged OpenMS has no built-in
# Thermo reader (share/OpenMS/openms_thermo_bridge/managed, which
# stage-openms.sh leaves out when FileConverter is not staged). DOTNET_CHANNEL
# names the .NET release channel (default 10.0, the current long-term support
# release; the bridge rolls forward from 8.0 to any newer major version).
set -euo pipefail

out="$1"
channel="${DOTNET_CHANNEL:-10.0}"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) rid=osx-arm64 ;;
  Linux-x86_64) rid=linux-x64 ;;
  MINGW*-x86_64|MSYS*-x86_64|CYGWIN*-x86_64) rid=win-x64 ;;
  *) echo "No .NET runtime for $(uname -s)-$(uname -m)"; exit 0 ;;
esac
# Microsoft publishes the Windows runtime as a zip, the others as tar.gz.
ext=tar.gz
[[ $rid == win-* ]] && ext=zip

config="$out/share/OpenMS/openms_thermo_bridge/managed/ThermoWrapperManaged.runtimeconfig.json"
if [[ ! -f "$config" ]]; then
  echo "The staged OpenMS has no built-in Thermo reader; no .NET runtime staged"
  exit 0
fi
echo "Thermo reader runtime config:"
cat "$config"

dl=$(mktemp -d)
trap 'rm -rf "$dl"' EXIT
curl -fsSL --retry 5 --retry-all-errors -o "$dl/releases.json" \
  "https://builds.dotnet.microsoft.com/dotnet/release-metadata/${channel}/releases.json"
# jq on Windows ends its lines with CRLF; the CR would end up in the hash.
version=$(jq -r '."latest-runtime"' "$dl/releases.json" | tr -d '\r')
read -r url hash < <(jq -r --arg v "$version" --arg n "dotnet-runtime-${rid}.${ext}" \
  '.releases[] | select(.runtime.version == $v) | .runtime.files[] | select(.name == $n) | "\(.url) \(.hash)"' \
  "$dl/releases.json" | tr -d '\r' | head -n 1)
[[ -n "${url:-}" && -n "${hash:-}" ]] || { echo "::error::no dotnet-runtime-${rid}.${ext} for .NET ${version}"; exit 1; }

echo "Downloading .NET runtime ${version} (${rid})"
curl -fsSL --retry 5 --retry-all-errors -o "$dl/runtime.${ext}" "$url"
if command -v sha512sum >/dev/null; then
  actual=$(sha512sum "$dl/runtime.${ext}" | cut -d' ' -f1)
else
  actual=$(shasum -a 512 "$dl/runtime.${ext}" | cut -d' ' -f1)
fi
[[ "$actual" == "$hash" ]] || { echo "::error::SHA-512 mismatch for $url"; exit 1; }

rm -rf "$out/dotnet"
mkdir -p "$out/dotnet"
if [[ $ext == zip ]]; then
  # Git for Windows has unzip; 7-Zip is on the GitHub Windows runners too.
  if command -v unzip >/dev/null; then
    unzip -q "$dl/runtime.zip" -d "$out/dotnet"
  else
    7z x -y -bd "-o$out/dotnet" "$dl/runtime.zip" >/dev/null
  fi
else
  tar -xzf "$dl/runtime.tar.gz" -C "$out/dotnet"
fi
# The dotnet muxer is not needed to host the runtime from FileConverter, but
# it is small and lets a user check the runtime (dotnet --list-runtimes).
compgen -G "$out/dotnet/host/fxr/*/*hostfxr.*" >/dev/null ||
  { echo "::error::the .NET runtime archive has no host/fxr"; exit 1; }
echo "Staged .NET runtime ${version}: $(ls "$out/dotnet/shared/Microsoft.NETCore.App" | tr '\n' ' ')"
du -sh "$out/dotnet"
