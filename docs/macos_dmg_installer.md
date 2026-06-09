# 🍏 Create a draggable macOS .dmg installer of a Streamlit App

This is the macOS counterpart to [`win_exe_with_embed_py.md`](win_exe_with_embed_py.md).
It produces a draggable `.dmg` containing a `<AppName>.app` bundle that ships a
relocatable Python, the Streamlit app, and the OpenMS/TOPP binaries — the user
just drags the app into `/Applications`.

The whole process is automated by the GitHub Action
[`build-macos-dmg-app.yaml`](../.github/workflows/build-macos-dmg-app.yaml), which
mirrors the Windows installer and shares its environment setup through
`installer/common/` (see [Shared with the Windows build](#shared-with-the-windows-build)).

> **Target:** Apple Silicon (arm64), `runs-on: macos-14`, macOS 12+.

## Overview

The workflow has two jobs, exactly mirroring the Windows pipeline:

1. **`build-openms-macos`** — compiles OpenMS + TOPP tools from source and uploads
   an `openms-package-macos` artifact (`bin/`, `lib/`, `share/`).
2. **`build-dmg`** — downloads that artifact, adds a relocatable Python with the
   app's `requirements.txt`, assembles the `.app`, code-signs it, and packages a
   draggable `.dmg`.

## Building OpenMS on Apple Silicon

⚠️ **Do not download the prebuilt OpenMS contrib on arm64.** OpenMS 3.5.0's
`contrib_build-macOS.tar.gz` is an **x86_64** build (3.5.0 was the last Intel-mac
release), so linking arm64 tools against it fails. Instead — like OpenMS's own
macOS CI — install the dependencies from Homebrew and point CMake at them:

```bash
# Homebrew deps (mirrors OpenMS/tools/ci/deps-macos.sh)
brew install autoconf automake libtool ninja ccache libomp \
             boost eigen xerces-c libsvm cbc glpk sqlite hdf5 qt
export CMAKE_PREFIX_PATH="$(brew --prefix);$(brew --prefix libomp);$(brew --prefix qt)"
```

Build with the same cross-platform OpenMS CI scripts the Windows job uses
(`tools/ci/cibuild.cmake`, `citest.cmake`, `cipackage.cmake`), but with the
macOS-correct flags: `BOOST_USE_STATIC=OFF` (Homebrew boost is shared),
`MACOSX_DEPLOYMENT_TARGET=12.0`, `WITH_GUI=OFF`.

## Relocatable Python (python-build-standalone)

macOS has no official "embeddable" Python like Windows. We use
[`astral-sh/python-build-standalone`](https://github.com/astral-sh/python-build-standalone)
`install_only` builds, e.g. `cpython-3.11.x+YYYYMMDD-aarch64-apple-darwin-install_only.tar.gz`.
Unlike the Windows embeddable zip, these **ship pip + headers + ensurepip**, so
you install requirements directly into the interpreter:

```bash
./python/bin/python3 -m pip install -r requirements.txt
```

> **Never set `PYTHONHOME`.** python-build-standalone derives its prefix from the
> interpreter's own location, so calling `.../Resources/python/bin/python3` by
> absolute path keeps working after the `.app` is moved to `/Applications`.

`installer/macos/find_pbs_url.py` selects the right asset for the configured
`PYTHON_VERSION`.

## Anatomy of the `.app` bundle

```
<AppName>.app/
  Contents/
    Info.plist                 # from installer/macos/Info.plist.template
    MacOS/<AppName>            # launcher (CFBundleExecutable); from launcher.sh.template
    Resources/
      python/                  # relocatable interpreter + site-packages
      bin/  lib/  share/       # OpenMS TOPP tools, dylibs, and data (OPENMS_DATA_PATH)
      src/ content/ assets/ ... # the shared app payload (app_payload.txt)
      app.py settings.json ...
      AppIcon.icns
```

Minimal `Info.plist` keys: `CFBundleExecutable`, `CFBundleIdentifier`,
`CFBundleName`/`CFBundleDisplayName`, `CFBundleVersion`/`CFBundleShortVersionString`,
`CFBundleIconFile`, `CFBundlePackageType=APPL`, `NSHighResolutionCapable`,
`LSMinimumSystemVersion=12.0`, and `LSUIElement=true` (runs as an agent — no Dock
icon — while the launcher opens the browser).

### The launcher and the writable working directory

The bundle is read-only and code-signed, so the app must **not** run or write
inside it. The launcher (`installer/macos/launcher.sh.template`) therefore:

- creates a per-user writable dir `~/Library/Application Support/<AppName>/app`
  and symlinks the read-only app files into it (the app reads `settings.json` and
  `assets/` relative to the working directory);
- runs from there, so local **workspaces** (written to `../`, see
  `src/common/common.py`) land in `~/Library/Application Support/<AppName>/` —
  outside the bundle;
- sets `OPENMS_DATA_PATH`, prepends `Resources/bin` and the bundled
  `THIRDPARTY/*` to `PATH`, and sets `DYLD_FALLBACK_LIBRARY_PATH=Resources/lib`
  for the TOPP dylibs (mirrors the Windows `.bat`);
- starts Streamlit headless with the `local` argument (not `windows`), waits for
  the port, then runs `open http://localhost:8501`.

## App icon

`assets/OpenMS.png` is 400×291 — not square and below 512px, so it can't become a
valid `.icns`. `installer/macos/make_icns.sh` rasterizes
`assets/openms_transparent_bg_logo.svg` to a 1024×1024 transparent square (via
ImageMagick + librsvg), builds the standard iconset sizes with `sips`, and packs
them with `iconutil`.

## Building the DMG

`installer/macos/build_dmg.sh` wraps [`create-dmg`](https://github.com/create-dmg/create-dmg)
(`brew install create-dmg`) to produce the classic window with the app icon and an
`/Applications` drop-link, the volume icon, and the license EULA. `hdiutil` is
occasionally flaky in CI, so the call uses `--hdiutil-retries` and a retry loop.

## Code signing on Apple Silicon

**Ad-hoc signing is mandatory even for an "unsigned" distribution.** On Apple
Silicon the OS refuses to run any unsigned Mach-O — the bundle, the bundled
`python3`, and every `.dylib`/`.so`. `installer/macos/sign_macos.sh` therefore
**always** signs, inside-out (nested binaries first, the bundle last; `--deep` is
avoided per Apple TN2206):

- **No secrets →** ad-hoc (`codesign --sign -`). Ships, runs locally, but is not
  notarized, so end users must clear Gatekeeper (see below).
- **Secrets present →** Developer ID signing with a hardened runtime, then
  `xcrun notarytool submit --wait` + `xcrun stapler staple`. Provide these repo
  secrets to activate it: `MACOS_CERTIFICATE_BASE64`, `MACOS_CERTIFICATE_PW`,
  `MACOS_SIGN_IDENTITY`, `MACOS_NOTARY_APPLE_ID`, `MACOS_NOTARY_TEAM_ID`,
  `MACOS_NOTARY_PW`.

### Gatekeeper, for end users of an unsigned/ad-hoc build

The first launch is blocked by Gatekeeper. Either right-click the app → **Open** →
**Open**, or run once:

```bash
xattr -dr com.apple.quarantine "/Applications/<AppName>.app"
```

## Shared with the Windows build

To keep the two installers in sync, both call cross-platform helpers in
`installer/common/`:

- `set_app_version.py` — sets `version` + `online_deployment=false` in `settings.json`.
- `app_payload.txt` — the single source of truth for which app files/dirs are bundled.
- `collect_payload.py` — copies that payload into the bundle.
- `prune_site_packages.py` — strips `__pycache__`/`test` dirs from the bundled Python.

## Stopping the app

The local server keeps running after you close the browser tab (same model as the
Windows build). To stop it, quit the app, or end the `streamlit`/`python` process
(e.g. via Activity Monitor); it also stops on logout.

## Migrating this to your own app

Use the `configure-installers` skill — it reads your `Dockerfile` and
`settings.json` and fills in the workflow env (`OPENMS_VERSION`, `PYTHON_VERSION`,
`APP_NAME`, `BUNDLE_ID`, `TOPP_TOOLS`), the OpenMS checkout repo/ref (handling
forks such as FLASHApp), a JS/Vue build step when needed, and a fresh Windows
`APP_UpgradeCode`.
