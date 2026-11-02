---
name: release-app
description: Use when cutting a release of an app derived from the template, bumping its version, tagging it, publishing images and installers, or writing its release notes.
---

# Release an app

A release is a version bump, a tag, and what CI builds from the tag: the
multi-arch container images, the Apptainer SIF and the desktop installers. The
cluster is updated by changing the image tag the prod overlay pulls.

## Steps

1. **Pick the version** (semver). Breaking change for users (removed workflow,
   changed parameter meaning, new required input) → major; new feature →
   minor; fixes → patch.
2. **Bump** `version` in `settings.json` on a branch, and add the release notes
   where the app shows them (FLASHApp has a "What's new" panel; others use the
   GitHub release body). Notes are written for users: what they can do now,
   what changed in results, what they must re-run. Collect them from merged
   PRs since the last tag:
   ```bash
   git log --first-parent --format='%s' $(git describe --tags --abbrev=0)..HEAD   # merge, squash and rebase merges alike
   ```
3. **PR, merge** to the default branch.
4. **Tag and release** on the merge commit: `v<version>`, or
   `<AppName>-<version>` (e.g. `OpenDDA-1.3`) for an app that names its tags
   that way; `build-and-test.yml` builds both forms. Creating the GitHub
   release (not only the tag) is what triggers the installer build
   (`release: created`) and attaches the installers; the tag push triggers
   `build-and-test.yml`, which publishes `<tag>-full`, `<tag>-simple` and the
   multi-arch manifests to GHCR, plus the SIF.
5. **Wait for both workflows** to finish green before announcing. A release
   without its installer asset is not done.
6. **Deploy**: set `images[0].newTag` in `k8s/overlays/prod/kustomization.yaml`
   to `<tag>-full` (e.g. `v1.3-full` or `OpenDDA-1.3-full`) in a PR; after merge the operator (or the GitOps
   controller, if the cluster has one) applies it. Pinning a tag instead of
   `latest` is what makes a rollback a one-line revert.

Tagging, publishing and deploying are visible to users and cannot be taken
back cleanly; do them only when the user asked for the release.

## Checklist

- [ ] Version chosen by the change type and bumped in settings.json
- [ ] User-facing notes written
- [ ] GitHub release `<tag>` (`v<version>` or `<AppName>-<version>`) created on the merge commit
- [ ] Images, SIF and installers published; both workflows green
- [ ] Overlay pins the new tag
