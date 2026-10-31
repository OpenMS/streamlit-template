#!/usr/bin/env bash
# Stages the OpenMS TOPP tools of an official OpenMS release for the macOS or
# Linux Electron app, in the layout the shell expects:
#   <out>/openms/bin/<tool>     TOPP executables
#   <out>/openms/lib/           every shared library they need
#   <out>/share/OpenMS/         OPENMS_DATA_PATH (incl. THIRDPARTY/ when shipped)
# The binaries find their libraries through a relative rpath, so the folder
# can live anywhere (app bundle, AppImage mount, /opt).
#
#   stage-openms.sh <openms-version> <out dir> <TOPP tool>...
# Needs gh (GH_TOKEN), and sudo to install the release package (macOS) or the
# deb's dependencies (Linux) on the runner.
# OPENMS_REPOSITORY overrides the repository the release comes from.
set -euo pipefail

version="$1"
out="$2"
shift 2
tools=("$@")
repo="${OPENMS_REPOSITORY:-OpenMS/OpenMS}"
[[ ${#tools[@]} -gt 0 ]] || { echo "::error::no TOPP tools given"; exit 1; }

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) platform=macos ;;
  Linux-x86_64) platform=linux ;;
  *) echo "::error::unsupported platform $(uname -s)-$(uname -m)"; exit 1 ;;
esac

# Same tag schemes as openms-windows.yml.
tag=""
for candidate in "v${version}" "release/${version}" "Release${version}"; do
  if gh release view "$candidate" -R "$repo" --json tagName >/dev/null 2>&1; then
    tag="$candidate"
    break
  fi
done
[[ -n "$tag" ]] || { echo "::error::no release for OpenMS ${version} in ${repo}"; exit 1; }
assets=$(gh release view "$tag" -R "$repo" --json assets -q '.assets[].name')

pick() {
  local match
  match=$(grep -iE "$1" <<<"$assets" | grep -iE "${2:-.}" | head -n 1 || true)
  if [[ -z "$match" ]]; then
    echo "::error::no $3 package in release $tag. Assets: $(tr '\n' ' ' <<<"$assets")" >&2
    exit 1
  fi
  echo "$match"
}

dl=$(mktemp -d)
mkdir -p "$out/openms/bin" "$out/openms/lib" "$out/share"

if [[ $platform == macos ]]; then
  # The release has an Intel and an Apple Silicon .pkg; take the arm64 one.
  asset=$(pick '\.pkg$' 'arm64|aarch64|silicon' "macOS arm64")
  gh release download "$tag" -R "$repo" --pattern "$asset" --dir "$dl"
  sudo installer -pkg "$dl/$asset" -target /
  root=$(ls -d /Applications/OpenMS-* | head -n 1)
  echo "Installed $asset to $root"

  for t in "${tools[@]}"; do
    [[ -f "$root/bin/$t" ]] || { echo "::error::TOPP tool $t is not in $asset"; exit 1; }
    cp "$root/bin/$t" "$out/openms/bin/"
  done
  # OpenMS's packaging already copies every dependency into lib/ and rewrites
  # the install names to @rpath, with @executable_path/../lib as the rpath.
  cp -R "$root/lib/." "$out/openms/lib/"
  cp -R "$root/share/OpenMS" "$out/share/"

  bad=$(find "$out/openms" -type f \( -perm -u+x -o -name '*.dylib' \) -print0 |
    xargs -0 otool -L 2>/dev/null |
    awk '/^\t/ {print $1}' |
    grep -vE '^(@rpath|@executable_path|@loader_path|/usr/lib/|/System/)' | sort -u || true)
