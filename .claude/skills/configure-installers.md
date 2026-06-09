# Configure Installer Workflows (Windows MSI + macOS DMG)

Configure the desktop installer workflows when the template has been merged into
another OpenMS Streamlit app, driving the settings from the app's **Dockerfile**
and **settings.json**. Produces a Windows `.msi` and a draggable macOS `.dmg`
that bundle the same app payload. Run after `configure-app-settings`.

The two workflows already share their environment setup through `installer/common/`,
so migration is mostly editing each workflow's `env:` block and the OpenMS
checkout — plus, when relevant, adding a JS build step.

## Instructions

1. **Read the source of truth.** Open the app's `Dockerfile` (fall back to
   `Dockerfile.arm` / `Dockerfile_simple`) and `settings.json`.

2. **Parse the Dockerfile** for these `ARG`/commands and map them to workflow env:

   | Dockerfile | Workflow setting |
   |------------|------------------|
   | `ARG OPENMS_BRANCH=release/X.Y.Z` | `OPENMS_VERSION: X.Y.Z` (both workflows) and the OpenMS checkout `ref: release/X.Y.Z` |
   | `ARG OPENMS_REPO=…/<owner>/OpenMS.git` | OpenMS checkout `repository: <owner>/OpenMS`. **If it is a fork** (not `OpenMS/OpenMS`), set both the `repository` and `ref` to the fork/branch and note that the build-from-source path is required (a matching prebuilt OpenMS does not exist — these workflows already build from source, so nothing else changes) |
   | `mamba create -n streamlit-env python=3.XX` | `PYTHON_VERSION: 3.XX.<patch>` (the macOS job uses the `3.XX` line for python-build-standalone; pick a released patch for Windows' embeddable Python) |

   For a non-release `OPENMS_BRANCH` (e.g. `develop`, or a fork branch), set
   `OPENMS_VERSION` to the nearest release for contrib/version display and set the
   checkout `ref` to the actual branch.

3. **Read settings.json** and map:

   | settings.json | Workflow setting |
   |---------------|------------------|
   | `app-name` | `APP_NAME` (slugified for filenames, e.g. "UmetaFlow" → `UmetaFlow`) |
   | `repository-name` | macOS `BUNDLE_ID: de.openms.<repository-name>`; release-asset names |
   | `version` | fallback `CFBundleVersion` when not a release build |

4. **Determine `TOPP_TOOLS`** — the TOPP tools the app actually invokes:

   ```bash
   grep -rho 'run_topp("[^"]*"' src content | sed -E 's/run_topp\("([^"]*)"/\1/' | sort -u
   ```

   Union that with the `THIRDPARTY/*` entries on the Dockerfile `ENV PATH` line and
   the tool keys in `presets.json`. Present the list and confirm with the user.
   Set the same `TOPP_TOOLS` in both workflows. ⚠️ Search engines that are native
   **x86_64-only** won't run on Apple Silicon without Rosetta — flag any such tool.

5. **Detect a JS/Vue component build stage.** Look in the Dockerfile for a
   `FROM node:… AS js-build` stage that builds a Vue component (e.g. FLASHApp's
   `openms-streamlit-vue-component`, branch `FVdeploy`, copied to
   `/app/js-component/dist`). If present:
   - add a JS build step to **both** installer workflows, before the payload is
     assembled: checkout the Vue repo/branch, `npm ci && npm run build`, and copy
     `dist` into the app at `js-component/dist`;
   - add `js-component` to `installer/common/app_payload.txt` so both bundles
     include the compiled component.

6. **Generate a fresh Windows `APP_UpgradeCode`** (never reuse the template's):

   ```bash
   python -c "import uuid; print(uuid.uuid4())"
   ```

   Put it in `build-windows-executable-app.yaml`'s `env.APP_UpgradeCode`.

7. **Write the changes** to both workflow `env:` blocks and the OpenMS checkout
   step, then sanity-check that the YAML still parses and the `TOPP_TOOLS` exist in
   a build (the macOS job warns if a listed tool is missing from the package).

## Dockerfile → app type decision guide

| App | OpenMS repo / ref | Vue build? | Notes |
|-----|-------------------|------------|-------|
| streamlit-template | `OpenMS/OpenMS` @ `release/3.5.0` | no | the defaults shipped in the workflows |
| umetaflow | `OpenMS/OpenMS` @ release | no | metabolomics TOPP tools in `TOPP_TOOLS` |
| quantms-web | `OpenMS/OpenMS` @ release | no | proteomics TOPP tools |
| FLASHApp | `t0mdavid-m/OpenMS` @ `FVdeploy` (fork) | **yes** | add the JS build step + `js-component` to the payload |

## Reference Files

- Installer workflows: `.github/workflows/build-windows-executable-app.yaml`,
  `.github/workflows/build-macos-dmg-app.yaml`
- Shared setup: `installer/common/{set_app_version.py, collect_payload.py, app_payload.txt, prune_site_packages.py}`
- macOS specifics: `installer/macos/` (templates + `make_icns.sh`, `build_app_bundle.sh`, `build_dmg.sh`, `sign_macos.sh`, `find_pbs_url.py`)
- Inputs to parse: `Dockerfile`, `Dockerfile.arm`, `settings.json`, `presets.json`
- Docs: `docs/macos_dmg_installer.md`, `docs/win_exe_with_embed_py.md`

## Checklist

- [ ] `OPENMS_VERSION` set in both workflows; OpenMS checkout `repository`/`ref` match the Dockerfile (fork handled)
- [ ] `PYTHON_VERSION` set from the Dockerfile's `python=` (both workflows)
- [ ] `APP_NAME` set; macOS `BUNDLE_ID` set from `repository-name`
- [ ] `TOPP_TOOLS` derived from `run_topp(...)` usage and confirmed; x86_64-only engines flagged
- [ ] JS/Vue build step added to both workflows **iff** the Dockerfile has a node build stage (and `js-component` added to `app_payload.txt`)
- [ ] Fresh `APP_UpgradeCode` GUID generated for the Windows workflow
- [ ] Both workflows still parse; artifacts upload, and release events attach the installers

## Next Steps

Trigger each workflow via `workflow_dispatch` to confirm a green build, then test
the produced `.msi` / `.dmg` on real Windows / Apple-Silicon machines. To enable a
notarized (no-warning) macOS install later, add the Apple Developer secrets listed
in `docs/macos_dmg_installer.md`.
