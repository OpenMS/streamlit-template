#!/bin/bash
# Build a draggable .dmg from the assembled .app using create-dmg
# (brew install create-dmg). Produces a window with the app icon on the left and
# an /Applications drop-link on the right. Run from the repo root.
#
# Required environment: APP_NAME.
set -euo pipefail

APP_NAME="${APP_NAME:?APP_NAME is required}"
APP="dist/${APP_NAME}.app"
DMG="dist/${APP_NAME}.dmg"

[ -d "$APP" ] || { echo "missing $APP - run build_app_bundle.sh first" >&2; exit 1; }
rm -f "$DMG"

# create-dmg packages every file in the source directory, so stage only the .app.
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"

ARGS=(
    --volname "$APP_NAME"
    --window-pos 200 120
    --window-size 700 450
    --icon-size 120
    --icon "${APP_NAME}.app" 180 200
    --app-drop-link 520 200
    --hide-extension "${APP_NAME}.app"
    --hdiutil-retries 5
    --no-internet-enable
)
[ -f AppIcon.icns ] && ARGS+=(--volicon AppIcon.icns)
[ -f assets/openms_license.rtf ] && ARGS+=(--eula assets/openms_license.rtf)

# create-dmg occasionally fails on hdiutil flakiness in CI; retry a few times.
n=0
until create-dmg "${ARGS[@]}" "$DMG" "$STAGE"; do
    n=$((n + 1))
    if [ "$n" -ge 3 ]; then
        echo "create-dmg failed after $n attempts" >&2
        exit 1
    fi
    echo "create-dmg flaked (hdiutil); retry $n" >&2
    sleep 5
    rm -f "$DMG"
done

rm -rf "$STAGE"
echo "Built $DMG"