else
  asset=$(pick '\.deb$' 'x86_64|amd64' "Linux x86_64")
  gh release download "$tag" -R "$repo" --pattern "$asset" --dir "$dl"
  # Unpack instead of installing: the deb also ships headers that collide
  # with packages already on the runner (e.g. sqlite3.h from libsqlite3-dev).
  root="$dl/root"
  dpkg-deb -x "$dl/$asset" "$root"
  # Its runtime dependencies (Qt, ...) come from apt, which also picks among
  # the alternatives (e.g. libqt6core6t64 | libqt6core6) what this Ubuntu has.
  depends=$(dpkg-deb -f "$dl/$asset" Depends)
  echo "Depends: $depends"
  sudo apt-get update -q
  sudo apt-get install -y -q patchelf
  # libOpenMS also links QtNetwork, which the deb does not declare.
  sudo apt-get satisfy -y -q "$depends, libqt6network6t64 | libqt6network6"
  files=$(find "$root" \( -type f -o -type l \))
  echo "Unpacked $asset"

  for t in "${tools[@]}"; do
    src=$(grep -E "/bin/${t}$" <<<"$files" | head -n 1 || true)
    [[ -n "$src" ]] || { echo "::error::TOPP tool $t is not in $asset"; exit 1; }
    cp "$src" "$out/openms/bin/"
  done
  share=$(find "$root" -type d -path '*/share/OpenMS/CHEMISTRY' | head -n 1)
  [[ -n "$share" ]] || { echo "::error::$asset has no share/OpenMS"; exit 1; }
  cp -R "$(dirname "$share")" "$out/share/"
  # Let ldd find the deb's own libraries (libOpenMS, ...) where they were unpacked.
  export LD_LIBRARY_PATH
  LD_LIBRARY_PATH=$(find "$root" -name '*.so*' \( -type f -o -type l \) -exec dirname {} \; | sort -u | paste -sd:)

  # The deb relies on system packages (Qt, Xerces, ...). Copy every library the
  # tools load except glibc's, which must come from the host, and point all
  # rpaths into the bundle.
  glibc='^(linux-vdso|ld-linux|libc|libm|libdl|libpthread|librt|libresolv|libutil|libnsl|libanl|libmvec|libthread_db|libBrokenLocale)\.so'
  missing=$(for t in "$out"/openms/bin/*; do ldd "$t"; done | awk '/not found/ {print $1}' | sort -u)
  if [[ -n "$missing" ]]; then
    echo "::error::libraries not found on the runner (add their packages above): $(tr '\n' ' ' <<<"$missing")"
    exit 1
  fi
  for t in "$out"/openms/bin/*; do
    ldd "$t" | awk '/=> \// {print $1, $3}'
  done | sort -u | while read -r name path; do
    [[ $name =~ $glibc ]] && continue
    cp -L "$path" "$out/openms/lib/$name"
  done
  chmod u+w "$out"/openms/lib/* "$out"/openms/bin/*
  for f in "$out"/openms/bin/*; do patchelf --force-rpath --set-rpath '$ORIGIN/../lib' "$f"; done
  for f in "$out"/openms/lib/*; do patchelf --force-rpath --set-rpath '$ORIGIN' "$f"; done

  # Every dependency must now resolve inside the bundle (or to glibc).
  libdir=$(realpath "$out/openms/lib")
  bad=$(for f in "$out"/openms/bin/* "$out"/openms/lib/*; do
      env -u LD_LIBRARY_PATH ldd "$f" | awk '/=>/ {print $1, $3}'
    done | sort -u | while read -r name path; do
      [[ $name =~ $glibc ]] && continue
      [[ $(realpath -m "$path") == "$libdir/"* ]] || echo "$name => $path"
    done)
fi

if [[ -n "${bad:-}" ]]; then
  echo "::error::libraries resolved outside the bundle:"
  echo "$bad"
  exit 1
fi

if [[ -d "$out/share/OpenMS/THIRDPARTY" ]]; then
  echo "THIRDPARTY: $(ls "$out/share/OpenMS/THIRDPARTY" | tr '\n' ' ')"
fi
echo "Staged ${#tools[@]} TOPP tools and $(ls "$out/openms/lib" | wc -l) libraries from $asset"
