## OpenMS for Windows: the reusable workflow

`.github/workflows/openms-windows.yml` is a [reusable workflow](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) that provides the OpenMS TOPP tools for a Windows app installer. It uploads one artifact (default name `openms-package`) holding a zip whose top level is:

```
openms-package/bin/     TOPP tool .exe files and every DLL they need
openms-package/share/   share/OpenMS, including share/OpenMS/THIRDPARTY/<engine>
```

This is the layout the `build-executable` job of `build-windows-executable-app.yaml` has always consumed, so an app switching to the reusable workflow keeps that job unchanged.

It replaces the old `build-openms` job, which compiled OpenMS against the `contrib` dependency archive with `tools/ci/cibuild.cmake`. Neither exists any more for OpenMS 3.6 and develop: OpenMS builds its dependencies with vcpkg (OpenMS/OpenMS#10327).

### Calling it from an app

```yaml
jobs:
  build-openms:
    uses: OpenMS/streamlit-template/.github/workflows/openms-windows.yml@<ref>
    with:
      openms-version: "3.5.0"
      topp-tools: "FeatureFinderMetabo FeatureLinkerUnlabeledKD SiriusExport"

  build-executable:
    runs-on: windows-2022
    needs: build-openms
    steps:
      # ... unchanged: download the `openms-package` artifact, unzip it, copy
      # openms-package/bin and openms-package/share into the installer.
```

`with:` of a reusable-workflow call cannot read the workflow's `env`. To keep `TOPP_TOOLS` defined once in `env`, pass it through a small job output, as this repository's `build-windows-executable-app.yaml` does.

A reusable workflow gets the caller's `GITHUB_TOKEN`; it only needs `contents: read`.

### Inputs

| input | default | meaning |
|---|---|---|
| `openms-version` | `3.5.0` | Release to package. Installer mode looks up the GitHub release; source mode uses it only for the default ref. |
| `mode` | `installer` | `installer`: repackage the official Windows installer. `source`: build OpenMS with vcpkg. |
| `openms-repository` | `OpenMS/OpenMS` | Repository whose releases (installer) or sources (source) are used. |
| `openms-ref` | `release/<openms-version>` | Branch, tag or SHA to build in source mode. |
| `topp-tools` | *(all)* | Space-separated TOPP tools to keep. Each must exist, or the job fails. DLLs and `share/` are always kept whole. |
| `artifact-name` | `openms-package` | Name of the uploaded artifact (also an output). |
| `runs-on` | `windows-2025` | Windows runner label. |

### Installer mode (default)

Downloads the Windows installer (`*.exe`) from the OpenMS GitHub release and installs it silently (`/S /allusers /D=...`); if that fails, it extracts the installer with 7-Zip instead. Releases are found under the tags `v<version>` (3.6 on), `release/<version>` (3.2.0 to 3.5.0) and `Release<version>` (3.0.0).

Nothing is compiled, so this takes minutes. It runs no OpenMS tests, because the official installers are tested upstream; it does run `<tool> --help` for every kept tool (or `FeatureFinderMetabo` when all are kept) with a bare system `PATH`, which catches a DLL missing from `bin/`.

Use it for every app that ships a released OpenMS.

### Source mode

For apps that ship a branch or a fork, for example `mode: source`, `openms-repository: <you>/OpenMS`, `openms-ref: my-feature`.

It checks out the ref with the `vcpkg` and `THIRDPARTY` submodules (not `contrib`), configures with `cmake --preset windows-x64-release` plus a TOPP-only set of options (`WITH_GUI=OFF`, `ENABLE_DOCS=OFF`, no tests; the optional dependencies match the official installer's), builds, and packages with CPack's `ZIP` generator, with `THIRDPARTY` as `SEARCH_ENGINES_DIRECTORY`.

**Source mode needs OpenMS sources with the vcpkg CMake presets**: OpenMS 3.6 and later, and develop from about 2026-08 on. A fork based on an older develop must rebase first; the job stops with that message if `CMakePresets.json` has no `windows-x64-release` preset.

The vcpkg binaries (a `files` binary source, keyed on `vcpkg.json`, `vcpkg-configuration.json`, the overlays and the vcpkg commit) and ccache are cached with `actions/cache`, in the calling repository's cache. Measured on `windows-2025` against OpenMS develop: a cold run (empty caches) takes about 2 h 50 min, 1 h 23 min of it building the vcpkg dependencies and 1 h 24 min compiling OpenMS; a warm run takes about 8 min. The job allows 6 h, so the first run has headroom; the caches are per repository and branch scope, so each app pays the cold run once.

### Which `<ref>` to use

Pin a ref that does not move under you: a commit SHA of `OpenMS/streamlit-template`, or a tag, if the maintainers publish one for this workflow. `@main` works, but picks up every change to the workflow the moment it is merged. Dependabot's `github-actions` ecosystem keeps a SHA or tag pin up to date.
