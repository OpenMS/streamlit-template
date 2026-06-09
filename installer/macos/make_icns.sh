#!/bin/bash
# Generate a macOS .icns icon from an SVG (preferred) or PNG source.
#
#   make_icns.sh <source.(svg|png)> <output.icns>
#
# assets/OpenMS.png is 400x291 (not square and < 512px), so it cannot be turned
# into a valid .icns directly. We render the source to a 1024x1024 transparent,
# aspect-preserved square first. ImageMagick (with the librsvg delegate) renders
# SVG crisply; install it in CI with `brew install imagemagick librsvg`.
set -euo pipefail

SRC="${1:?usage: make_icns.sh <source> <output.icns>}"
OUT="${2:?usage: make_icns.sh <source> <output.icns>}"
WORK="$(mktemp -d)"
BASE="$WORK/base.png"

IM=""
command -v magick >/dev/null 2>&1 && IM="magick"
[ -z "$IM" ] && command -v convert >/dev/null 2>&1 && IM="convert"

if [ -n "$IM" ]; then
    "$IM" -background none "$SRC" -resize 1024x1024 -gravity center -extent 1024x1024 "$BASE"
elif [ "${SRC##*.}" = "png" ] || [ "${SRC##*.}" = "PNG" ]; then
    # Fallback: sips cannot read SVG or pad transparently, so this only runs for
    # PNG input and may distort/letterbox. Prefer installing ImageMagick.
    sips -s format png "$SRC" --out "$BASE" >/dev/null
    sips -z 1024 1024 "$BASE" --out "$BASE" >/dev/null
else
    echo "make_icns: need ImageMagick to rasterize '$SRC' (brew install imagemagick librsvg)" >&2
    exit 1
fi

ICONSET="$WORK/AppIcon.iconset"
mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
    sips -z "$s" "$s" "$BASE" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2))
    sips -z "$d" "$d" "$BASE" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done

iconutil -c icns "$ICONSET" -o "$OUT"
rm -rf "$WORK"
echo "Built $OUT"
