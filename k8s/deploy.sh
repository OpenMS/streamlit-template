#!/usr/bin/env bash
# Deploy the whole thing, in the one order that works.
#
#   k8s/deploy.sh              # deploy
#   k8s/deploy.sh --dry-run    # render and check everything, apply nothing
#   k8s/deploy.sh --yes        # skip the context confirmation
#
# WHY A SCRIPT AND NOT `kubectl apply -k`
#
# Three constraints make a single apply impossible, and each of them is a
# silent, expensive failure when a human gets it wrong at the end of a long day:
#
#  1. TWO ROOTS, IN ORDER. k8s/storage/ publishes the StorageClass that
#     k8s/base/workspace-pvc.yaml claims. Applied the other way round every pod
#     sits Pending on a class that does not exist, and the message says nothing
#     about ordering. They cannot be merged into one root either - the reasoning
#     is at the top of k8s/storage/kustomization.yaml, and it is about the
#     namespace transformer clobbering per-object namespaces.
#
#  2. `kubectl apply -k` HAS NO --enable-helm. The storage root inflates the
#     Ganesha chart, so it has to be rendered and piped.
#
#  3. THE NODE ADDRESSES ARE NOT IN THE REPO. See set-node-cidrs.sh. Forgetting
#     that step leaves the shipped placeholder in place and every workspace
#     mount hangs on `mount.nfs: Connection timed out`, forty minutes later,
#     naming nothing.
#
# So this wraps the sequence rather than inventing a mechanism. It applies
# exactly what the documented pipelines apply, in the documented order, and adds
# only the waits between them and a check that the prerequisites are present
# before anything is touched.

set -euo pipefail

cd "$(dirname "$0")/.."

STORAGE_ROOT="${STORAGE_ROOT:-k8s/storage}"
OVERLAY="${OVERLAY:-k8s/overlays/prod}"
STORAGE_NS="${STORAGE_NS:-template-app-storage}"

DRY_RUN=0
ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --yes|-y)  ASSUME_YES=1 ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) printf 'unknown argument: %s\n' "$arg" >&2; exit 2 ;;
    esac
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# --- prerequisites, before anything is touched -------------------------------

for tool in kubectl helm yq python3; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is not on PATH.
       kubectl and helm render the storage root; yq and python3 are used by
       set-node-cidrs.sh to write and bounds-check the node addresses."
done
[ -x "$STORAGE_ROOT/set-node-cidrs.sh" ] || die "$STORAGE_ROOT/set-node-cidrs.sh is missing or not executable"

ctx="$(kubectl config current-context 2>/dev/null || true)"
[ -n "$ctx" ] || die "kubectl has no current context"
srv="$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null || true)"

printf '\ncontext : %s\ncluster : %s\nstorage : %s\noverlay : %s\n' \
    "$ctx" "${srv:-unknown}" "$STORAGE_ROOT" "$OVERLAY"

# The context is confirmed because the two namespaces this touches are named the
# same on every cluster, so there is nothing in the later output that would tell
# you it went to the wrong one.
if [ "$DRY_RUN" -eq 0 ] && [ "$ASSUME_YES" -eq 0 ]; then
    if [ -t 0 ]; then
        printf '\nDeploy to this cluster? [y/N] '
        read -r reply
        case "$reply" in [yY]*) ;; *) die "aborted" ;; esac
    else
        die "not a terminal and --yes was not given; refusing to guess which cluster you meant"
    fi
fi

# --- 1. storage root ---------------------------------------------------------

step "Rendering $STORAGE_ROOT and injecting this cluster's node addresses"
rendered="$(mktemp)"; trap 'rm -f "$rendered"' EXIT
kubectl kustomize --enable-helm "$STORAGE_ROOT" \
    | "$STORAGE_ROOT/set-node-cidrs.sh" > "$rendered"
[ -s "$rendered" ] || die "the storage root rendered nothing"

if [ "$DRY_RUN" -eq 1 ]; then
    step "--dry-run: server-side validating the storage root"
    kubectl apply --dry-run=server -f "$rendered" >/dev/null
    step "--dry-run: server-side validating $OVERLAY"
    kubectl apply --dry-run=server -k "$OVERLAY" >/dev/null
    printf '\nBoth roots render and validate. Nothing was applied.\n'
    exit 0
fi

step "Applying the storage root"
kubectl apply -f "$rendered"

step "Waiting for the NFS server to become Ready"
# Before the overlay, not after: the workspaces PVC binds only once the
# provisioner is running, and a pod that starts first sits Pending on it.
kubectl -n "$STORAGE_NS" rollout status statefulset -l app=nfs-server --timeout=300s

# --- 2. the app --------------------------------------------------------------

step "Applying $OVERLAY"
kubectl apply -k "$OVERLAY"

ns="$(kubectl kustomize "$OVERLAY" | yq 'select(.kind == "Deployment") | .metadata.namespace' | head -n1)"
ns="${ns:-openms}"

step "Waiting for the app to roll out"
for d in $(kubectl kustomize "$OVERLAY" | yq 'select(.kind == "Deployment") | .metadata.name'); do
    kubectl -n "$ns" rollout status "deployment/$d" --timeout=300s
done

# --- done --------------------------------------------------------------------

step "Deployed. Pod placement:"
kubectl -n "$ns" get pods -o wide

cat <<EOF

Two pods on two DIFFERENT nodes above is the acceptance criterion for the whole
storage tier. If everything is on one node, nothing was achieved regardless of
what else passed.

Next: docs/a16-storage-runbook.md section 4 - the cross-node write check, the
POSIX contract, and the Ganesha restart. Run them in order and stop at the first
failure; later steps assume earlier ones passed.
EOF
