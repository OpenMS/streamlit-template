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
3. **PR, merge** to the default branch. The bump is merged **before** the
   release exists: never create a tag, and never hand anyone a release link
   (a prefilled `releases/new?tag=...` URL), while `version` in
   `settings.json` on the target commit is not the tag's version. Check it
   with `python .github/scripts/release_version.py check <tag>` on that
   commit.
4. **Tag and release** on the merge commit: `v<version>`, or
   `<AppName>-<version>` (e.g. `OpenDDA-1.3`) for an app that names its tags
   that way; `build-and-test.yml` builds both forms. Creating the GitHub
   release (not only the tag) is what triggers the installer build
   (`release: created`) and attaches the installers; the tag push triggers
   `build-and-test.yml`, which publishes `<tag>-full`, `<tag>-simple` and the
   multi-arch manifests to GHCR, plus the SIF.
   `release-version.yml` compares the tag with `settings.json` on every
   release tag. A release made before its bump fails that check and gets a
   PR setting the version on the default branch (merge it); the images and
   installers built from the tag carry the tag's version anyway, because
   `build-image.yml` and `build-desktop-app.yaml` write it into
   `settings.json` before building.
5. **Wait for both workflows** to finish green before announcing. A release
   without its installer asset is not done.
6. **Deploy**: nothing to do. With the app's Argo CD Image Updater (cluster
   configuration, kept outside the repository) the cluster moves to the new release
   image, pre-releases included, within a few minutes of the image being
   published. Do not pin `images[0].newTag` in a PR; the overlay's tag is
   only where a new Application starts. To roll back, ask the cluster's admin to
   narrow the ImageUpdater's `allowTags` to the release to stay on. On a cluster without the ImageUpdater,
   set `newTag` to `<tag>-full` and apply the overlay.

Tagging, publishing and deploying are visible to users and cannot be taken
back cleanly; do them only when the user asked for the release.

## Checklist

- [ ] Version chosen by the change type and bumped in settings.json
- [ ] Bump merged before the tag or a release link exists (`release_version.py check <tag>` passes)
- [ ] User-facing notes written
- [ ] GitHub release `<tag>` (`v<version>` or `<AppName>-<version>`) created on the merge commit
- [ ] Images, SIF and installers published; build workflows and `Release version` green
- [ ] If `Release version` failed (the tag came before its bump): merge its `release-version` PR. The release stays as it is, since its images and installers already carry the tag's version; the failed check stays red on that tag as the record
- [ ] On a cluster without the ImageUpdater, the overlay pins the new tag
