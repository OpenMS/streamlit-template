#!/usr/bin/env bash
# Stages a .NET runtime for the Electron app on macOS and Linux:
#   <out>/dotnet/   host/fxr/<version>/, shared/Microsoft.NETCore.App/<version>/
# OpenMS's FileConverter reads Thermo .raw files there with its built-in reader
# (openms-thermo-bridge), which starts .NET in the tool's own process and needs
# a .NET 8 or newer runtime. Users rarely have one, so the app ships it and
# payload.js points DOTNET_ROOT at it. Windows needs none: FileConverter's
# default reader there is ThermoRawFileParser, which runs on the .NET Framework
# every Windows has.
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
  *) echo "No .NET runtime needed on $(uname -s)"; exit 0 ;;
esac

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
version=$(jq -r '."latest-runtime"' "$dl/releases.json")
read -r url hash < <(jq -r --arg v "$version" --arg n "dotnet-runtime-${rid}.tar.gz" \
  '.releases[] | select(.runtime.version == $v) | .runtime.files[] | select(.name == $n) | "\(.url) \(.hash)"' \
  "$dl/releases.json" | head -n 1)
[[ -n "${url:-}" && -n "${hash:-}" ]] || { echo "::error::no dotnet-runtime-${rid}.tar.gz for .NET ${version}"; exit 1; }

echo "Downloading .NET runtime ${version} (${rid})"
curl -fsSL --retry 5 --retry-all-errors -o "$dl/runtime.tar.gz" "$url"
if command -v sha512sum >/dev/null; then
  actual=$(sha512sum "$dl/runtime.tar.gz" | cut -d' ' -f1)
else
  actual=$(shasum -a 512 "$dl/runtime.tar.gz" | cut -d' ' -f1)
fi
[[ "$actual" == "$hash" ]] || { echo "::error::SHA-512 mismatch for $url"; exit 1; }

rm -rf "$out/dotnet"
mkdir -p "$out/dotnet"
tar -xzf "$dl/runtime.tar.gz" -C "$out/dotnet"
# The dotnet muxer is not needed to host the runtime from FileConverter, but
# it is small and lets a user check the runtime (dotnet --list-runtimes).
compgen -G "$out/dotnet/host/fxr/*/libhostfxr.*" >/dev/null ||
  { echo "::error::the .NET runtime archive has no host/fxr"; exit 1; }
echo "Staged .NET runtime ${version}: $(ls "$out/dotnet/shared/Microsoft.NETCore.App" | tr '\n' ' ')"
du -sh "$out/dotnet"
