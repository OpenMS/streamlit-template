# Configure Kubernetes Deployment

Create a Kustomize overlay for deploying a forked OpenMS streamlit app to Kubernetes.

## Prerequisite

Run `configure-app-settings` first. This skill assumes `settings.json`, the Dockerfile, and app metadata are already configured.

## Cluster Prerequisites

- `kubectl` configured for the target cluster
- A storage class that supports `ReadWriteOnce` volumes (default: `cinder-csi` for de.NBI / OpenStack)
- An ingress controller (default: Traefik; nginx also supported via the base `Ingress` resource)
- Read access to GHCR for pulling the app image
- A DNS record pointing to the cluster's ingress load balancer

## Instructions

1. **Let CI build and push the image.**

   Push your changes to `main` or create a tag. The workflow `.github/workflows/build-and-test.yml` builds both the full and lightweight (`-simple`) variants and publishes them to `ghcr.io/<your-org>/<your-repo>:<tag>-full` and `:<tag>-simple` respectively. The unsuffixed `latest` tag tracks the full variant on the `main` branch.

2. **Copy the template overlay.**

    ```bash
    cp -r k8s/overlays/template-app k8s/overlays/<your-app-name>
    ```

3. **Edit `k8s/overlays/<your-app-name>/kustomization.yaml`**:

   - Change `namePrefix` from `template-app-` to `<your-app-name>-`
   - Change `commonLabels.app` from `template-app` to `<your-app-name>`
   - Change `images[0].newName` to `ghcr.io/<your-org>/<your-repo>`
   - In the IngressRoute patch, update:
     - the `Host(...)` match — change the quoted hostname to your own
     - the service name reference from `template-app-streamlit` to `<your-app-name>-streamlit`
   - In both Deployment patches (`streamlit` and `rq-worker`), update the Redis URL from `redis://template-app-redis:6379/0` to `redis://<your-app-name>-redis:6379/0`

   The overlay leaves the nginx `Ingress` unpatched because production deployments use Traefik. If you are deploying to an nginx-only cluster, substitute an Ingress host patch for the IngressRoute patch.

4. **Validate the overlay builds.**

    ```bash
    kubectl kustomize k8s/overlays/<your-app-name>/
    ```

    Should print the rendered manifests with no errors.

5. **Deploy.**

    ```bash
    kubectl apply -k k8s/overlays/<your-app-name>/
    ```

6. **Verify.**

    ```bash
    kubectl -n openms get pods -l app=<your-app-name>
    kubectl -n openms rollout status deployment/<your-app-name>-streamlit --timeout=120s
    ```

    Smoke-test the ingress URL in a browser.

## Reference Files

- Overlay template: `k8s/overlays/template-app/kustomization.yaml`
- Base manifests: `k8s/base/*.yaml`
- CI: `.github/workflows/build-and-test.yml` (unified build + lint + kind integration), `.github/workflows/ghcr-cleanup.yml` (scheduled tag retention)
- Full reference: see the "Developers Guide: Kubernetes Deployment" Documentation page in the running Streamlit app.

## Checklist

- [ ] Image built and pushed to GHCR (via CI or manual push to `main`/tag)
- [ ] Overlay copied to `k8s/overlays/<your-app-name>/`
- [ ] `namePrefix`, `commonLabels.app`, `images[0].newName` updated
- [ ] IngressRoute patch updated (host + service reference)
- [ ] Redis URL updated in both Deployment patches
- [ ] `kubectl kustomize` succeeds
- [ ] `kubectl apply -k` succeeds
- [ ] All pods Running, `rollout status` succeeds
- [ ] App accessible via the ingress hostname
