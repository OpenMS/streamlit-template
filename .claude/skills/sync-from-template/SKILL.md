---
name: sync-from-template
description: Use when bringing template changes into an app (merging OpenMS/streamlit-template into quantms-web, umetaflow, FLASHApp or another fork), when resolving a template-sync conflict, or when the scheduled sync job opened an issue.
---

# Sync an app from the template

Merge the template into an app, resolve conflicts by ownership, prove the app
still works, and open one PR. The scheduled job
(`.github/workflows/template-sync.yml`) does the clean cases on its own; this
skill is for the ones it hands to a human, and for first syncs.

## Rules

- **Merge, never rebase or squash.** A merge keeps the template's commits in
  the app's history, so the next sync only sees what is new. A squashed sync
  makes every later sync re-conflict on the same lines.
- **Ownership decides conflicts.** `sync.app_owned` in `app.yaml` lists the
  app's files. A conflict there keeps the app's side unless the template change
  is one the app needs (read it first). Everything else is template-owned: take
  the template's side and re-apply the app's change on top only if the app
  really needs to differ, and then the difference belongs in the template as an
  option (`upstream-to-template`).
- **One sync PR at a time**, titled `Sync with template (<short sha>)`.
- **Clean syncs merge themselves.** The job sets a sync PR without any conflict
  to auto-merge once the required checks pass (`docs/review-queue.md`). A PR
  with resolved app-owned conflicts, and any sync done with this skill, waits
  for a review: merge it with a merge commit.

## Steps

```bash
git remote add template https://github.com/OpenMS/streamlit-template.git 2>/dev/null
git fetch template main
git merge-base HEAD template/main || echo "NO COMMON HISTORY"
git fetch origin template-sync 2>/dev/null && git log --oneline origin/template-sync -5   # an open sync branch?
# Reuse it if it exists (it may already hold the bot's merge or someone's resolution):
git checkout template-sync 2>/dev/null || git checkout -b template-sync --track origin/template-sync 2>/dev/null || git checkout -b template-sync
git merge --no-ff template/main
```

**No common history** (the app was created by copying files): do a one-time
`git merge --allow-unrelated-histories template/main`, resolve every conflict by
the rules above, and say so in the PR. After it merges, the scheduled job works.

**Conflicts:**

```bash
python - <<'PY'
import subprocess
from utils.app_spec import load_spec, is_app_owned
spec = load_spec("app.yaml")
files = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"],
                       capture_output=True, text=True).stdout.split()
for f in files:
    print("app-owned     " if is_app_owned(spec, f) else "template-owned", f)
PY
```

Before an `app.yaml` exists in the app (first sync), treat `app.py`,
`settings.json`, `default-parameters.json`, `presets.json`, `content/`,
`src/Workflow.py` and the app's own workflow classes, `src/python-tools/`,
`example-data/`, `assets/`, `README.md` and `k8s/overlays/` as app-owned, and
add `app.yaml` in the same PR (`configure-app-identity`).

Recurring hot spots:

| File | What to do |
|---|---|
| `requirements.txt` | union of both; keep the app's pins where both pin |
| `settings.json` | keep the app's values, add new template keys with their defaults |
| `.github/workflows/build-windows-executable-app.yaml` | take the template's, then restore the app's `APP_NAME` and `TOPP_TOOLS` |
| `Dockerfile*` | take the template's, restore the app's `GITHUB_REPO` and extra build steps |
| `k8s/storage/*`, `k8s/ci-storage/*` | take the template's; they carry no app names. A cluster's two storage values (share type, node subnet) live in the copy the operator applies, not in the app |
| `.claude/skills/*` | always the template's; an app-specific skill gets its own directory name |

**New template features** the app should adopt (a new storage tier, a new
settings block) are part of the sync, not a follow-up: list them in the PR
body with what the app has to set.

## Prove it

```bash
python -m utils.app_spec
python -m pytest test_gui.py tests/      # or the app's own test command
pylint $(git ls-files '*.py') --errors-only --disable=C0103,C0114,C0301,C0411,W0212,W0631,W0602,W1514,W2402,E0401,E1101,F0001,R1732
```

Then start the app and run one workflow on the example data. Push
`template-sync` and open the PR with: the template range
(`<old merge-base>..<template sha>`), the conflicts and how each was resolved,
and anything the app must now configure.

## Checklist

- [ ] Merge (not rebase) of `template/main`
- [ ] Every conflict resolved by ownership, and listed in the PR
- [ ] New template features adopted or listed as follow-ups with a reason
- [ ] `utils.app_spec`, tests and pylint pass; one workflow ran
