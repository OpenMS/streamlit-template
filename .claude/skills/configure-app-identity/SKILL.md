---
name: configure-app-identity
description: Use when naming or renaming an app derived from the template, setting its slug, display name, repository, image, hosts or installer name, or when python -m utils.app_spec reports an identity mismatch.
---

# Configure app identity

An app's identity lives in `app.yaml` (`app:` block). This skill writes it
there first and then into every file that repeats it, so the app never ships
with a `template-app` or `streamlit-template` name left over. Run it for a new
app (`new-app-from-spec` calls it) and for a rename.

## Values

| spec field | default |
|---|---|
| `app.slug` | repo name lowercased, `streamlit-`/`-template` stripped |
| `app.name` | the user's display name |
| `app.repository` | `git remote get-url origin` → `owner/name` |
| `app.image` | `ghcr.io/<owner lowercased>/<repo lowercased>` |
| `deploy.k8s.hosts` | `<slug>.webapps.openms.de`, `<slug>.webapps.openms.org` |

Confirm them with the user in one question.

## Where each value goes

| Value | File | Field |
|---|---|---|
| name | `settings.json` | `app-name` |
| repository | `settings.json` | `github-user`, `repository-name` (the Dockerfiles read them too, to bundle the app's own Windows installer) |
| slug | `k8s/overlays/prod/kustomization.yaml` | `namePrefix: <slug>-`, `commonLabels.app` |
| image | `k8s/overlays/prod/kustomization.yaml` | `images[0].newName` |
| hosts | `k8s/overlays/prod/kustomization.yaml` | IngressRoute `Host(...)` patch |
| slug, repository, branch, image | `k8s/argocd/application.yaml`, `k8s/argocd/image-updater.yaml`, `k8s/argocd/argocd-application.yaml`, `k8s/argocd/kustomization.yaml` | Application and ImageUpdater `name`, `repoURL`, `targetRevision`, `<slug>-streamlit-secrets`, `imageName`, `allowTags` matching the app's release tags and their pre-releases; the `<name>-argocd` Application's `name`, `repoURL`, `targetRevision` and the Application name it ignores; the bootstrap URL in kustomization.yaml (`tests/test_argocd_autodeploy.py` checks them) |
| name (no spaces) | `.github/workflows/build-windows-executable-app.yaml` | `env.APP_NAME`; it becomes the installer file name and the Electron `appId` `de.openms.<APP_NAME>` |
| slug | `docker-compose.yml` | service, `image`, `container_name`, and the `workspaces-<repository-name>` volume |
| repository | `k8s/base/{streamlit,rq-worker}-deployment.yaml`, `k8s/base/cleanup-cronjob.yaml` | `WORKSPACES_DIR=/workspaces-<repository-name>` (only on a new app; on a deployed one it moves user data) |
| logo | `assets/*.svg` + `settings.json` | `branding`: `page_icon`, `logo`, `logo_icon`, `app_icon` (each one path or `{"light", "dark"}`), `logo_size`; see the README section "Logo" |
| logo | `electron/build/icon.png` (512 px or more), `electron/build/icon.ico` | the desktop app and installer icon |

Use `configure-app-settings` for the remaining settings.json keys and
`configure-k8s-deployment` for capacity.

## Renaming a deployed app

The k8s names are a **migration** for a deployed app (new
PVC, new share), and `APP_NAME` changes the install location of the
desktop app, so existing users get a second install. List both to the user and
change them only on explicit approval; the display name, hosts and image can
change freely.

## Check

```bash
python -m utils.app_spec
grep -rn "template-app\|streamlit-template\|StreamlitTemplateApp" \
  --include='*.json' --include='*.yaml' --include='*.yml' --include='Dockerfile*' . \
  | grep -v '^./app.yaml' | grep -v '#'
```

The grep should print only lines that refer to the template on purpose (the
`template:` block, sync job, reusable workflow `uses:` lines).

## Checklist

- [ ] `app.yaml` `app:` block written first
- [ ] Every row of the table updated
- [ ] `python -m utils.app_spec` clean, leftover-name grep clean
- [ ] Deployed app: migration items listed, changed only with approval
