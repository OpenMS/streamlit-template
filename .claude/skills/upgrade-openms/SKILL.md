---
name: upgrade-openms
description: Use when moving an app or the template to a new OpenMS / pyOpenMS release or branch, in the Docker images, the Windows desktop build or requirements.
---

# Upgrade OpenMS

OpenMS appears in four places, which must move together:

| Where | Field |
|---|---|
| `Dockerfile`, `Dockerfile.arm` | `ARG OPENMS_BRANCH=release/<x.y.z>` (TOPP tools and pyOpenMS built from source) |
| `Dockerfile_simple*` / `requirements.txt` | the `pyopenms==` pin |
| `.github/workflows/build-windows-executable-app.yaml` | `openms-version:` passed to `openms-windows.yml` |
| CI (`ci.yml`, `workflow-tests.yml`) | whatever pyOpenMS they install, via requirements |

Do the template first (`upgrade-openms` there, then `sync-from-template` in
each app). An app only upgrades on its own when it needs a release the
template does not yet use, and then says so in the PR.

## Steps

1. **Read the release notes** for removed or renamed TOPP tools and parameters
   the app uses. List tools from the spec:
   `python -c "from utils.app_spec import load_spec; s=load_spec('app.yaml'); print(sorted({t['tool'] for w in s.get('workflows',[]) for t in w.get('steps',[]) if 'tool' in t}))"`
2. **Regenerate parameter defaults.** TOPP defaults come from `ini/<Tool>.ini`
   created by `-write_ini`; a renamed parameter makes a saved `params.json`
   key stop applying without an error. Check presets.json keys against the new
   ini (`tests/test_parameter_presets.py` covers the template's).
3. **Bump all four places** in one commit.
4. **Build the full image** (`docker build -f Dockerfile .`, slow: OpenMS from
   source) and run each workflow on example data inside it. Compare result
   counts (features, PSMs, proteins) with the previous version; a large shift
   is a finding to report, not to hide.
5. **Windows build** runs on the PR; its smoke test checks each tool in
   `TOPP_TOOLS` exists in the new release.
6. **PR** with the comparison.

## Checklist

- [ ] Template first; apps through sync
- [ ] Release notes checked against the tools the spec uses
- [ ] Presets and saved parameter keys still exist in the new ini
- [ ] All four places bumped together
- [ ] Workflows ran in the new image; result counts compared
