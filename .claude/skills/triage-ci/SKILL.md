---
name: triage-ci
description: Use when a CI run of the template or an app fails (build-and-test, kind/nginx/traefik, apptainer, Windows installer, pytest, pylint) and the cause must be found and fixed.
---

# Triage a CI failure

Find which job failed and why, reproduce it locally where possible, fix the
cause, and never make CI green by skipping, disabling or weakening a check.

## Map the failure

| Job (workflow) | What it proves | Reproduce locally |
|---|---|---|
| `ci.yml` | `pytest test_gui.py tests/` | same command, from the repo root, Python 3.10 |
| `workflow-tests.yml` | `pytest test.py` (downloads data) | same, needs network |
| `pylint.yml` | errors-only lint | the pylint command in `CLAUDE.md` |
| `build-and-test.yml` static job | kubeconform + `ci-assertions.sh` static asserts | `source .github/scripts/ci-assertions.sh; assert_<name>` (needs mikefarah `yq`, `helm`, `kubectl`) |
| `build-*` (via `build-image.yml`) | Docker images build | `docker build -f Dockerfile .` |
| `test-apptainer` | image runs read-only under Apptainer | needs apptainer; read the entrypoint log artifact |
| `test-nginx` / `test-traefik` | full kind deploy incl. the NFS storage tier | `kind create cluster --config .github/kind-config.yaml`, then the job's steps |
| `build-windows-executable-app` | Windows installer, smoke + e2e | Windows only; read the smoke output, it names the missing tool |

## Steps

1. **Read the failing step's log**, not the summary. Find the first error;
   later ones are usually consequences.
2. **Classify**: our change / flaky infrastructure (runner disk, registry
   rate limit, network) / upstream (a dependency release, an OpenMS branch
   change).
3. **Flaky** only with evidence: the failing step shows an infrastructure cause (runner lost, registry 429/5xx, DNS or network timeout, disk full), or the same check passed on recent runs of the base branch with the same inputs. Re-run once to confirm. Two identical failures do not prove the code is at fault when the error itself is infrastructural; check the job's history before changing code. A failure in our own assertion or test with no infrastructure error is ours.
4. **Reproduce** with the table above, and show the same check failing.
5. **Fix the cause**, then show the same check passing locally.
6. **Recurring patterns:**
   - `FAIL:` lines from `ci-assertions.sh` say which file and field; the
     assertion is the contract, change the manifest, not the assertion.
   - Storage class: `assert_storage_class_contract` → `k8s/base/workspace-pvc.yaml`, `k8s/ci-storage/ganesha-values.yaml` and the production class pinned as `CI_ASSERT_PROD_MOUNT_OPTIONS` must agree.
   - `No space left on device` on kind/build jobs: the "Free disk space" step
     did not free enough; image size grew.
   - Windows smoke test names a TOPP tool: it is missing from `TOPP_TOOLS`.
   - AppTest page failures after a template sync: a page uses a session key
     only `page_setup()` creates; check the page calls it first.
7. **Push the fix** with the reproduction in the PR or commit message.

## Never

Skip or `xfail` a test to get green, delete an assertion, add
`continue-on-error`, push an empty commit to re-trigger, or close and reopen a
PR to re-run CI.

## Checklist

- [ ] First real error found and classified
- [ ] Reproduced locally (or reason it cannot be)
- [ ] Cause fixed; same check shown passing
