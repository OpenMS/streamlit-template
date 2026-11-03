---
name: upgrade-openms
description: Use when moving an app or the template to a new OpenMS / pyOpenMS release or branch, in the Docker images, the Windows desktop build or requirements.
---

# Upgrade OpenMS

OpenMS appears in four places, which must move together:

| Where | Field |
|---|---|
| `Dockerfile`, `Dockerfile.arm` | `ARG OPENMS_BRANCH=release/<x.y.z>` or `v<x.y.z>` (TOPP tools and pyOpenMS built from source; 3.5 and 3.6+ build with the same steps) |
| `Dockerfile_simple*` / `requirements.txt` | the `pyopenms==` pin |
| `.github/workflows/build-windows-executable-app.yaml` | `openms-version:` passed to `openms-windows.yml` |
| CI (`ci.yml`, `workflow-tests.yml`) | whatever pyOpenMS they install, via requirements |

**New releases arrive by themselves.** `.github/workflows/openms-release.yml`
runs weekly in the template and in every app: a repository whose Dockerfile
builds the release just before the newest gets one PR (`openms-release`
branch, made by `.github/scripts/openms_release.py`) that bumps the
Dockerfiles, the pyopenms pin, the desktop default and CI's Python together.
Use this skill to review that PR (steps 1, 2 and 4) or to move to a branch,
a fork or an older release by hand; a repository not on the latest release is
never upgraded automatically.

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
4. **Build the full image** (`docker build -f Dockerfile --build-arg OPENMS_BRANCH=<ref> .`,
   slow: OpenMS from source; or dispatch `build-and-test.yml` with `openms_branch`) and run each workflow on example data inside it. Compare result
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
