#!/usr/bin/env bash
# Stages OpenMS TOPP tools for the Electron app, on Windows, macOS and Linux
# alike, in the layout the shell expects:
#   <out>/openms/bin/<tool>     TOPP executables (on Windows with their DLLs)
#   <out>/openms/lib/           every shared library they need (macOS, Linux)
#   <out>/share/OpenMS/         OPENMS_DATA_PATH (incl. THIRDPARTY/ when shipped)
# The macOS and Linux binaries find their libraries through a relative rpath,
# Windows ones next to the executable, so the folder can live anywhere (app
# bundle, AppImage mount, install directory).
#
#   stage-openms.sh <openms-version> <out dir> <TOPP tool>...
# macOS and Linux take the official release package (.pkg, .deb); OPENMS_PACKAGE
# names a local .pkg or .deb to stage instead, e.g. one built by OpenMS's
# cipackage.cmake from a branch with unreleased tools. Windows always takes
# OPENMS_PACKAGE: the zip of openms-package/{bin,share} that openms-windows.yml
# uploads (from the release installer or a source build).
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
  MINGW*-x86_64|MSYS*-x86_64|CYGWIN*-x86_64) platform=windows ;;
  *) echo "::error::unsupported platform $(uname -s)-$(uname -m)"; exit 1 ;;
esac

dl=$(mktemp -d)
mkdir -p "$out/openms/bin" "$out/share"
[[ $platform == windows ]] || mkdir -p "$out/openms/lib"

if [[ -n "${OPENMS_PACKAGE:-}" ]]; then
  [[ -f "$OPENMS_PACKAGE" ]] || { echo "::error::OPENMS_PACKAGE $OPENMS_PACKAGE does not exist"; exit 1; }
  cp "$OPENMS_PACKAGE" "$dl/"
  local_asset=$(basename "$OPENMS_PACKAGE")
elif [[ $platform == windows ]]; then
  echo "::error::on Windows, OPENMS_PACKAGE must name the zip from openms-windows.yml"
  exit 1
else
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
fi

# Picks the package from the release (or takes the local one) and downloads it to $dl.
pick() {
  local match
  if [[ -n "${local_asset:-}" ]]; then
    echo "$local_asset"
    return
  fi
  match=$(grep -iE "$1" <<<"$assets" | grep -iE "${2:-.}" | head -n 1 || true)
  if [[ -z "$match" ]]; then
    echo "::error::no $3 package in release $tag. Assets: $(tr '\n' ' ' <<<"$assets")" >&2
    exit 1
  fi
  gh release download "$tag" -R "$repo" --pattern "$match" --dir "$dl" >&2
  echo "$match"
}

if [[ $platform == windows ]]; then
  asset=$local_asset
  unzip -q "$dl/$asset" -d "$dl/root"
  pkg=$(dirname "$(find "$dl/root" -maxdepth 3 -type d -name bin -path '*openms-package/bin' | head -n 1)")
  [[ -d "$pkg/bin" && -d "$pkg/share/OpenMS" ]] || { echo "::error::$asset has no openms-package/{bin,share/OpenMS}"; exit 1; }
  for t in "${tools[@]}"; do
    [[ -f "$pkg/bin/$t.exe" ]] || { echo "::error::TOPP tool $t is not in $asset"; exit 1; }
    cp "$pkg/bin/$t.exe" "$out/openms/bin/"
  done
  # Windows loads a program's DLLs from its own folder.
  cp "$pkg"/bin/*.dll "$out/openms/bin/"
  cp -R "$pkg/share/OpenMS" "$out/share/"
elif [[ $platform == macos ]]; then
  # The release has an Intel and an Apple Silicon .pkg; take the arm64 one.
  asset=$(pick '\.pkg$' 'arm64|aarch64|silicon' "macOS arm64")
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
libs=$(find "$out/openms" -type f \( -name '*.dll' -o -name '*.dylib' -o -name '*.so*' \) | wc -l)
echo "Staged ${#tools[@]} TOPP tools and $libs libraries from $asset"
