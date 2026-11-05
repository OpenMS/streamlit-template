#!/usr/bin/env bash
# Installs the packaged app the way a user would, so the tests that follow run
# the same commands on every platform:
#   Windows  silent per-user install of the NSIS installer
#   macOS    mounts the dmg read-only (and checks signature and notarization)
#   Linux    the AppImage, mounted for Playwright, plus an extracted copy of its payload
#
#   APP_NAME=MyApp electron/scripts/install-app.sh <installer>
# Prints, and appends to $GITHUB_ENV when set:
#   APP_EXE      what a user starts (the installed .exe, the .app's binary, the AppImage)
#   APP_PAYLOAD  the installed app-payload folder
#   APP_LOG      the shell's Streamlit log
#   E2E_EXE      the executable Playwright drives
# On macOS, SIGNED=true checks the signature and NOTARIZED=true the stapled
# notarization ticket and Gatekeeper's verdict.
set -euo pipefail

: "${APP_NAME:?APP_NAME must be set}"
installer="$1"
id=$(tr '[:upper:]' '[:lower:]' <<<"$APP_NAME")
tmp="${RUNNER_TEMP:-$(mktemp -d)}"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    # /S stays a switch only if MSYS does not turn it into a path.
    MSYS_NO_PATHCONV=1 "$installer" /S
    inst="$(cygpath -m "$LOCALAPPDATA")/Programs/$APP_NAME"
    exe="$inst/$APP_NAME.exe"
    payload="$inst/resources/app-payload"
    log="$(cygpath -m "$APPDATA")/$APP_NAME/logs/streamlit.log"
    e2e="$exe"
    ;;

  Darwin)
    mnt="$tmp/dmg"
    hdiutil attach -nobrowse -readonly -mountpoint "$mnt" "$installer"
    app="$mnt/$APP_NAME.app"
    if [[ ${SIGNED:-} == true ]]; then
      codesign --verify --deep --strict --verbose=2 "$app"
      if [[ ${NOTARIZED:-} == true ]]; then
        # stapler validate talks to Apple's CloudKit, whose connection
        # sometimes drops (exit 68).
        for i in 1 2 3; do
          xcrun stapler validate "$app" && break
          [[ $i == 3 ]] && exit 1
          sleep 30
        done
        spctl --assess --type execute --verbose=2 "$app"
      fi
    fi
    exe="$app/Contents/MacOS/$APP_NAME"
    payload="$app/Contents/Resources/app-payload"
    log="$HOME/Library/Application Support/$APP_NAME/logs/streamlit.log"
    e2e="$exe"
    ;;

  Linux)
    # libfuse2t64 from Ubuntu 24.04 on, where libfuse2 is only a virtual package.
    sudo apt-get update -q
    sudo apt-get satisfy -y -q "libfuse2t64 | libfuse2, xvfb"
    exe=$(realpath "$installer")
    chmod +x "$exe"
    (cd "$tmp" && "$exe" --appimage-extract >/dev/null)
    payload="$tmp/squashfs-root/resources/app-payload"
    log="$HOME/.config/$APP_NAME/logs/streamlit.log"
    # Playwright drives the AppImage's own mounted image, so the app reads its
    # files through the image's compression as it does for a user (an
    # extracted copy would hide that), with APPIMAGE set as its runtime would.
    # The mount stays up until the job ends.
    nohup "$exe" --appimage-mount >"$tmp/appimage-mount.txt" 2>&1 &
    mnt=""
    for _ in $(seq 60); do
      mnt=$(head -n 1 "$tmp/appimage-mount.txt" 2>/dev/null || true)
      [[ -n $mnt && -x $mnt/$id ]] && break
      sleep 1
    done
    [[ -n $mnt && -x $mnt/$id ]] || { echo "::error::could not mount $exe"; cat "$tmp/appimage-mount.txt"; exit 1; }
    e2e="$mnt/$id"
    if [[ -n "${GITHUB_ENV:-}" ]]; then echo "APPIMAGE=$exe" >> "$GITHUB_ENV"; fi
    ;;

  *) echo "::error::unsupported platform $(uname -s)"; exit 1 ;;
esac

[[ -f "$exe" ]] || { echo "::error::$exe does not exist after installing $installer"; exit 1; }
[[ -d "$payload" ]] || { echo "::error::$payload does not exist after installing $installer"; exit 1; }
for kv in "APP_EXE=$exe" "APP_PAYLOAD=$payload" "APP_LOG=$log" "E2E_EXE=$e2e"; do
  echo "$kv"
  if [[ -n "${GITHUB_ENV:-}" ]]; then echo "$kv" >> "$GITHUB_ENV"; fi
done
