# Review queue

Generating PRs is cheap; review is the bottleneck. Every app receives a weekly
template-sync PR, dependabot adds more, and if each one waits for the same full
review, the queue grows faster than it drains. The review queue sorts PRs by
risk and lets GitHub merge the low-risk class once the required checks pass.

| Class | Examples | Who merges |
|---|---|---|
| Automatic | dependabot patch/minor; a template-sync PR without any conflict | GitHub auto-merge, after the required checks pass |
| Light review | template-sync PR with resolved app-owned conflicts; `app.yaml`, presets, skills, docs | one reviewer, scoped to the diff |
| Full review | `src/workflow/`, `.github/`, `k8s/`, `docker/`, Dockerfiles (`.github/CODEOWNERS`) | the code owner, plus one workflow run on example data |

## What is automated

- `.github/workflows/auto-merge.yml` sets dependabot patch and minor PRs to
  auto-merge (squash). Major updates wait for a human.
- `.github/workflows/template-sync.yml` sets a sync PR without any conflict to
  auto-merge with a **merge commit** (never squash, or the next sync conflicts
  on the same lines). A sync that resolved app-owned conflicts is left for a
  review. `sync.auto_merge: false` in `app.yaml` turns this off for an app.
- Both enable auto-merge only when the default branch has **required status
  checks**. Without them GitHub would merge before any test ran, so they log a
  notice and leave the PR alone.
- `.github/CODEOWNERS` requests the owner's review on full-review paths.

## One-time setup per repository

Admin rights are needed. One command per repository sets the merge options
(auto-merge, merge commits and squash allowed, merged branches deleted) and a
ruleset on the default branch: changes only through PRs, the listed checks
required, no force-push or deletion; repository admins can bypass.

```bash
.github/scripts/setup-review-queue.sh OWNER/REPO "CHECK" ["CHECK" ...]
```

Name only **fast checks that pass on the default branch today**. A required
check that is red, or never reported for a PR, blocks every merge. The Docker
image builds and desktop installers take up to an hour and are better left
optional. Check names are the ones shown on a PR (a job named `build` in two
workflows must pass in both).

Then add the `TEMPLATE_SYNC_TOKEN` secret to each app (contents, pull-requests,
issues and workflows write). Without it the sync cannot push template changes
to `.github/workflows/`, and its PR triggers no checks, so auto-merge would
wait forever.

## Keeping it drained

- Close or rebase stale PRs once, then keep the open count low (under 10) and
  triage weekly.
- An open sync PR is updated to the latest template by each run, unless
  someone pushed to it by hand; then the run comments and leaves it alone.
- Optional for the template: a merge queue re-tests each PR on top of the
  previous one, so two green PRs cannot combine into a red `main`. It needs
  every required workflow to also run `on: merge_group`.
