#!/bin/bash
# Code-sign the macOS .app bundle.
#
#   sign_macos.sh <App.app>
#
# On Apple Silicon EVERY Mach-O (the bundle, the bundled python, every
# .dylib/.so) must be signed or the OS kills it - so even the "unsigned"
# distribution path ad-hoc signs everything. Signing is done inside-out
# (nested code first, bundle last; `--deep` is avoided - see Apple TN2206).
#
# If Apple Developer secrets are present the script instead Developer-ID signs
# with a hardened runtime and notarizes; otherwise it ad-hoc signs. The step is
# therefore safe to run unconditionally - it always succeeds without secrets.
#
# Real-signing env (all optional): MACOS_CERTIFICATE_BASE64, MACOS_CERTIFICATE_PW,
# MACOS_SIGN_IDENTITY, MACOS_NOTARY_APPLE_ID, MACOS_NOTARY_TEAM_ID, MACOS_NOTARY_PW.
set -euo pipefail

APP="${1:?usage: sign_macos.sh <App.app>}"
xattr -cr "$APP" || true

EXECUTABLE="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP/Contents/Info.plist")"

# Sign all nested binaries first, then the launcher. Bundle is signed by callers.
sign_inner() {
    local id="$1"; shift
    local flags=("$@")
    find "$APP/Contents/Resources" \( -name '*.dylib' -o -name '*.so' \) -type f -print0 |
        while IFS= read -r -d '' f; do
            codesign --force "${flags[@]}" --sign "$id" "$f"
        done
    for d in "$APP/Contents/Resources/bin" "$APP/Contents/Resources/python"; do
        [ -d "$d" ] || continue
        find "$d" -type f -perm -111 -print0 |
            while IFS= read -r -d '' f; do
                codesign --force "${flags[@]}" --sign "$id" "$f" 2>/dev/null || true
            done
    done
    codesign --force "${flags[@]}" --sign "$id" "$APP/Contents/MacOS/$EXECUTABLE"
}

if [ -z "${MACOS_CERTIFICATE_BASE64:-}" ]; then
    echo "No signing secrets present -> ad-hoc signing (required on Apple Silicon)."
    sign_inner "-"
    codesign --force --sign - "$APP"
    codesign --verify --verbose=2 "$APP" || true
    exit 0
fi

echo "Developer ID signing + notarization."
KEYCHAIN="${RUNNER_TEMP:-/tmp}/app-signing.keychain-db"
KEYCHAIN_PW="$(uuidgen)"
security create-keychain -p "$KEYCHAIN_PW" "$KEYCHAIN"
security set-keychain-settings -lut 3600 "$KEYCHAIN"
security unlock-keychain -p "$KEYCHAIN_PW" "$KEYCHAIN"
echo "$MACOS_CERTIFICATE_BASE64" | base64 --decode > "${RUNNER_TEMP:-/tmp}/cert.p12"
security import "${RUNNER_TEMP:-/tmp}/cert.p12" -P "${MACOS_CERTIFICATE_PW:-}" -A -t cert -f pkcs12 -k "$KEYCHAIN"
security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | tr -d '"')
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PW" "$KEYCHAIN" >/dev/null

ID="${MACOS_SIGN_IDENTITY:?MACOS_SIGN_IDENTITY required when signing}"
sign_inner "$ID" --options runtime --timestamp
codesign --force --options runtime --timestamp --sign "$ID" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

# Notarize the bundle, then staple the ticket so it validates offline.
ditto -c -k --keepParent "$APP" "${RUNNER_TEMP:-/tmp}/notarize.zip"
xcrun notarytool submit "${RUNNER_TEMP:-/tmp}/notarize.zip" --wait \
    --apple-id "${MACOS_NOTARY_APPLE_ID:?}" \
    --team-id "${MACOS_NOTARY_TEAM_ID:?}" \
    --password "${MACOS_NOTARY_PW:?}"
xcrun stapler staple "$APP"
