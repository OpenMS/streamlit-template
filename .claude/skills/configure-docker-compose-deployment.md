# Configure Docker Compose Deployment

Set up docker-compose-specific configuration for a new or forked OpenMS streamlit app.

## Prerequisite

Run `configure-app-settings` first. This skill assumes `settings.json`, the Dockerfile, and app metadata (app name, GitHub user/repo, README) are already configured.

## Instructions

1. **Update `docker-compose.yml`**:

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

2. **Update `clean-up-workspaces.py`**:

    ```python
    workspaces_directory = Path("/workspaces-your-repo-name")
    ```

3. **Build and run**:

    ```bash
    docker-compose up --build -d
    ```

## Reference Files

- Docker Compose: `docker-compose.yml`
- Workspace cleanup: `clean-up-workspaces.py`
- Full reference: see the "Developers Guide: Deployment" Documentation page in the running Streamlit app.

## Checklist

- [ ] `docker-compose.yml` updated with service name and volume
- [ ] `clean-up-workspaces.py` updated with workspace directory path
- [ ] Successfully builds and starts with `docker-compose up --build -d`
- [ ] App accessible at http://localhost:8501
