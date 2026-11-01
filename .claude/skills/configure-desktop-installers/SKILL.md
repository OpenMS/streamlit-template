---
name: configure-desktop-installers
description: Use when setting up, changing or debugging the desktop app (Electron installer, Windows .exe, embedded Python, bundled TOPP tools) of an app derived from the template.
---

# Configure the desktop installers

The desktop app is the Streamlit app with an embedded Python, the TOPP tools it
needs and an Electron shell, built by
`.github/workflows/build-windows-executable-app.yaml`. OpenMS itself comes from
the reusable `.github/workflows/openms-windows.yml`, which repackages the
official OpenMS installer (`mode: installer`) or builds a branch (`mode:
source`, hours cold). `electron/` holds the shell, its smoke test
(`scripts/smoke-payload.js`) and the end-to-end test (`scripts/e2e.js`).

Platforms are listed in `app.yaml` under `deploy.desktop`. On the template's
`main` only Windows is built; macOS and Linux arrive with the template's
Electron multi-platform work, and an app adopts them through
`sync-from-template`, not by copying the workflow.

## What an app sets

In `build-windows-executable-app.yaml`, the first three keys live in the top-level `env:` block and `openms-version` lives in `jobs.build-openms.with:` (a reusable-workflow call cannot read `env`):

| Key | What |
|---|---|
| `APP_NAME` | installer and install-folder name, no spaces; also `appId de.openms.<APP_NAME>`. Changing it on a released app gives users a second install. |
| `TOPP_TOOLS` | every TOPP tool the app's `execution()` calls, plus `FileConverter` if `raw` input is accepted. A tool missing here works in Docker and fails only on the desktop. |
| `PYTHON_VERSION` | must match a version with an embeddable build (3.11.x) |
| `openms-version` (in `build-openms.with`) | the OpenMS release; see `upgrade-openms` |

Derive `TOPP_TOOLS` from the spec instead of by hand:

```bash
python - <<'PY'
from utils.app_spec import load_spec
s = load_spec("app.yaml")
tools = {st["tool"] for wf in s.get("workflows", []) for st in wf.get("steps", []) if "tool" in st}
if any("raw" in i.get("types", []) for i in s.get("inputs", {}).values()):
    tools.add("FileConverter")
print(" ".join(sorted(tools)))
PY
```

`settings.json` is switched to offline mode by the workflow itself (`Set to
offline deployment` step); do not commit `online_deployment: false` for that.

## Verify

The workflow runs on every PR to `main`: it installs silently, runs
`smoke-payload.js` (pyOpenMS, each TOPP tool, the Streamlit server) and the
Electron end-to-end test, and uploads screenshots as an artifact. A failing
smoke test names the tool; check `TOPP_TOOLS` first. On a release
(`release: created`) the installer is attached to the release.

## Checklist

- [ ] `APP_NAME` set (and unchanged on an already released app)
- [ ] `TOPP_TOOLS` covers every tool in the spec, plus FileConverter for `.raw`
- [ ] `deploy.desktop` in `app.yaml` matches what is built
- [ ] Smoke and e2e steps green on the PR
