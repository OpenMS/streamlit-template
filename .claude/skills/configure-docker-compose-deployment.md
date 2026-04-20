# Configure Deployment

Set up Docker, settings, and CI/CD configuration for a new or forked app.

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

Key fields: `app-name`, `github-user`, `repository-name`, `version`, `online_deployment`, `max_threads`.

3. **Choose and update Dockerfile**:

   - **`Dockerfile`** (full): builds OpenMS from source with TOPP tools. Use when the app runs TOPP tools via `executor.run_topp()`. Update:
     - `GITHUB_USER` and `GITHUB_REPO` environment variables
     - Python dependencies in `environment.yml`
     - Entrypoint if main file is not `app.py`

   - **`Dockerfile_simple`** (lightweight): installs pyOpenMS via pip only. Use when the app only uses pyOpenMS Python API. Update:
     - `GITHUB_USER` and `GITHUB_REPO` environment variables
     - Python dependencies in `requirements.txt`

4. **Update `docker-compose.yml`**:

```yaml
services:
  your-app-name:
    build: .
    ports:
      - "8501:8501"
    volumes:
      - workspaces-your-repo-name:/workspaces-your-repo-name

volumes:
  workspaces-your-repo-name:
```

Service name and volume name should use the repository name.

5. **Update `clean-up-workspaces.py`**:

```python
workspaces_directory = Path("/workspaces-your-repo-name")
```

6. **Update `README.md`** with the new app name, description, and instructions.

## Dockerfile Decision Guide

| App Type | Dockerfile | Why |
|----------|-----------|-----|
| Uses TOPP tools (FeatureFinder, etc.) | `Dockerfile` | Needs compiled OpenMS binaries |
| Pure pyOpenMS / Python only | `Dockerfile_simple` | Lighter, faster build |
| Vue.js components (like FLASHApp) | `Dockerfile` + build step | Needs npm build for JS components |

## Reference Files

- App settings: `settings.json`
- Docker: `Dockerfile`, `Dockerfile_simple`, `docker-compose.yml`
- Build docs: `docs/build_app.md`
- Deployment docs: `docs/deployment.md`
- CI/CD: `.github/workflows/` (Docker build, Windows exe, linting, tests)
- Workspace cleanup: `clean-up-workspaces.py`

## Real-World Examples

- **quantms-web**: Full Dockerfile with TOPP tools, online deployment with Redis queue
- **umetaflow**: Full Dockerfile, metabolomics TOPP tools, hosted at abi-services.cs.uni-tuebingen.de
- **FLASHApp**: Full Dockerfile + Vue.js component build step, `develop` as default branch

## Checklist

- [ ] `settings.json` updated with app name, GitHub user/repo, version
- [ ] Correct Dockerfile chosen and configured (GITHUB_USER, GITHUB_REPO)
- [ ] `docker-compose.yml` updated with service name and volume
- [ ] `clean-up-workspaces.py` updated with workspace directory path
- [ ] `requirements.txt` or `environment.yml` updated with dependencies
- [ ] `README.md` updated
