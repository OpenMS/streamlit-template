#!/usr/bin/env bash
# Packages the staged electron/payload into this platform's installer, the one
# step of the desktop build that differs between platforms:
#   Windows  dist/<APP_NAME>-Setup.exe              per-user NSIS installer (no admin rights)
#   macOS    dist/<APP_NAME>-macOS-arm64.dmg        signed and notarized when the secrets exist
#   Linux    dist/<APP_NAME>-Linux-x86_64.AppImage
# Run from the repository root after `npm ci` in electron/:
#   APP_NAME=MyApp [RELEASE_TAG=v1.2] electron/scripts/package.sh
# Writes installer=<path> to $GITHUB_OUTPUT when set.
#
# macOS signing reads MACOS_CERTIFICATE / MACOS_CERTIFICATE_PASSWORD, and
# notarization either APPLE_API_KEY_CONTENT (.p8 contents) + APPLE_API_KEY_ID +
# APPLE_API_ISSUER, or APPLE_ID + APPLE_APP_SPECIFIC_PASSWORD + APPLE_TEAM_ID.
set -euo pipefail

: "${APP_NAME:?APP_NAME must be set}"
RELEASE_TAG="${RELEASE_TAG:-}"

# electron-builder needs a semver version; take the numeric part of the release tag.
version=1.0.0
if [[ "$RELEASE_TAG" =~ ([0-9]+)(\.([0-9]+))?(\.([0-9]+))? ]]; then
  version="${BASH_REMATCH[1]}.${BASH_REMATCH[3]:-0}.${BASH_REMATCH[5]:-0}"
fi
# Package and executable name: lowercase, as Linux desktop entries expect.
id=$(tr '[:upper:]' '[:lower:]' <<<"$APP_NAME")
args=(
  --publish never
  "-c.productName=$APP_NAME"
  "-c.appId=de.openms.$APP_NAME"
  "-c.extraMetadata.productName=$APP_NAME"
  "-c.extraMetadata.version=$version"
)

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    installer="$APP_NAME-Setup.exe"
    args+=(--win nsis --x64 "-c.nsis.artifactName=$APP_NAME-Setup.\${ext}")
    ;;

  Darwin)
    installer="$APP_NAME-macOS-arm64.dmg"
    args+=("-c.extraMetadata.name=$id")
    # Notarization runs in our afterSign hook, which retries Apple's flaky
    # stapling service instead of failing the build.
    args+=(--mac dmg --arm64 "-c.dmg.artifactName=$APP_NAME-macOS-arm64.\${ext}"
      -c.mac.notarize=false -c.afterSign=scripts/notarize.js)
    # dmgbuild's own size estimate is too small for payloads with tens of
    # thousands of files (ditto runs out of space inside the volume);
    # electron-builder shrinks the image afterwards.
    payload_mb=$(du -sm electron/payload | cut -f1)
    args+=("-c.dmg.size=$(( payload_mb * 14 / 10 + 600 ))m")
    if [[ -n "${MACOS_CERTIFICATE:-}" ]]; then
      export CSC_LINK="$MACOS_CERTIFICATE" CSC_KEY_PASSWORD="${MACOS_CERTIFICATE_PASSWORD:-}"
      # electron-builder skips signing in pull requests by default. Only PRs from
      # branches of this repository see the secret, so sign those too.
      export CSC_FOR_PULL_REQUEST=true
      # Notarize with an App Store Connect API key, or else with an Apple ID
      # and an app-specific password.
      if [[ -n "${APPLE_API_KEY_CONTENT:-}" ]]; then
        printf '%s\n' "$APPLE_API_KEY_CONTENT" > "${RUNNER_TEMP:-/tmp}/AuthKey.p8"
        trap 'rm -f "${RUNNER_TEMP:-/tmp}/AuthKey.p8"' EXIT
        export APPLE_API_KEY="${RUNNER_TEMP:-/tmp}/AuthKey.p8" APPLE_API_KEY_ID APPLE_API_ISSUER
        unset APPLE_ID APPLE_APP_SPECIFIC_PASSWORD APPLE_TEAM_ID
      elif [[ -n "${APPLE_API_KEY_ID:-}" && -z "${APPLE_ID:-}" ]]; then
        echo "::warning::APPLE_API_KEY_ID is set but APPLE_API_KEY (the .p8 contents) is empty or not shared with this repository: the app is signed but not notarized"
      elif [[ -n "${APPLE_ID:-}" ]]; then
        unset APPLE_API_KEY_ID APPLE_API_ISSUER
      else
        echo "::warning::neither APPLE_API_KEY nor APPLE_ID is set: the app is signed but not notarized"
      fi
    else
      # Forks and pull requests from forks get no secrets: build unsigned.
      echo "::warning::MACOS_CERTIFICATE is not set: the app is not signed"
      export CSC_IDENTITY_AUTO_DISCOVERY=false
      unset APPLE_ID
    fi
    # The signer opens every file of the payload (tens of thousands) at once;
    # lift macOS's per-process limit above that.
    sudo sysctl -w kern.maxfiles=524288 kern.maxfilesperproc=524288 >/dev/null
    ulimit -n 524288
    echo "open-file limit: $(ulimit -n), payload files: $(find electron/payload -type f | wc -l)"
    ;;

  Linux)
    installer="$APP_NAME-Linux-x86_64.AppImage"
    args+=("-c.extraMetadata.name=$id")
    args+=(--linux AppImage --x64
      "-c.linux.executableName=$id"
      "-c.appImage.artifactName=$APP_NAME-Linux-x86_64.\${ext}")
    ;;

  *) echo "::error::unsupported platform $(uname -s)"; exit 1 ;;
esac

cd electron
log="${RUNNER_TEMP:-/tmp}/electron-builder.log"
# codesign can still lose a timestamp request to Apple's service on a Mach-O
# file; build again only for that error.
for i in 1 2 3; do
  npx electron-builder "${args[@]}" 2>&1 | tee "$log" && break
  if [[ $i == 3 ]] || ! grep -q "timestamp service is not available" "$log"; then exit 1; fi
  echo "::warning::Apple's timestamp service was not available; building again."
  sleep 60
done
ls -la dist
[[ -f "dist/$installer" ]] || { echo "::error::electron-builder did not produce dist/$installer"; exit 1; }

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "installer=electron/dist/$installer" >> "$GITHUB_OUTPUT"
fi
