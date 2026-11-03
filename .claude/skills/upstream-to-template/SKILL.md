---
name: upstream-to-template
description: Use when a change made in, or needed by, one app (quantms-web, umetaflow, FLASHApp, OpenDIAKiosk) touches template-owned code, so it must go to OpenMS/streamlit-template first and come back through a sync.
---

# Upstream a change to the template

Project rule: a change that applies to the template is made in the template
first, then reaches the apps by merging the template. This skill decides
whether a change is template material and moves it there.

## Is it template material?

It is when **any** of these holds:

- it touches a template-owned file (anything not in `sync.app_owned` of the
  app's `app.yaml`): `src/workflow/`, `src/common/`, `src/data_import/`,
  `docker/`, `k8s/base`, `k8s/storage`, `k8s/ci-storage`, CI, `electron/`, `.claude/`;
- a second app would want it;
- it fixes a bug the template also has.

It is not when it is the app's science (its workflow, python-tools, result
pages) or its identity (names, hosts, presets).

A change that is app-specific *behaviour* in template-owned code becomes a
template **option**: a parameter with the old behaviour as default, a
`settings.json` key, or a hook the app overrides. Never a fork of the file.

## Steps

1. **Separate it.** In the app, split the change so the template part is its
   own commit(s) touching only template-owned files.
2. **Port it.** In a template checkout on a feature branch, apply it
   (`git format-patch` from the app + `git am -3`, or by hand when the files
   have drifted). Replace app names with template ones.
3. **Prove it in the template**: tests (`python -m pytest test_gui.py tests/`),
   pylint, and the template's example workflow if the change is in the
   workflow framework. Add a test when the change fixes a bug.
4. **Template PR**, describing which app needed it and why.
5. **In the app**, either wait for the template PR to merge and run
   `sync-from-template`, or, if the app cannot wait, merge the template PR's
   branch into the app (`git merge template/<branch>`). Do not cherry-pick: a
   cherry-pick re-conflicts at the next sync, a merge of the same commits does
   not.
6. **Docs**: update the template's `CLAUDE.md` / `docs/` if the change alters a
   pattern, so every app's next sync carries the explanation too.

## Checklist

- [ ] Template part split from app part
- [ ] App-specific behaviour expressed as an option with the old default
- [ ] Template PR with tests; apps get it by merge, never cherry-pick
