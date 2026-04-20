# Kubernetes Deployment

This guide covers deploying an OpenMS streamlit app to a Kubernetes cluster using the Kustomize-based manifests under `k8s/`. For the docker-compose deployment path, see the "Developers Guide: Deployment" page.

## 1. Overview

The template ships a full Kubernetes deployment stack designed for the de.NBI cluster (OpenStack + `cinder-csi` storage + Traefik ingress). The stack includes:

- A Streamlit Deployment serving the web UI
- A Redis Deployment as the job-queue backing store
- An RQ worker Deployment running background workflows
- A nightly cleanup CronJob for stale workspaces
- A shared PersistentVolumeClaim holding per-user workspace data
- A Traefik IngressRoute routing external traffic to the Streamlit service (with session affinity)

Every production OpenMS webapp (quantms-web, umetaflow, FLASHApp) deploys via this stack.

## 2. Architecture

```
                              ┌────────────────────────┐
                              │  Traefik IngressRoute  │
                              │  Host(<your-hostname>) │
                              │  (sticky cookie)       │
                              └───────────┬────────────┘
                                          │
                                          ▼
                              ┌────────────────────────┐
                              │   Streamlit Service    │
                              │     ClusterIP :8501    │
                              └───────────┬────────────┘
                                          │
                                          ▼
                ┌─────────────────────────────────────────┐
                │        Streamlit Deployment             │
                │        (N replicas, default 2)          │
                │                                         │
                │   [pod affinity: co-locate with         │
                │    rq-worker + cleanup-cronjob pods]    │
                └────────┬────────────────────────┬───────┘
                         │ REDIS_URL              │
                         │                        │ /workspaces-...
                         ▼                        │
            ┌────────────────────────┐            │
            │    Redis Deployment    │            │
            │      (1 replica)       │            ▼
            └────────────────────────┘   ┌────────────────────────┐
                         ▲               │    Workspace PVC       │
                         │               │   ReadWriteOnce 500Gi  │
                         │ REDIS_URL     │   (cinder-csi)         │
                         │               └────────────────────────┘
                         │                        ▲
                         │                        │
                ┌────────┴───────────────────────┴────────┐
                │          RQ Worker Deployment           │
                │             (1 replica)                 │
                │       rq worker openms-workflows        │
                └─────────────────────────────────────────┘

                ┌─────────────────────────────────────────┐
                │      Cleanup CronJob (nightly 3 UTC)    │
                │      python clean-up-workspaces.py      │
                │      (mounts same PVC)                  │
                └─────────────────────────────────────────┘
```

### Components

| Component | Purpose | Replicas | Shares PVC? |
|-----------|---------|----------|-------------|
| Streamlit Deployment | Serves the web UI | N (default 2) | Yes |
| Redis Deployment | Job-queue backing store | 1 | No |
| RQ Worker Deployment | Runs background workflows from the Redis queue | 1 | Yes |
| Cleanup CronJob | Removes stale workspaces nightly at 03:00 UTC | — | Yes |
| Workspace PVC | Shared `/workspaces-*` directory for session data | — | — |
| Traefik IngressRoute | External HTTP entrypoint with sticky sessions | — | — |
| nginx Ingress | Alternative HTTP entrypoint used by the CI kind cluster | — | — |

### Pod affinity

All workspace-using pods (Streamlit, RQ worker, Cleanup) carry a `volume-group: workspaces` label and a `requiredDuringSchedulingIgnoredDuringExecution` pod-affinity rule keyed on `kubernetes.io/hostname`. This forces every workspace-using pod onto the same node, so they can share the `ReadWriteOnce` PVC.

Co-location is a placement constraint, not a replica cap. The Streamlit deployment can scale to N replicas — they all land on the same node alongside the worker.

### Ingress

Production deployments use the Traefik `IngressRoute`. The nginx `Ingress` is kept in `k8s/base/` because the CI integration test (`.github/workflows/k8s-manifests-ci.yml`) uses a kind cluster with an nginx ingress controller and filters out Traefik CRDs at apply time.
