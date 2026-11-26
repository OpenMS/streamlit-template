---
name: configure-desktop-installers
description: Use when setting up, changing or debugging the desktop app (Electron installer, Windows .exe, embedded Python, bundled TOPP tools) of an app derived from the template.
---

# Configure the desktop installers

The desktop app is the Streamlit app with an embedded Python, the TOPP tools it
needs and an Electron shell, built for Windows, macOS (Apple Silicon) and Linux
by `.github/workflows/build-desktop-app.yaml`. OpenMS comes from the reusable
`.github/workflows/openms.yml`: a released version is downloaded, any other
`[owner/repo@]ref` is built from source (hours cold, cached per commit).
`electron/` holds the shell, its smoke tests (`scripts/smoke-payload.js`,
`scripts/smoke-app.js`) and the end-to-end test (`scripts/e2e.js`).

Platforms are listed in `app.yaml` under `deploy.desktop` (`[]` turns the build
off). The workflow is template-owned and every app runs it unchanged: never
edit it in an app, and never list it in `sync.app_owned`.

## What an app sets

Everything app-specific goes in `deploy.desktop_app` of `app.yaml`; each key is
optional and falls back to the workflow's default:

| Key | What |
|---|---|
| `name` | installer and install-folder name, no spaces; also `appId de.openms.<name>`. Changing it on a released app gives users a second install. |
| `installer_version` | `true` names the installers `<name>-<version>-Setup.exe` and so on, version from `settings.json` |
| `topp_tools` | every TOPP tool the app's `execution()` calls, plus `FileConverter` if `raw` input is accepted. A tool missing here works in Docker and fails only on the desktop. |
| `openms` | the OpenMS to bundle: a release (`"3.6.0"`) or `owner/repo@ref`; see `upgrade-openms`. It must name what the full Dockerfiles build (`OPENMS_REPO`/`OPENMS_BRANCH`), so the desktop app, its command line tools and the image run one OpenMS; `python -m utils.app_spec` checks it |
| `synopsis` | one line for the Linux AppImage |
| `e2e_scenarios` | the app's scenario files for `e2e.js --scenario` (repository paths) |
| `stage_script` | a bash script run as `bash <script> <python> electron/payload` once the app's requirements are installed in the embedded Python: extra wheels, import checks, package swaps. It runs on all three platforms (Git Bash on Windows); tell them apart with `uname -s` |

`python -m utils.app_spec` checks the keys and that the named files exist.
Derive `topp_tools` from the spec instead of by hand:

```bash
python - <<'PY'
from utils.app_spec import load_spec
s = load_spec("app.yaml")
tools = {st["tool"] for wf in s.get("workflows", []) for st in wf.get("steps", []) if "tool" in st}
if any("raw" in i.get("types", []) for i in s.get("inputs", {}).values()):
    tools.add("FileConverter")
print(sorted(tools))
PY
```

`settings.json` is switched to offline mode by the workflow itself (`Set to
offline deployment` step); do not commit `online_deployment: false` for that.

## Verify

The full build runs on a PR that changes packaging (or carries the label
`desktop-build`), nightly, on a manual run and on a release. It installs each
installer, runs `smoke-payload.js` (pyOpenMS, each TOPP tool), `smoke-app.js`
and the end-to-end test with the app's scenarios, and uploads screenshots as an
artifact; a failure prints the app's and the workflow's logs. A failing smoke
test names the tool; check `topp_tools` first. On a published release the
installers are attached, then the release's container images are built.

The same run packages the OpenMS it bundled as installers of the command line
tools alone (job `tools`, `electron/scripts/package-tools.sh`), named
`<APP_NAME>-command-line-tools-<platform>.exe|.pkg|.deb`; `tools-test`
installs each and runs every `TOPP_TOOLS` entry. A release gets them beside
the app's installers, and `installers.find_tool_installers()` offers them on a
Quick Start page. The macOS `.pkg` of a branch build carries only an ad-hoc
signature, so Gatekeeper asks before opening it.

## Checklist

- [ ] `deploy.desktop_app.name` set (and unchanged on an already released app)
- [ ] `deploy.desktop_app.topp_tools` covers every tool in the spec, plus FileConverter for `.raw`
- [ ] `deploy.desktop` in `app.yaml` matches what is built
- [ ] Smoke and e2e steps green on the PR
