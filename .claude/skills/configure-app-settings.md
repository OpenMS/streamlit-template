# Configure App Settings

Set up app-level configuration (settings, Dockerfile, README) for a new or forked OpenMS streamlit app. Run before `configure-docker-compose-deployment` or `configure-k8s-deployment`.

## Instructions

1. **Ask the user** for:
   - App name (display name, e.g., "UmetaFlow")
   - GitHub user/organization and repository name
   - Whether the app needs TOPP tools (determines Dockerfile choice)
   - Deployment mode: local only, online, or both

2. **Update `settings.json`**:

    ```json
    {
        "app-name": "Your App Name",
        "github-user": "YourGitHubUser",
        "repository-name": "your-repo-name",
        "version": "0.1.0",
        "online_deployment": false,
        "enable_workspaces": true
    }
    ```

    Key fields: `app-name`, `github-user`, `repository-name`, `version`, `online_deployment`, `enable_workspaces`. `max_threads` (a nested object with `local`/`online` keys in `settings.json`) caps worker parallelism — tune it if your cluster or host has specific CPU constraints.

3. **Choose and update Dockerfile**:

   - **`Dockerfile`** (full): builds OpenMS from source with TOPP tools. Use when the app runs TOPP tools via `executor.run_topp()`. Update:
     - `GITHUB_USER` and `GITHUB_REPO` environment variables
     - Python dependencies in `environment.yml`
     - Entrypoint if main file is not `app.py`

   - **`Dockerfile_simple`** (lightweight): installs pyOpenMS via pip only. Use when the app only uses pyOpenMS Python API. Update:
     - `GITHUB_USER` and `GITHUB_REPO` environment variables
     - Python dependencies in `requirements.txt`

4. **Update `README.md`** with the new app name, description, and instructions.

## Dockerfile Decision Guide

| App Type | Dockerfile | Why |
|----------|-----------|-----|
| Uses TOPP tools (FeatureFinder, etc.) | `Dockerfile` | Needs compiled OpenMS binaries |
| Pure pyOpenMS / Python only | `Dockerfile_simple` | Lighter, faster build |
| Vue.js components (like FLASHApp) | `Dockerfile` + build step | Needs npm build for JS components |

## Reference Files

- App settings: `settings.json`
- Docker: `Dockerfile`, `Dockerfile_simple`
- Build docs: `docs/build_app.md`

## Real-World Examples

- **quantms-web**: Full Dockerfile with TOPP tools, online deployment with Redis queue
- **umetaflow**: Full Dockerfile, metabolomics TOPP tools, hosted at abi-services.cs.uni-tuebingen.de
- **FLASHApp**: Full Dockerfile + Vue.js component build step, `develop` as default branch

## Checklist

- [ ] `settings.json` updated with app name, GitHub user/repo, version
- [ ] Correct Dockerfile chosen and configured (`GITHUB_USER`, `GITHUB_REPO`)
- [ ] `requirements.txt` or `environment.yml` updated with dependencies
- [ ] `README.md` updated

## Next Steps

Run `configure-docker-compose-deployment` and/or `configure-k8s-deployment` to set up the deployment path(s).
