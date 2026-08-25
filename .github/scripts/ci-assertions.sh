#!/usr/bin/env bash
# Cluster and manifest assertions for the multi-node deployment work.
#
# Source this file inside a workflow step, then call the assertions:
#
#   - name: Assert cross-node write visibility
#     run: |
#       source .github/scripts/ci-assertions.sh
#       assert_cross_node_write_visible
#
# Every assertion prints exactly one `PASS: ...` or `FAIL: ...` line and
# returns non-zero on failure, so it fails the step under the default `bash -e`
# shell. None of them can pass vacuously: an assertion that finds nothing to
# inspect fails rather than reporting success.
#
#   assert_two_pods_two_nodes        two pods, one workspace volume, two nodes
#   assert_cross_node_write_visible  each pod reads the other pod's writes
#   assert_posix_contract            the mount really is NFS; absolute symlink,
#                                    atomic rename, and flock that excludes a
#                                    holder on the *other* node
#   assert_survives_nfs_restart      a workflow running throughout a Ganesha
#                                    restart completes, with no lost output
#   assert_stable_identity_across_restart
#                                    file handles survive a Ganesha restart
#   assert_fsids_pinned              static; the storage root pins
#                                    device-based-fsids off
#   assert_netpol_string_matches_overlay
#   assert_netpol_admits_every_node
#   assert_storage_identity_values
#                                    static; the storage NetworkPolicy admits
#                                    exactly the overlay's commonLabels.app, in
#                                    the overlay's namespace, on 2049 alone
#   assert_no_node_pinning_anywhere  static; no nodeSelector, nodeName,
#                                    nodeAffinity or memory tier
#   assert_workers_spread_across_nodes
#                                    every worker replica is Running, on more
#                                    than one node, within the declared maxSkew
#   assert_worker_qos_guaranteed     worker pods are Running and Guaranteed QoS
#
# Inputs, all optional; the defaults are discovered from the cluster:
#   CI_ASSERT_NS       namespace of the deployment    (default: openms)
#   CI_ASSERT_APP      value of the `app` label       (default: $SLUG, else
#                      .commonLabels.app of the overlay)
#   CI_ASSERT_OVERLAY  kustomize root to render       (default: k8s/overlays/prod)
#   CI_ASSERT_BASE     kustomize root the overlay      (default: k8s/base)
#                      builds on, read for its namespace
#   CI_ASSERT_CLAIM    workspace PVC name             (default: discovered)
#   CI_ASSERT_MOUNT    workspace mount path           (default: the WORKSPACES_DIR
#                      the deployments use)
#   CI_ASSERT_IMAGE    image for throwaway pods       (default: the app image,
#                      which is already on every kind node so nothing pulls)
#   CI_ASSERT_TIMEOUT  seconds to wait for a pod      (default: 180)
#   CI_ASSERT_STORAGE_NS    namespace of the NFS server
#                           (default: template-app-storage)
#   CI_ASSERT_STORAGE_ROOT  kustomize root serving it    (default: k8s/storage)

CI_ASSERT_NS="${CI_ASSERT_NS:-openms}"
CI_ASSERT_OVERLAY="${CI_ASSERT_OVERLAY:-k8s/overlays/prod}"
# The overlay the kind jobs actually apply. Scanned for pinning too:
# prod is the one under test, but a nodeSelector reintroduced here would
# pin every pod CI ever schedules while prod stayed clean.
CI_ASSERT_CI_OVERLAY="${CI_ASSERT_CI_OVERLAY:-k8s/overlays/ci}"
CI_ASSERT_MOUNT="${CI_ASSERT_MOUNT:-/workspaces-streamlit-template}"
CI_ASSERT_TIMEOUT="${CI_ASSERT_TIMEOUT:-180}"
CI_ASSERT_BASE="${CI_ASSERT_BASE:-k8s/base}"
CI_ASSERT_STORAGE_NS="${CI_ASSERT_STORAGE_NS:-template-app-storage}"
CI_ASSERT_STORAGE_ROOT="${CI_ASSERT_STORAGE_ROOT:-k8s/storage}"
# Seconds to wait for the NFS server to come back, and for a client operation to
# get through afterwards. NFSv4.1's grace period is ~90s by default, during
# which state-mutating operations are refused and a `hard` mount simply retries.
CI_ASSERT_RESTART_TIMEOUT="${CI_ASSERT_RESTART_TIMEOUT:-300}"
# assert_survives_nfs_restart: how many one-per-second records the stand-in
# workflow writes, and how long it is then given to finish. The workflow has to
# outlast the restart *plus* the ~90s grace period with time to spare, or the
# assertion measures the timeout instead of the filesystem.
CI_ASSERT_WORKFLOW_RECORDS="${CI_ASSERT_WORKFLOW_RECORDS:-60}"
CI_ASSERT_WORKFLOW_TIMEOUT="${CI_ASSERT_WORKFLOW_TIMEOUT:-420}"
# Trees scanned by assert_no_node_pinning_anywhere. Space separated.
CI_ASSERT_PINNING_PATHS="${CI_ASSERT_PINNING_PATHS:-k8s .github/kind-config.yaml}"

# --- reporting -------------------------------------------------------------
#
# _ci_fail only reports; the caller decides when to return, so that cleanup
# still runs and every failure of a multi-part assertion is printed rather than
# just the first one.

_ci_pass() {
    printf 'PASS: %s\n' "$*"
}

_ci_fail() {
    printf 'FAIL: %s\n' "$*" >&2
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
        printf '::error title=CI assertion failed::%s\n' "$*"
    fi
}

# --- discovery -------------------------------------------------------------

_ci_have() {
    command -v "$1" >/dev/null 2>&1
}

_ci_require() {
    # Fail loudly on a missing tool rather than silently skipping the check.
    local missing="" _ci_tool
    for _ci_tool in "$@"; do
        if ! _ci_have "$_ci_tool"; then
            missing="$missing $_ci_tool"
        fi
    done
    if [ -n "$missing" ]; then
        _ci_fail "required tool(s) not on PATH:$missing"
        return 1
    fi
    return 0
}

_ci_app() {
    # The `app` label every object carries, from commonLabels in the overlay.
    if [ -n "${CI_ASSERT_APP:-}" ]; then
        printf '%s\n' "$CI_ASSERT_APP"
        return 0
    fi
    if [ -n "${SLUG:-}" ]; then
        printf '%s\n' "$SLUG"
        return 0
    fi
    local app=""
    if _ci_have yq && [ -f "$CI_ASSERT_OVERLAY/kustomization.yaml" ]; then
        app="$(yq '.commonLabels.app' "$CI_ASSERT_OVERLAY/kustomization.yaml" 2>/dev/null || true)"
    fi
    if [ "$app" = "null" ]; then
        app=""
    fi
    printf '%s\n' "$app"
}

_ci_claim() {
    # Name of the workspace PVC, read off whichever Deployment mounts it, so
    # the assertions keep working when namePrefix changes.
    if [ -n "${CI_ASSERT_CLAIM:-}" ]; then
        printf '%s\n' "$CI_ASSERT_CLAIM"
        return 0
    fi
    kubectl get deployment -n "$CI_ASSERT_NS" -l "app=$1" \
        -o jsonpath='{range .items[*]}{range .spec.template.spec.volumes[?(@.name=="workspaces")]}{.persistentVolumeClaim.claimName}{"\n"}{end}{end}' \
        2>/dev/null | sed '/^$/d' | head -n 1 || true
}

_ci_image() {
    # The app image is already present on every kind node (`kind load
    # image-archive`), so a helper pod built from it never pulls, and its
    # userland is the one the app actually runs on.
    if [ -n "${CI_ASSERT_IMAGE:-}" ]; then
        printf '%s\n' "$CI_ASSERT_IMAGE"
        return 0
    fi
    local image
    image="$(kubectl get deployment -n "$CI_ASSERT_NS" -l "app=$1,component=streamlit" \
        -o jsonpath='{.items[0].spec.template.spec.containers[0].image}' 2>/dev/null || true)"
    if [ -z "$image" ]; then
        image="ubuntu:22.04"
    fi
    printf '%s\n' "$image"
}

_ci_nodes_for_selector() {
    # Distinct nodes hosting Running pods that match a label selector, used by
    # assert_workers_spread_across_nodes. Running is filtered on server-side:
    # a Pending pod already carries every label and would otherwise be counted
    # as though it had landed somewhere.
    kubectl get pods -n "$CI_ASSERT_NS" -l "$1" \
        --field-selector=status.phase=Running \
        -o jsonpath='{range .items[*]}{.spec.nodeName}{"\n"}{end}' 2>/dev/null \
        | sed '/^$/d' | sort -u || true
}

_ci_ready_node_names() {
    # Every Ready node, one per line. The denominator for a spread check: a
    # skew computed only over the nodes that already hold a worker cannot see
    # the node that holds none, which is the interesting case.
    kubectl get nodes --no-headers 2>/dev/null | awk '$2 == "Ready" { print $1 }' || true
}

_ci_ready_pods() {
    # `<name><TAB><uid>` for every Running *and* Ready pod in a namespace.
    #
    # The uid, not the name, is what identifies a pod across a restart here:
    # the NFS server is a StatefulSet, so its replacement comes back as the
    # same `nfs-server-0`, and a name comparison would wait forever for a name
    # that is never going to change.
    #
    # `kubectl wait --all` cannot stand in for any of this either: it reports
    # success against zero pods, which is precisely the state a restart
    # assertion has to catch.
    kubectl get pods -n "$1" -o json 2>/dev/null | jq -r '
        .items[]
        | select(.status.phase == "Running")
        | select([.status.conditions[]? | select(.type == "Ready") | .status] | index("True"))
        | "\(.metadata.name)\t\(.metadata.uid)"' 2>/dev/null || true
}

_ci_kustomize_storage() {
    # Render the storage root. --enable-helm because that root inflates the
    # Ganesha chart; the flag is inert on a root with no helmCharts field, so it
    # costs nothing if the chart is ever vendored as plain manifests instead.
    kubectl kustomize --enable-helm "$CI_ASSERT_STORAGE_ROOT"
}

_ci_two_ready_nodes() {
    # The names of two distinct Ready nodes, one per line, or nothing at all.
    kubectl get nodes --no-headers 2>/dev/null | awk '$2 == "Ready" { print $1 }' | head -n 2 || true
}

_ci_pinning_files() {
    # The files assert_no_node_pinning_anywhere text-scans, one per line.
    #
    # git-tracked files PLUS untracked ones that are not gitignored. The
    # ignored half is the part that matters: `kubectl kustomize --enable-helm
    # k8s/storage/` makes kustomize vendor the Ganesha chart into
    # k8s/storage/charts/, and that chart carries its own `nodeSelector: {}`
    # default plus the template and README lines that go with it. Scanning the
    # raw working tree therefore turns this assertion permanently red on any
    # checkout where the storage root has been rendered once - which, in the
    # assert-invariants job, is guaranteed, because the NetworkPolicy step
    # renders it first. k8s/storage/charts/ is .gitignored, so
    # `--exclude-standard` prunes it by construction.
    #
    # Tracked-only would have been simpler and was wrong: a new manifest is
    # untracked until `git add`, so a nodeSelector added in a new file under
    # k8s/ would have reported PASS right up to the moment it was committed -
    # and k8s/overlays/ci/ and k8s/storage/*.yaml were themselves untracked
    # while this branch was being built, i.e. unscanned exactly when they were
    # being written. The one thing still skipped is deliberately-ignored
    # files, and the pass message says so.
    local p
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        for p in $CI_ASSERT_PINNING_PATHS; do
            git ls-files --cached --others --exclude-standard -- "$p" 2>/dev/null || true
        done
        return 0
    fi
    # No git (a tarball checkout): fall back to the filesystem, pruning any
    # vendored chart directory by name.
    for p in $CI_ASSERT_PINNING_PATHS; do
        [ -e "$p" ] || continue
        find "$p" -type d -name charts -prune -o -type f -print 2>/dev/null || true
    done
}

# --- throwaway pods --------------------------------------------------------

_ci_helper_pod_manifest() {
    # _ci_helper_pod_manifest <name> <node|""> <image> <claim>
    #
    # nodeName, not nodeSelector: bypassing the scheduler keeps a failure
    # unambiguously about the volume rather than about taints or affinity, and
    # this repo is in the business of removing nodeSelectors.
    local nodeline=""
    if [ -n "$2" ]; then
        nodeline="  nodeName: $2"
    fi
    cat <<MANIFEST
apiVersion: v1
kind: Pod
metadata:
  name: $1
  namespace: ${CI_ASSERT_NS}
  labels:
    ci-assertion: "true"
spec:
  restartPolicy: Never
  terminationGracePeriodSeconds: 0
${nodeline}
  containers:
    - name: main
      image: $3
      imagePullPolicy: IfNotPresent
      command: ["/bin/sh", "-c", "while true; do sleep 3600; done"]
      volumeMounts:
        - name: workspaces
          mountPath: ${CI_ASSERT_MOUNT}
  volumes:
    - name: workspaces
      persistentVolumeClaim:
        claimName: $4
MANIFEST
}

_ci_start_helper_pod() {
    # _ci_start_helper_pod <name> <node|""> <image> <claim>
    if ! _ci_helper_pod_manifest "$@" | kubectl apply -f - >/dev/null; then
        return 1
    fi
    if ! kubectl wait -n "$CI_ASSERT_NS" --for=condition=Ready "pod/$1" \
        --timeout="${CI_ASSERT_TIMEOUT}s" >/dev/null; then
        printf 'helper pod %s never became Ready:\n' "$1" >&2
        kubectl describe pod -n "$CI_ASSERT_NS" "$1" >&2 || true
        return 1
    fi
    return 0
}

_ci_delete_pods() {
    if [ "$#" -gt 0 ]; then
        kubectl delete pod -n "$CI_ASSERT_NS" "$@" \
            --ignore-not-found --wait=false >/dev/null 2>&1 || true
    fi
}

_ci_exec_script() {
    # _ci_exec_script <pod> [arg...] < script
    #
    # The script arrives on stdin, so nothing has to survive a round of shell
    # quoting. /bin/sh in the app image is dash: keep those scripts POSIX.
    local pod="$1"
    shift
    kubectl exec -i -n "$CI_ASSERT_NS" "$pod" -- /bin/sh -s "$@"
}

# --- assertions ------------------------------------------------------------

assert_two_pods_two_nodes() {
    # The acceptance criterion for the whole project: two pods that mount the
    # *same* workspace claim, Running on two different nodes. Filtering by the
    # claim matters - redis mounts nothing, so counting app pods alone would go
    # green while the shared workspace was still stuck on one node.
    _ci_require kubectl jq || return 1
    _ci_min_nodes="${1:-2}"
    _ci_rc=0

    _ci_a="$(_ci_app)"
    if [ -z "$_ci_a" ]; then
        _ci_fail "cannot determine the app label (set SLUG or CI_ASSERT_APP)"
        return 1
    fi
    _ci_c="$(_ci_claim "$_ci_a")"
    if [ -z "$_ci_c" ]; then
        _ci_fail "no Deployment in $CI_ASSERT_NS mounts a 'workspaces' volume - nothing to assert"
        return 1
    fi

    _ci_rows="$(kubectl get pods -n "$CI_ASSERT_NS" -l "app=$_ci_a" -o json 2>/dev/null \
        | jq -r --arg claim "$_ci_c" '
            .items[]
            | select(.status.phase == "Running")
            | select([.spec.volumes[]? | .persistentVolumeClaim.claimName? // empty] | index($claim))
            | "\(.metadata.name)\t\(.spec.nodeName)"' 2>/dev/null || true)"
    _ci_rows="$(printf '%s\n' "$_ci_rows" | sed '/^$/d')"
    printf 'pods mounting %s:\n%s\n' "$_ci_c" "${_ci_rows:-  <none>}"

    _ci_pods="$(printf '%s\n' "$_ci_rows" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [ "$_ci_pods" -lt 2 ]; then
        _ci_fail "only $_ci_pods Running pod(s) mount $_ci_c - two are needed to prove the volume is shared"
        _ci_rc=1
    fi

    _ci_nodes="$(printf '%s\n' "$_ci_rows" | awk -F'\t' 'NF > 1 && $2 != "" { print $2 }' | sort -u)"
    _ci_n="$(printf '%s\n' "$_ci_nodes" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [ "$_ci_n" -lt "$_ci_min_nodes" ]; then
        _ci_fail "pods mounting $_ci_c occupy $_ci_n node(s), expected at least $_ci_min_nodes: $(printf '%s' "$_ci_nodes" | tr '\n' ' ')"
        _ci_rc=1
    fi

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_pass "$_ci_pods pods mount $_ci_c across $_ci_n nodes: $(printf '%s' "$_ci_nodes" | tr '\n' ' ')"
    fi
    return "$_ci_rc"
}

assert_cross_node_write_visible() {
    # A pod on node A and a pod on node B, both holding the workspace volume at
    # the same time, each reading what the other wrote. Concurrency is the
    # point: a sequential write-then-read passes on an RWO volume that simply
    # detached and re-attached, which proves nothing.
    _ci_require kubectl || return 1
    _ci_rc=0

    _ci_a="$(_ci_app)"
    if [ -z "$_ci_a" ]; then
        _ci_fail "cannot determine the app label (set SLUG or CI_ASSERT_APP)"
        return 1
    fi
    _ci_c="$(_ci_claim "$_ci_a")"
    if [ -z "$_ci_c" ]; then
        _ci_fail "no Deployment in $CI_ASSERT_NS mounts a 'workspaces' volume - nothing to assert"
        return 1
    fi
    _ci_img="$(_ci_image "$_ci_a")"

    _ci_ready_nodes="$(kubectl get nodes --no-headers 2>/dev/null | awk '$2 == "Ready" { print $1 }' || true)"
    _ci_node_a="$(printf '%s\n' "$_ci_ready_nodes" | sed -n '1p')"
    _ci_node_b="$(printf '%s\n' "$_ci_ready_nodes" | sed -n '2p')"
    if [ -z "$_ci_node_b" ]; then
        _ci_fail "cluster has fewer than two Ready nodes - cross-node visibility cannot be asserted"
        return 1
    fi

    _ci_stamp="$(date +%s)"
    _ci_writer="ci-xnode-writer-$_ci_stamp"
    _ci_reader="ci-xnode-reader-$_ci_stamp"
    _ci_dir="$CI_ASSERT_MOUNT/.ci-cross-node-$_ci_stamp"
    _ci_token_w="written-on-$_ci_node_a"
    _ci_token_r="written-on-$_ci_node_b"

    if ! _ci_start_helper_pod "$_ci_writer" "$_ci_node_a" "$_ci_img" "$_ci_c"; then
        _ci_fail "writer pod could not start on $_ci_node_a"
        _ci_delete_pods "$_ci_writer"
        return 1
    fi
    # The reader has to come up while the writer still holds the mount.
    if ! _ci_start_helper_pod "$_ci_reader" "$_ci_node_b" "$_ci_img" "$_ci_c"; then
        _ci_fail "reader pod could not start on $_ci_node_b while the writer holds $_ci_c on $_ci_node_a"
        _ci_delete_pods "$_ci_writer" "$_ci_reader"
        return 1
    fi

    _ci_exec_script "$_ci_writer" "$_ci_dir" "$_ci_token_w" <<'WRITE' || _ci_rc=1
set -e
mkdir -p "$1"
printf '%s' "$2" > "$1/from-writer"
WRITE
    if [ "$_ci_rc" -ne 0 ]; then
        _ci_fail "writer pod on $_ci_node_a could not write to $_ci_dir"
    fi

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_got="$(_ci_exec_script "$_ci_reader" "$_ci_dir/from-writer" "$_ci_dir" "$_ci_token_r" <<'READ' || true
i=0
while [ "$i" -lt 30 ]; do
    if [ -f "$1" ]; then
        cat "$1"
        mkdir -p "$2"
        printf '%s' "$3" > "$2/from-reader"
        exit 0
    fi
    i=$((i + 1))
    sleep 2
done
exit 1
READ
)"
        if [ "$_ci_got" != "$_ci_token_w" ]; then
            _ci_fail "pod on $_ci_node_b read '$_ci_got' from $_ci_dir/from-writer, expected '$_ci_token_w'"
            _ci_rc=1
        fi
    fi

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_got="$(_ci_exec_script "$_ci_writer" "$_ci_dir/from-reader" <<'READBACK' || true
i=0
while [ "$i" -lt 30 ]; do
    if [ -f "$1" ]; then
        cat "$1"
        exit 0
    fi
    i=$((i + 1))
    sleep 2
done
exit 1
READBACK
)"
        if [ "$_ci_got" != "$_ci_token_r" ]; then
            _ci_fail "pod on $_ci_node_a read '$_ci_got' from $_ci_dir/from-reader, expected '$_ci_token_r'"
            _ci_rc=1
        fi
    fi

    _ci_exec_script "$_ci_writer" "$_ci_dir" <<'CLEAN' >/dev/null 2>&1 || true
rm -rf "$1"
CLEAN
    _ci_delete_pods "$_ci_writer" "$_ci_reader"

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_pass "$_ci_node_a and $_ci_node_b hold $_ci_c at the same time and each reads the other's writes"
    fi
    return "$_ci_rc"
}

assert_posix_contract() {
    # The filesystem guarantees src/ depends on, checked on the real mount:
    #   the mount is NFS    without this the whole assertion is vacuous. On the
    #                       pre-change cluster the helper lands on the node
    #                       holding the RWO volume and every check below passes
    #                       against overlayfs, proving nothing about the export
    #   absolute symlinks   common.py:179, :678 and fileupload.py:91 all call
    #                       symlink_to(x.resolve()), so demo seeding breaks if
    #                       readlink does not return the absolute target
    #   atomic rename       the seed-demos initContainer replaces `cp -rn` with
    #                       copy-to-temp plus `mv -T`
    #   flock ACROSS NODES  the property the locking design actually needs. A
    #                       single-pod flock test proves only local semantics:
    #                       an NFS mount with local_lock=all, or a client-side
    #                       emulation, passes it and still leaves locking a
    #                       no-op between the two workers. So the second holder
    #                       is a pod on the other node. If this half fails, the
    #                       lock backend moves from flock to Redis.
    _ci_require kubectl || return 1
    _ci_rc=0

    _ci_a="$(_ci_app)"
    if [ -z "$_ci_a" ]; then
        _ci_fail "cannot determine the app label (set SLUG or CI_ASSERT_APP)"
        return 1
    fi
    _ci_c="$(_ci_claim "$_ci_a")"
    if [ -z "$_ci_c" ]; then
        _ci_fail "no Deployment in $CI_ASSERT_NS mounts a 'workspaces' volume - nothing to assert"
        return 1
    fi
    _ci_img="$(_ci_image "$_ci_a")"

    _ci_ready_nodes="$(_ci_two_ready_nodes)"
    _ci_node_a="$(printf '%s\n' "$_ci_ready_nodes" | sed -n '1p')"
    _ci_node_b="$(printf '%s\n' "$_ci_ready_nodes" | sed -n '2p')"
    if [ -z "$_ci_node_b" ]; then
        _ci_fail "cluster has fewer than two Ready nodes - cross-client locking cannot be asserted"
        return 1
    fi

    _ci_stamp="$(date +%s)"
    _ci_holder="ci-posix-holder-$_ci_stamp"
    _ci_rival="ci-posix-rival-$_ci_stamp"
    _ci_dir="$CI_ASSERT_MOUNT/.ci-posix-contract-$_ci_stamp"

    if ! _ci_start_helper_pod "$_ci_holder" "$_ci_node_a" "$_ci_img" "$_ci_c"; then
        _ci_fail "helper pod could not start on $_ci_node_a with $_ci_c mounted at $CI_ASSERT_MOUNT"
        _ci_delete_pods "$_ci_holder"
        return 1
    fi
    if ! _ci_start_helper_pod "$_ci_rival" "$_ci_node_b" "$_ci_img" "$_ci_c"; then
        _ci_fail "helper pod could not start on $_ci_node_b while $_ci_holder holds $_ci_c on $_ci_node_a"
        _ci_delete_pods "$_ci_holder" "$_ci_rival"
        return 1
    fi

    # Pod A: prove the mount is NFS, then symlink, rename, and take the lock.
    # The holder runs detached with its output closed so `kubectl exec` returns
    # while it still holds the lock; it releases when pod B drops the release
    # file, so nothing here depends on a fixed sleep.
    _ci_exec_script "$_ci_holder" "$CI_ASSERT_MOUNT" "$_ci_dir" <<'POSIXA' || _ci_rc=1
set -e
m="$1"
d="$2"

fstype="$(awk -v mp="$m" '$2 == mp { t = $3 } END { print t }' /proc/mounts)"
opts="$(awk -v mp="$m" '$2 == mp { o = $4 } END { print o }' /proc/mounts)"
echo "mount: $m type=${fstype:-<none>} opts=${opts:-<none>}"
case "$fstype" in
    nfs|nfs4) ;;
    "")
        echo "mount: $m is not a mount point in this pod at all"
        exit 1
        ;;
    *)
        echo "mount: $m is '$fstype', not NFS - this assertion would be measuring the node's local filesystem"
        exit 1
        ;;
esac

rm -rf "$d"
mkdir -p "$d"

# 1. an absolute symlink survives readlink and can be read through
printf 'payload' > "$d/target"
ln -s "$d/target" "$d/link"
got="$(readlink "$d/link")"
if [ "$got" != "$d/target" ]; then
    echo "symlink: readlink returned '$got', expected '$d/target'"
    exit 1
fi
if [ "$(cat "$d/link")" != "payload" ]; then
    echo "symlink: reading through the link did not return the target's content"
    exit 1
fi

# 2. rename over an existing file, and rename of a directory (mv -T)
printf 'old' > "$d/dst"
printf 'new' > "$d/src"
mv "$d/src" "$d/dst"
if [ "$(cat "$d/dst")" != "new" ]; then
    echo "rename: destination was not replaced"
    exit 1
fi
if [ -e "$d/src" ]; then
    echo "rename: source still exists after mv"
    exit 1
fi
mkdir "$d/dsrc"
: > "$d/dsrc/f"
mv -T "$d/dsrc" "$d/ddst"
if [ ! -f "$d/ddst/f" ]; then
    echo "rename: directory rename lost its contents"
    exit 1
fi

# 3. take an exclusive lock and hold it until the other node says otherwise
: > "$d/lock"
(
    exec 9> "$d/lock"
    flock -x 9
    : > "$d/held"
    i=0
    while [ ! -f "$d/release" ] && [ "$i" -lt 180 ]; do
        i=$((i + 1))
        sleep 1
    done
) > /dev/null 2>&1 &

i=0
while [ ! -f "$d/held" ] && [ "$i" -lt 30 ]; do
    i=$((i + 1))
    sleep 1
done
if [ ! -f "$d/held" ]; then
    echo "flock: the holder on this node never acquired the lock"
    exit 1
fi
echo "absolute symlink and atomic rename behave; exclusive lock held on this node"
POSIXA

    if [ "$_ci_rc" -ne 0 ]; then
        _ci_fail "the POSIX contract does not hold on $_ci_c at $CI_ASSERT_MOUNT (pod on $_ci_node_a)"
        _ci_exec_script "$_ci_holder" "$_ci_dir" <<'CLEAN' > /dev/null 2>&1 || true
: > "$1/release"
rm -rf "$1"
CLEAN
        _ci_delete_pods "$_ci_holder" "$_ci_rival"
        return 1
    fi

    # Pod B, on the other node: the same mount has to be NFS here too, the
    # holder's lock has to exclude it, and once released it has to be takeable -
    # otherwise "cannot acquire" would prove nothing but a broken lock file.
    _ci_exec_script "$_ci_rival" "$CI_ASSERT_MOUNT" "$_ci_dir" <<'POSIXB' || _ci_rc=1
m="$1"
d="$2"
rc=0

fstype="$(awk -v mp="$m" '$2 == mp { t = $3 } END { print t }' /proc/mounts)"
echo "mount: $m type=${fstype:-<none>}"
case "$fstype" in
    nfs|nfs4) ;;
    *)
        echo "mount: $m is '${fstype:-<none>}', not NFS, on this node"
        exit 1
        ;;
esac

i=0
while [ ! -f "$d/held" ] && [ "$i" -lt 60 ]; do
    i=$((i + 1))
    sleep 1
done
if [ ! -f "$d/held" ]; then
    echo "flock: the other node's lock never became visible here"
    exit 1
fi

if flock -n -x "$d/lock" true; then
    echo "flock: this node took a lock the other node already holds, so locking is a no-op between clients"
    rc=1
fi

: > "$d/release"

# Generous, because the holder learns about the release file through the
# directory attribute cache: with default actimeo a negative lookup can be
# cached for up to acdirmax, 60s, before it revalidates and sees the file.
if ! flock -w 180 -x "$d/lock" true; then
    echo "flock: could not take the lock even after the other node released it"
    rc=1
fi

if [ "$(readlink "$d/link")" != "$d/target" ]; then
    echo "symlink: the absolute symlink does not resolve on this node"
    rc=1
fi

exit "$rc"
POSIXB

    _ci_exec_script "$_ci_holder" "$_ci_dir" <<'CLEAN' > /dev/null 2>&1 || true
: > "$1/release"
rm -rf "$1"
CLEAN
    _ci_delete_pods "$_ci_holder" "$_ci_rival"

    if [ "$_ci_rc" -ne 0 ]; then
        _ci_fail "the POSIX contract does not hold across nodes on $_ci_c at $CI_ASSERT_MOUNT"
        return 1
    fi
    _ci_pass "POSIX contract holds on $_ci_c: NFS mount, absolute symlink, atomic rename, and flock that excludes a holder on $_ci_node_a from $_ci_node_b"
    return 0
}

_ci_scan_rendered_for_pinning() {
    # Report every object in a RENDERED manifest stream that pins pods to a
    # node. Factored out of assert_no_node_pinning_anywhere because three
    # separate roots have to be scanned and they are not rendered the same way.
    #
    # PersistentVolume is skipped whole. `spec.nodeAffinity` on a PV is volume
    # TOPOLOGY - where the bytes are - not pod pinning, and it is mandatory for
    # a local volume. Nothing in the roots scanned today renders a PV, since the
    # provisioner creates them at runtime, but this function now also reads the
    # storage root, and a chart that ever emitted a static PV would otherwise
    # turn invariant 1 permanently red with no way to make it green except
    # weakening the check.
    #
    # $1 rendered file, $2 label printed against each hit.
    awk -v src="$2" '
        /^---[[:space:]]*$/ { kind = ""; name = ""; inmeta = 0; next }
        /^kind:/ && kind == "" { kind = $2; next }
        /^metadata:/ { inmeta = 1; next }
        /^[^[:space:]]/ { inmeta = 0 }
        inmeta && /^  name:/ && name == "" { name = $2 }
        kind == "PersistentVolume" { next }
        /^[[:space:]]*(nodeSelector|nodeName|nodeAffinity)[[:space:]]*:/ {
            key = $1
            sub(/:.*$/, "", key)
            print "  " src ": " kind "/" name " pins pods with " key " (rendered line " NR ")"
        }
    ' "$1" || true
}

assert_no_node_pinning_anywhere() {
    # Invariant 1 as a test: Kubernetes decides placement, the config must not.
    # Static, so it needs no cluster:
    #   1. no object rendered from the overlay pins a pod, by nodeSelector,
    #      nodeName or nodeAffinity
    #   2. no manifest in the tree mentions any of those, or the
    #      openms.de/memory-tier label (see _ci_pinning_files for what "in the
    #      tree" excludes, and why)
    # It also stops the pinning being reintroduced by a later fork rebase,
    # which is exactly how it would come back.
    # helm as well as kubectl, because the storage root is one of the three
    # roots scanned below and inflating it shells out to helm. A hard
    # requirement, deliberately not `if command -v helm`: a check that silently
    # does less work when a tool is missing is the shape this round exists to
    # remove.
    _ci_require kubectl helm || return 1
    _ci_rc=0

    # THREE rendered roots, not one. The Ganesha StatefulSet is the pod whose
    # placement mattered most in this work, and until now nothing inspected it:
    # the rendered half only ever rendered the prod overlay, and the text half
    # below asks git, which prunes the vendored chart under k8s/storage/charts/
    # through .gitignore. k8s/overlays/ci/ was equally unseen, and it is what
    # the kind jobs actually apply - a nodeSelector reintroduced there would pin
    # every pod CI ever schedules while prod stayed clean.
    _ci_hits=""
    for _ci_root in "$CI_ASSERT_OVERLAY" "$CI_ASSERT_CI_OVERLAY" "$CI_ASSERT_STORAGE_ROOT"; do
        [ -n "$_ci_root" ] || continue
        _ci_rendered="$(mktemp)"
        _ci_err="$(mktemp)"
        _ci_ok=0
        if [ "$_ci_root" = "$CI_ASSERT_STORAGE_ROOT" ]; then
            _ci_kustomize_storage > "$_ci_rendered" 2>"$_ci_err" && _ci_ok=1
        else
            kubectl kustomize "$_ci_root" > "$_ci_rendered" 2>"$_ci_err" && _ci_ok=1
        fi
        if [ "$_ci_ok" -ne 1 ]; then
            _ci_fail "kubectl kustomize $_ci_root failed"
            cat "$_ci_err" >&2 || true
            rm -f "$_ci_rendered" "$_ci_err"
            return 1
        fi
        rm -f "$_ci_err"
        if [ ! -s "$_ci_rendered" ]; then
            _ci_fail "kubectl kustomize $_ci_root rendered nothing - the check would pass vacuously"
            rm -f "$_ci_rendered"
            return 1
        fi
        _ci_found="$(_ci_scan_rendered_for_pinning "$_ci_rendered" "$_ci_root")"
        rm -f "$_ci_rendered"
        if [ -n "$_ci_found" ]; then
            if [ -z "$_ci_hits" ]; then
                _ci_hits="$_ci_found"
            else
                _ci_hits="$(printf '%s
%s' "$_ci_hits" "$_ci_found")"
            fi
        fi
    done
    if [ -n "$_ci_hits" ]; then
        _ci_fail "a rendered root still contains objects that pin pods to nodes"
        printf '%s
' "$_ci_hits" >&2
        _ci_rc=1
    fi

    # The text half runs over COMMENT-STRIPPED lines. `.github/kind-config.yaml`
    # explains its control-plane taint patch in prose that contains the word
    # nodeSelector, and a raw grep matches that comment for ever - including
    # after the labels it describes have been deleted, which would leave this
    # assertion red with no way left to make it green except weakening it.
    #
    # Keys are matched at the start of a mapping entry, or as a JSON-patch
    # `path:` segment - which is how k8s/components/memory-tier-*/ spell it -
    # so the Downward API reference `fieldPath: spec.nodeName` in the worker
    # Deployment, which pins nothing, is not mistaken for pinning.
    _ci_pin_re='(^|[[:space:]/])(nodeSelector|nodeName|nodeAffinity)([[:space:]]*:|[[:space:]]*$|/)|openms\.de/memory-tier'
    _ci_scanned=0
    _ci_hits=""
    for _ci_file in $(_ci_pinning_files); do
        [ -f "$_ci_file" ] || continue
        _ci_scanned=$((_ci_scanned + 1))
        _ci_tmp="$(mktemp)"
        sed 's/#.*$//' "$_ci_file" > "$_ci_tmp"
        _ci_found="$(grep -nE "$_ci_pin_re" "$_ci_tmp" | grep -v 'nodeSelectorTerms' || true)"
        rm -f "$_ci_tmp"
        if [ -n "$_ci_found" ]; then
            _ci_found="$(printf '%s' "$_ci_found" | sed "s|^|  $_ci_file:|")"
            if [ -z "$_ci_hits" ]; then
                _ci_hits="$_ci_found"
            else
                _ci_hits="$(printf '%s\n%s' "$_ci_hits" "$_ci_found")"
            fi
        fi
    done
    if [ "$_ci_scanned" -eq 0 ]; then
        _ci_fail "no files under '$CI_ASSERT_PINNING_PATHS' were scanned - the check would pass vacuously"
        _ci_rc=1
    elif [ -n "$_ci_hits" ]; then
        _ci_fail "manifests under '$CI_ASSERT_PINNING_PATHS' still pin pods to nodes (nodeSelector / nodeName / nodeAffinity / openms.de/memory-tier)"
        printf '%s\n' "$_ci_hits" >&2
        _ci_rc=1
    fi

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_pass "no node pinning anywhere: $CI_ASSERT_OVERLAY, $CI_ASSERT_CI_OVERLAY and $CI_ASSERT_STORAGE_ROOT all render none - the last of those is what covers the vendored Ganesha chart, which the text scan cannot see - and none of the $_ci_scanned files scanned under '$CI_ASSERT_PINNING_PATHS' references any (tracked + untracked; gitignored files are not scanned)"
    fi
    return "$_ci_rc"
}

_ci_worker_deployment() {
    # Name of the rq-worker Deployment, discovered by label so namePrefix stays
    # irrelevant.
    kubectl get deployment -n "$CI_ASSERT_NS" -l "app=$1,component=rq-worker" \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true
}

assert_workers_spread_across_nodes() {
    # Step 4's acceptance criterion for the workers themselves: every replica
    # Running, on more than one node, inside the skew the Deployment declares.
    #
    # This is the assertion that does NOT go green from deleting the
    # nodeSelector alone. Placement is only half of it:
    #
    #   1. every replica is Running. `.spec.replicas` is the denominator, so a
    #      worker that cannot be scheduled - the exact state an oversized
    #      request produces - fails here rather than being quietly left out of
    #      the node count. assert_two_pods_two_nodes cannot stand in: it starts
    #      its own helper pods with an explicit nodeName, which proves the
    #      volume is reachable from two nodes and says nothing about where the
    #      scheduler put the workers.
    #   2. they occupy at least two nodes.
    #   3. the observed per-node counts, over ALL Ready nodes rather than only
    #      those already holding a worker, are within the constraint's own
    #      maxSkew.
    #   4. the constraint's labelSelector actually matches the worker pods'
    #      labels. kustomize copies the overlay's `commonLabels.app` into
    #      topologySpreadConstraints/labelSelector/matchLabels; if that ever
    #      stops happening the constraint starts counting every rq-worker in
    #      the namespace, including other forks', and nothing about the
    #      placement in a single-fork test cluster would look different.
    _ci_require kubectl jq || return 1
    _ci_rc=0

    _ci_a="$(_ci_app)"
    if [ -z "$_ci_a" ]; then
        _ci_fail "cannot determine the app label (set SLUG or CI_ASSERT_APP)"
        return 1
    fi
    _ci_sel="${1:-app=$_ci_a,component=rq-worker}"

    _ci_ready_nodes="$(_ci_ready_node_names)"
    _ci_node_count="$(printf '%s\n' "$_ci_ready_nodes" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [ "$_ci_node_count" -lt 2 ]; then
        _ci_fail "cluster has $_ci_node_count Ready node(s) - spreading cannot be observed on fewer than two, and every constraint would pass vacuously"
        return 1
    fi

    _ci_deploy="$(_ci_worker_deployment "$_ci_a")"
    if [ -z "$_ci_deploy" ]; then
        _ci_fail "no Deployment matching app=$_ci_a,component=rq-worker in $CI_ASSERT_NS - there are no workers to spread"
        return 1
    fi
    _ci_want="$(kubectl get deployment -n "$CI_ASSERT_NS" "$_ci_deploy" \
        -o jsonpath='{.spec.replicas}' 2>/dev/null || true)"
    case "$_ci_want" in
        ''|*[!0-9]*)
            _ci_fail "could not read .spec.replicas from deployment/$_ci_deploy"
            return 1
            ;;
    esac
    if [ "$_ci_want" -lt 2 ]; then
        _ci_fail "deployment/$_ci_deploy declares replicas: $_ci_want - one worker is trivially 'spread' over one node, so this assertion would pass without observing anything"
        return 1
    fi

    # `<name><TAB><phase><TAB><node>` per worker pod, Pending ones INCLUDED:
    # they are the failure this assertion exists to catch, so they have to be
    # counted rather than filtered out server-side the way the other
    # assertions do it.
    _ci_rows="$(kubectl get pods -n "$CI_ASSERT_NS" -l "$_ci_sel" -o json 2>/dev/null \
        | jq -r '.items[] | "\(.metadata.name)\t\(.status.phase)\t\(.spec.nodeName // "<unscheduled>")"' 2>/dev/null || true)"
    _ci_rows="$(printf '%s\n' "$_ci_rows" | sed '/^$/d')"
    if [ -z "$_ci_rows" ]; then
        _ci_fail "no pods match $_ci_sel in $CI_ASSERT_NS - spreading cannot be asserted"
        return 1
    fi
    printf 'worker pods (name / phase / node):\n%s\n' "$_ci_rows"

    # One node name per RUNNING pod, duplicates kept - two workers on one node
    # is a skew of 2 over a two-node cluster, and a `sort -u` here would report
    # it as a tidy one-each. `$_ci_placements` is the multiset, `$_ci_running`
    # the distinct nodes. Both come out of the single snapshot above rather
    # than a second query, so they cannot disagree with each other or with the
    # listing just printed.
    _ci_placements="$(printf '%s\n' "$_ci_rows" | awk -F'\t' '$2 == "Running" && $3 != "<unscheduled>" { print $3 }')"
    _ci_running="$(printf '%s\n' "$_ci_placements" | sed '/^$/d' | sort -u)"
    _ci_running_count="$(printf '%s\n' "$_ci_rows" | awk -F'\t' '$2 == "Running"' | sed '/^$/d' | wc -l | tr -d ' ')"
    if [ "$_ci_running_count" -lt "$_ci_want" ]; then
        _ci_fail "deployment/$_ci_deploy wants $_ci_want replicas but only $_ci_running_count are Running - a replica the scheduler cannot place is the failure mode an oversized request produces"
        kubectl get pods -n "$CI_ASSERT_NS" -l "$_ci_sel" -o wide >&2 || true
        kubectl describe pods -n "$CI_ASSERT_NS" -l "$_ci_sel" 2>/dev/null \
            | grep -A5 '^Events:' >&2 || true
        _ci_rc=1
    fi

    _ci_n="$(printf '%s\n' "$_ci_running" | sed '/^$/d' | wc -l | tr -d ' ')"
    if [ "$_ci_n" -lt 2 ]; then
        _ci_fail "$_ci_running_count Running worker(s) occupy $_ci_n node(s) across a $_ci_node_count-node cluster: $(printf '%s' "$_ci_running" | tr '\n' ' ')"
        _ci_rc=1
    fi

    # maxSkew as the Deployment declares it, so retuning the constraint retunes
    # the assertion with it rather than leaving a hardcoded 1 behind.
    _ci_skew_max="$(kubectl get deployment -n "$CI_ASSERT_NS" "$_ci_deploy" -o json 2>/dev/null \
        | jq -r '[.spec.template.spec.topologySpreadConstraints[]?
                  | select(.topologyKey == "kubernetes.io/hostname")
                  | .maxSkew] | first // empty' 2>/dev/null || true)"
    if [ -z "$_ci_skew_max" ]; then
        _ci_fail "deployment/$_ci_deploy declares no topologySpreadConstraint over kubernetes.io/hostname - two nodes here would be the scheduler's default scoring, which it is free to stop doing"
        _ci_rc=1
    else
        # Counts over every Ready node, zeros included: a node holding no
        # worker is a domain the constraint was measured over and is the whole
        # point of the check.
        _ci_skew="$( { printf '%s\n' "$_ci_ready_nodes" | sed '/^$/d' | sed 's/$/\t0/'
                       printf '%s\n' "$_ci_placements" | sed '/^$/d' | sed 's/$/\t1/'; } \
            | awk -F'\t' '{ c[$1] += $2 }
                          END { for (n in c) { if (!seen++ || c[n] > hi) hi = c[n];
                                               if (lo == "" || c[n] < lo) lo = c[n] }
                                print hi - lo }')"
        if [ -n "$_ci_skew" ] && [ "$_ci_skew" -gt "$_ci_skew_max" ]; then
            _ci_fail "worker pods are skewed $_ci_skew across the $_ci_node_count Ready nodes, above the declared maxSkew of $_ci_skew_max"
            _ci_rc=1
        fi
    fi

    # The labelSelector has to select the workers themselves.
    _ci_bad="$(kubectl get deployment -n "$CI_ASSERT_NS" "$_ci_deploy" -o json 2>/dev/null \
        | jq -r --arg app "$_ci_a" '.spec.template as $t
                 | [.spec.template.spec.topologySpreadConstraints[]?
                    | select(.topologyKey == "kubernetes.io/hostname")
                    | (.labelSelector.matchLabels // {}) as $m
                    | if ($m | length) == 0 then "labelSelector.matchLabels is empty, so the constraint counts every pod in the namespace"
                      elif [$m | to_entries[] | select($t.metadata.labels[.key] != .value)] | length > 0
                      then "labelSelector.matchLabels \($m) does not match the pod template labels \($t.metadata.labels)"
                      # NOTE: no apostrophes in this jq program - it is inside a
                      # single-quoted shell string, where one would end it.
                      # to_entries only walks keys that are PRESENT, so a bare
                      # {component: rq-worker} selector matched the pod template
                      # and passed, while counting every other fork rq-worker in
                      # this shared namespace against our skew. That is the
                      # regression k8s/base/rq-worker-deployment.yaml calls
                      # load-bearing in the comment above its own constraint,
                      # and the check above cannot see it, because the app label
                      # is injected by commonLabels at overlay time rather than
                      # declared in the base.
                      elif ($m.app // "") != $app
                      then "labelSelector.matchLabels \($m) carries no app=\($app) key, so the constraint counts every rq-worker in the namespace rather than only these workers"
                      else empty end] | .[]' 2>/dev/null || true)"
    if [ -n "$_ci_bad" ]; then
        _ci_fail "deployment/$_ci_deploy has a spread constraint that does not select its own workers: $_ci_bad"
        _ci_rc=1
    fi

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_pass "$_ci_running_count/$_ci_want worker replicas Running on $_ci_n of $_ci_node_count nodes within maxSkew $_ci_skew_max: $(printf '%s' "$_ci_running" | tr '\n' ' ')"
    fi
    return "$_ci_rc"
}

assert_worker_qos_guaranteed() {
    # Guaranteed QoS gives the worker oom_score_adj -997 instead of burstable's
    # ~937, which is near the top of the node's kill list. Catches a
    # requests != limits regression, which otherwise only shows up as an
    # OOMKill under load.
    #
    # Running pods only, and that filter is load-bearing rather than tidiness:
    # .status.qosClass is computed at ADMISSION and is populated on a Pending
    # pod, so a selector without it reports "every worker is Guaranteed" for
    # two replicas that were never scheduled - which is exactly the state an
    # oversized request produces, and exactly the state this suite must not
    # call a pass. The count of Running replicas against .spec.replicas belongs
    # to assert_workers_spread_across_nodes; here it is enough that at least
    # one worker is actually running to have a QoS class worth reading.
    _ci_require kubectl || return 1
    _ci_rc=0

    _ci_a="$(_ci_app)"
    if [ -z "$_ci_a" ]; then
        _ci_fail "cannot determine the app label (set SLUG or CI_ASSERT_APP)"
        return 1
    fi
    _ci_sel="${1:-app=$_ci_a,component=rq-worker}"

    _ci_rows="$(kubectl get pods -n "$CI_ASSERT_NS" -l "$_ci_sel" \
        --field-selector=status.phase=Running \
        -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.qosClass}{"\n"}{end}' 2>/dev/null || true)"
    _ci_rows="$(printf '%s\n' "$_ci_rows" | sed '/^$/d')"
    if [ -z "$_ci_rows" ]; then
        _ci_fail "no Running pods match $_ci_sel in $CI_ASSERT_NS - QoS cannot be asserted, and reading it off a Pending pod would report a pass for a worker that never started"
        kubectl get pods -n "$CI_ASSERT_NS" -l "$_ci_sel" -o wide >&2 || true
        return 1
    fi
    printf '%s\n' "$_ci_rows"

    _ci_bad="$(printf '%s\n' "$_ci_rows" \
        | awk -F'\t' '$2 != "Guaranteed" { printf "%s=%s ", $1, ($2 == "" ? "<unset>" : $2) }')"
    if [ -n "$_ci_bad" ]; then
        _ci_fail "worker pods are not Guaranteed QoS (requests must equal limits): $_ci_bad"
        kubectl get pods -n "$CI_ASSERT_NS" -l "$_ci_sel" \
            -o jsonpath='{range .items[*]}{.metadata.name}{" requests="}{.spec.containers[*].resources.requests}{" limits="}{.spec.containers[*].resources.limits}{"\n"}{end}' >&2 || true
        _ci_rc=1
    fi

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_pass "every Running pod matching $_ci_sel is Guaranteed QoS"
    fi
    return "$_ci_rc"
}

assert_fsids_pinned() {
    # The static half of invariant 2, split out so it can also run in the cheap
    # manifest-only job on every push rather than only after a full kind deploy.
    #
    # Ganesha derives every NFS file handle it hands to every client from the
    # backing device's major/minor by default, and a Cinder /dev/vdX minor is
    # not stable across re-attach: left alone, every client ESTALEs the first
    # time this pod moves - typically weeks later, with nothing pointing back at
    # the change that caused it.
    #
    # Read off the RENDERED root rather than the values file, so it holds
    # whichever key the chart happens to expose, and matched exhaustively rather
    # than on the first hit - `head -n 1` would accept a `false` followed by a
    # later `true`. kustomize strips YAML comments, so no amount of prose about
    # fsids in the values file can satisfy this.
    #
    # helm is required explicitly: `kubectl kustomize --enable-helm` shells out
    # to it, and "required tool(s) not on PATH: helm" is a better answer than a
    # kustomize error about a chart it could not inflate.
    _ci_require kubectl helm || return 1
    _ci_rc=0

    _ci_rendered="$(mktemp)"
    _ci_err="$(mktemp)"
    if ! _ci_kustomize_storage > "$_ci_rendered" 2>"$_ci_err"; then
        _ci_fail "kubectl kustomize --enable-helm $CI_ASSERT_STORAGE_ROOT failed"
        cat "$_ci_err" >&2 || true
        rm -f "$_ci_rendered" "$_ci_err"
        return 1
    fi
    rm -f "$_ci_err"
    if [ ! -s "$_ci_rendered" ]; then
        _ci_fail "$CI_ASSERT_STORAGE_ROOT rendered nothing - the fsid check would pass vacuously"
        rm -f "$_ci_rendered"
        return 1
    fi

    _ci_fsid="$(grep -oiE 'device-based-fsids[^A-Za-z]*(true|false)' "$_ci_rendered" || true)"
    rm -f "$_ci_rendered"
    if [ -z "$_ci_fsid" ]; then
        _ci_fail "$CI_ASSERT_STORAGE_ROOT never sets device-based-fsids; Ganesha defaults it to true and derives file handles from a device minor number that a Cinder re-attach renumbers"
        return 1
    fi
    _ci_bad="$(printf '%s\n' "$_ci_fsid" | grep -i 'true' || true)"
    if [ -n "$_ci_bad" ]; then
        _ci_fail "$CI_ASSERT_STORAGE_ROOT renders device-based fsids ON, which makes every client ESTALE the first time the volume is re-attached"
        printf '%s\n' "$_ci_fsid" >&2
        _ci_rc=1
    fi

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_pass "$CI_ASSERT_STORAGE_ROOT pins device-based fsids off: $(printf '%s' "$_ci_fsid" | tr '\n' ' ')"
    fi
    return "$_ci_rc"
}

assert_storage_identity_values() {
    # The other three quarters of invariant 2. `device-based-fsids` above is
    # only one of the four things that make the NFS server come back serving
    # the same bytes under the same identity; the remaining three were asserted
    # nowhere, so a values edit dropping any of them rendered clean,
    # kubeconformed clean, deployed clean, and passed every runtime assertion
    # in this file. What it costs is not a red build - it is deleted data on a
    # PVC delete, or a second Ganesha Pending forever on an RWO claim.
    #
    # Read off the RENDERED root for the same reason as assert_fsids_pinned:
    # it holds whichever key the chart exposes, and kustomize strips the
    # comments that would otherwise look like compliance.
    _ci_require kubectl helm yq || return 1
    _ci_rc=0

    _ci_rendered="$(mktemp)"
    _ci_err="$(mktemp)"
    if ! _ci_kustomize_storage > "$_ci_rendered" 2>"$_ci_err"; then
        _ci_fail "kubectl kustomize --enable-helm $CI_ASSERT_STORAGE_ROOT failed"
        cat "$_ci_err" >&2 || true
        rm -f "$_ci_rendered" "$_ci_err"
        return 1
    fi
    rm -f "$_ci_err"
    if [ ! -s "$_ci_rendered" ]; then
        _ci_fail "$CI_ASSERT_STORAGE_ROOT rendered nothing - these checks would pass vacuously"
        rm -f "$_ci_rendered"
        return 1
    fi

    # 1. reclaimPolicy: Retain on the class this root publishes. The cluster
    #    default is Delete, which destroys the volume with the claim.
    _ci_reclaim="$(yq 'select(.kind == "StorageClass") | .reclaimPolicy' "$_ci_rendered" \
        | grep -v '^---$' | grep -v '^$' || true)"
    if [ "$_ci_reclaim" != "Retain" ]; then
        _ci_fail "the StorageClass reclaimPolicy is '${_ci_reclaim:-unset}', not Retain: deleting a PV or PVC would destroy the workspace data rather than orphan it"
        _ci_rc=1
    fi

    # The workload selects below are scoped to the server's own app label, not
    # to "any StatefulSet or Deployment". The chart is free to grow a second
    # workload - a metrics exporter, a sidecar controller - and an unscoped
    # select would then yield two lines, turning both checks into a spurious
    # failure whose message names no workload at all.
    #
    # Derived from the values file rather than hardcoded: replacing one
    # hand-synced literal with another is not an improvement. `nameOverride`
    # is what the chart renders into `app:`; `fullnameOverride` names the
    # objects and is a different string on purpose.
    _ci_srv="$(yq '.nameOverride' "$CI_ASSERT_STORAGE_ROOT/ganesha-values.yaml" 2>/dev/null \
        | grep -v '^null$' || true)"
    if [ -z "$_ci_srv" ]; then
        _ci_fail "could not read nameOverride from $CI_ASSERT_STORAGE_ROOT/ganesha-values.yaml; cannot identify the NFS server workload"
        rm -f "$_ci_rendered"
        return 1
    fi

    # 2. A fixed, pre-existing backing claim, whose name matches a PVC this
    #    root actually renders. Dynamic provisioning for the BACKING volume
    #    means a re-provisioned claim is a different volume and the server
    #    comes back empty; a claim name that matches nothing means the pod
    #    sits Pending forever. `persistence.existingClaim` in the values and
    #    `metadata.name` in nfs-backing-pvc.yaml are hand-synced, and until
    #    now nothing checked that they still agreed.
    _ci_claim="$(yq "select((.kind == \"StatefulSet\" or .kind == \"Deployment\")
                            and .metadata.labels.app == \"$_ci_srv\")
                     | .spec.template.spec.volumes[]?
                     | select(.persistentVolumeClaim)
                     | .persistentVolumeClaim.claimName" "$_ci_rendered" \
        | grep -v '^---$' | grep -v '^$' | grep -v '^null$' || true)"
    if [ -z "$_ci_claim" ]; then
        _ci_fail "the NFS server mounts no persistentVolumeClaim, so persistence.existingClaim was dropped and its backing store is not a fixed volume"
        _ci_rc=1
    else
        # `else`, not a second unguarded `if`: on a dropped claim both branches
        # would fire and the second message would misdirect.
        _ci_pvc="$(yq 'select(.kind == "PersistentVolumeClaim") | .metadata.name' "$_ci_rendered" \
            | grep -v '^---$' | grep -v '^$' | grep -v '^null$' || true)"
        if [ "$_ci_claim" != "$_ci_pvc" ]; then
            _ci_fail "the NFS server mounts claim '$_ci_claim' but $CI_ASSERT_STORAGE_ROOT renders PVC '${_ci_pvc:-none}': the pod would sit Pending on a claim that does not exist"
            _ci_rc=1
        fi
    fi

    # 3. Exactly one replica. Two Ganesha pods on one RWO claim is worse than
    #    the RollingUpdate deadlock `strategy: Recreate` exists to avoid.
    _ci_replicas="$(yq "select((.kind == \"StatefulSet\" or .kind == \"Deployment\")
                               and .metadata.labels.app == \"$_ci_srv\")
                        | .spec.replicas" "$_ci_rendered" \
        | grep -v '^---$' | grep -v '^$' | grep -v '^null$' || true)"
    if [ "$_ci_replicas" != "1" ]; then
        _ci_fail "the NFS server renders replicas='${_ci_replicas:-unset}', not 1: a second pod cannot mount the RWO backing claim and would sit Pending forever"
        _ci_rc=1
    fi

    rm -f "$_ci_rendered"
    if [ "$_ci_rc" -eq 0 ]; then
        _ci_pass "storage identity pinned: reclaimPolicy=Retain, backing claim=$_ci_claim, replicas=$_ci_replicas"
    fi
    return "$_ci_rc"
}

assert_survives_nfs_restart() {
    # The single most valuable assertion in this file: delete the Ganesha pod
    # while a workflow is running, and assert the workflow COMPLETES.
    #
    # A Ganesha restart is routine - upgrades, evictions, node drains, OOM - and
    # this is the exact case a `soft` mount would have corrupted, by returning a
    # short read or an EIO into the middle of a featureXML instead of blocking.
    # Nothing else here covers it: assert_stable_identity_across_restart runs a
    # handful of file operations after the server is back, so it cannot observe
    # a job that died during the outage or output that went missing while the
    # ~90s NFSv4.1 grace period was refusing state-mutating operations.
    #
    # The stand-in workflow is deliberately shaped like the real one rather than
    # being a single `cp`:
    #   - one long-lived file descriptor, opened BEFORE the restart and written
    #     through afterwards, the way a TOPP tool holds its output file
    #   - one open-append-close per line, the way src/workflow/Logger.py writes
    #   - a `WORKFLOW FINISHED` marker as the last line, which is the same
    #     signal src/workflow/_log_status.py classifies a run by
    # Its exit status is recorded in /tmp, NOT on the mount, so a wedged export
    # cannot hide the result it is being judged on.
    _ci_require kubectl jq || return 1
    _ci_rc=0
    _ci_run_rc=0

    _ci_a="$(_ci_app)"
    if [ -z "$_ci_a" ]; then
        _ci_fail "cannot determine the app label (set SLUG or CI_ASSERT_APP)"
        return 1
    fi
    _ci_c="$(_ci_claim "$_ci_a")"
    if [ -z "$_ci_c" ]; then
        _ci_fail "no Deployment in $CI_ASSERT_NS mounts a 'workspaces' volume - nothing to assert"
        return 1
    fi
    _ci_img="$(_ci_image "$_ci_a")"
    _ci_records="$CI_ASSERT_WORKFLOW_RECORDS"

    _ci_row="$(_ci_ready_pods "$CI_ASSERT_STORAGE_NS" | head -n 1)"
    _ci_before="$(printf '%s' "$_ci_row" | cut -f1)"
    _ci_before_uid="$(printf '%s' "$_ci_row" | cut -f2)"
    if [ -z "$_ci_before" ] || [ -z "$_ci_before_uid" ]; then
        _ci_fail "no Ready pod in $CI_ASSERT_STORAGE_NS - the NFS server is not running, so restarting it proves nothing"
        kubectl get pods -n "$CI_ASSERT_STORAGE_NS" -o wide >&2 || true
        return 1
    fi

    _ci_stamp="$(date +%s)"
    _ci_pod="ci-workflow-$_ci_stamp"
    _ci_dir="$CI_ASSERT_MOUNT/.ci-survives-restart-$_ci_stamp"

    # Unpinned: the scheduler places it, and the mount it ends up holding is the
    # one that has to survive.
    if ! _ci_start_helper_pod "$_ci_pod" "" "$_ci_img" "$_ci_c"; then
        _ci_fail "client pod could not start with $_ci_c mounted at $CI_ASSERT_MOUNT"
        _ci_delete_pods "$_ci_pod"
        return 1
    fi

    _ci_exec_script "$_ci_pod" "$_ci_dir" "$_ci_records" <<'START' || _ci_run_rc=1
set -e
d="$1"
n="$2"
rm -rf "$d"
mkdir -p "$d"
rm -f /tmp/ci-workflow-status /tmp/ci-workflow-stderr
: > /tmp/ci-workflow-stderr
(
    set -e
    trap 'rc=$?; echo "$rc" > /tmp/ci-workflow-status' EXIT
    # Opened once, up front. Every write after the restart therefore has to be
    # served against a file handle the previous server handed out.
    exec 8> "$d/stream.log"
    i=1
    while [ "$i" -le "$n" ]; do
        echo "record $i" >&8
        echo "record $i" >> "$d/perline.log"
        i=$((i + 1))
        sleep 1
    done
    echo "WORKFLOW FINISHED" >&8
    echo "WORKFLOW FINISHED" >> "$d/perline.log"
) > /dev/null 2>> /tmp/ci-workflow-stderr &
echo "workflow started, writing $n records to $d"
START
    if [ "$_ci_run_rc" -ne 0 ]; then
        _ci_fail "the stand-in workflow could not be started in $_ci_dir"
        _ci_delete_pods "$_ci_pod"
        return 1
    fi

    # Let it get properly under way before the server is pulled out from under
    # it. A restart that lands before the first write would test the mount, not
    # a workflow in progress.
    _ci_got="$(_ci_exec_script "$_ci_pod" "$_ci_dir" 5 <<'PROGRESS' || true
d="$1"
want="$2"
i=0
while [ "$i" -lt 60 ]; do
    if [ -f "$d/perline.log" ] && [ "$(wc -l < "$d/perline.log")" -ge "$want" ]; then
        wc -l < "$d/perline.log"
        exit 0
    fi
    i=$((i + 1))
    sleep 1
done
exit 1
PROGRESS
)"
    if [ -z "$_ci_got" ]; then
        _ci_fail "the stand-in workflow wrote nothing in 60s, so there is no run in progress to interrupt"
        _ci_delete_pods "$_ci_pod"
        return 1
    fi
    printf 'workflow is %s records in; deleting NFS server pod %s in %s\n' "$(printf '%s' "$_ci_got" | tr -d ' ')" "$_ci_before" "$CI_ASSERT_STORAGE_NS"

    if ! kubectl delete pod -n "$CI_ASSERT_STORAGE_NS" "$_ci_before" --wait=true --timeout="${CI_ASSERT_RESTART_TIMEOUT}s" > /dev/null; then
        _ci_fail "could not delete the NFS server pod $_ci_before"
        _ci_delete_pods "$_ci_pod"
        return 1
    fi

    # A pod with a NEW uid has to come back Ready. Matching on the name would
    # never fire - a StatefulSet reuses it.
    _ci_deadline=$(( $(date +%s) + CI_ASSERT_RESTART_TIMEOUT ))
    _ci_after_uid=""
    while [ "$(date +%s)" -lt "$_ci_deadline" ]; do
        _ci_row="$(_ci_ready_pods "$CI_ASSERT_STORAGE_NS" | awk -F'\t' -v old="$_ci_before_uid" '$2 != "" && $2 != old { print; exit }')"
        _ci_after="$(printf '%s' "$_ci_row" | cut -f1)"
        _ci_after_uid="$(printf '%s' "$_ci_row" | cut -f2)"
        if [ -n "$_ci_after_uid" ]; then
            break
        fi
        sleep 5
    done
    if [ -z "$_ci_after_uid" ]; then
        _ci_fail "no replacement NFS server pod became Ready within ${CI_ASSERT_RESTART_TIMEOUT}s of deleting $_ci_before"
        kubectl get pods -n "$CI_ASSERT_STORAGE_NS" -o wide >&2 || true
        _ci_delete_pods "$_ci_pod"
        return 1
    fi
    printf 'NFS server came back as %s (uid %s -> %s)\n' "$_ci_after" "$_ci_before_uid" "$_ci_after_uid"

    # Now wait it out. The workflow has to survive the outage AND the grace
    # period, during which a `hard` mount simply blocks and retries. The status
    # file lives on the pod's own /tmp, so polling it never touches the export.
    _ci_deadline=$(( $(date +%s) + CI_ASSERT_WORKFLOW_TIMEOUT ))
    _ci_status=""
    while [ "$(date +%s)" -lt "$_ci_deadline" ]; do
        _ci_status="$(_ci_exec_script "$_ci_pod" <<'STATUS' || true
if [ -f /tmp/ci-workflow-status ]; then
    cat /tmp/ci-workflow-status
fi
STATUS
)"
        _ci_status="$(printf '%s' "$_ci_status" | tr -d '[:space:]')"
        if [ -n "$_ci_status" ]; then
            break
        fi
        sleep 5
    done

    if [ -z "$_ci_status" ]; then
        _ci_fail "the workflow had not finished ${CI_ASSERT_WORKFLOW_TIMEOUT}s after the restart - it is still blocked, or it died without recording a status"
        _ci_rc=1
    elif [ "$_ci_status" != "0" ]; then
        _ci_fail "the workflow exited $_ci_status across the restart of $_ci_before; a hard mount is supposed to block and resume, not fail"
        _ci_rc=1
    fi

    # Completeness, not just exit status: a workflow that "finished" having
    # silently dropped half its output is the failure this is guarding against.
    _ci_exec_script "$_ci_pod" "$_ci_dir" "$_ci_records" <<'VERIFY' || _ci_rc=1
d="$1"
n="$2"
rc=0

check_log() {
    if [ ! -f "$1" ]; then
        echo "$1 does not exist - the workflow never created it"
        return 1
    fi
    awk -v n="$2" -v f="$1" '
        NR <= n {
            if ($0 != "record " NR) {
                printf "%s line %d is [%s], expected [record %d]\n", f, NR, $0, NR
                bad = 1
                exit 1
            }
            next
        }
        NR == n + 1 {
            if ($0 != "WORKFLOW FINISHED") {
                printf "%s line %d is [%s], expected the WORKFLOW FINISHED marker\n", f, NR, $0
                bad = 1
                exit 1
            }
            next
        }
        {
            printf "%s has an unexpected trailing line %d: [%s]\n", f, NR, $0
            bad = 1
            exit 1
        }
        END {
            if (bad) {
                exit 1
            }
            if (NR < n + 1) {
                printf "%s holds %d lines, expected %d records plus the marker\n", f, NR, n
                exit 1
            }
        }
    ' "$1"
}

# The long-lived descriptor and the open-append-close writer have to agree.
check_log "$d/stream.log" "$n" || rc=1
check_log "$d/perline.log" "$n" || rc=1

if [ -s /tmp/ci-workflow-stderr ]; then
    echo "the workflow wrote to stderr:"
    cat /tmp/ci-workflow-stderr
    rc=1
fi
exit "$rc"
VERIFY

    _ci_exec_script "$_ci_pod" "$_ci_dir" <<'CLEAN' > /dev/null 2>&1 || true
rm -rf "$1"
CLEAN
    _ci_delete_pods "$_ci_pod"

    if [ "$_ci_rc" -ne 0 ]; then
        _ci_fail "a workflow running across the restart of $_ci_before did not complete intact"
        return 1
    fi
    _ci_pass "a workflow writing $_ci_records records through the mount survived the NFS server restart ($_ci_before, uid $_ci_before_uid -> $_ci_after_uid) and finished complete and in order"
    return 0
}

assert_stable_identity_across_restart() {
    # Invariant 2: the filesystem pod comes back pointing at the same bytes,
    # under the same identity, on every restart. Two halves, both required.
    #
    #   static   assert_fsids_pinned, above: the rendered storage root has to
    #            pin device-based-fsids off.
    #
    #   runtime  delete the NFS server pod underneath a live client, then make
    #            that client *create* a file through the mount it opened before
    #            the restart. A create cannot be served out of the page cache
    #            the way a re-read can, so it has to present a pre-restart file
    #            handle to the new server and ESTALEs if identity moved.
    #
    # The static half is what keeps this from passing vacuously: kind's backing
    # device is not renumbered when the pod restarts, so the runtime half alone
    # would go green with device-based fsids left switched on.
    _ci_require kubectl jq || return 1
    _ci_rc=0
    _ci_run_rc=0

    if ! assert_fsids_pinned; then
        _ci_rc=1
    fi

    _ci_a="$(_ci_app)"
    if [ -z "$_ci_a" ]; then
        _ci_fail "cannot determine the app label (set SLUG or CI_ASSERT_APP)"
        return 1
    fi
    _ci_c="$(_ci_claim "$_ci_a")"
    if [ -z "$_ci_c" ]; then
        _ci_fail "no Deployment in $CI_ASSERT_NS mounts a 'workspaces' volume - nothing to assert"
        return 1
    fi
    _ci_img="$(_ci_image "$_ci_a")"

    _ci_row="$(_ci_ready_pods "$CI_ASSERT_STORAGE_NS" | head -n 1)"
    _ci_before="$(printf '%s' "$_ci_row" | cut -f1)"
    _ci_before_uid="$(printf '%s' "$_ci_row" | cut -f2)"
    if [ -z "$_ci_before" ] || [ -z "$_ci_before_uid" ]; then
        _ci_fail "no Ready pod in $CI_ASSERT_STORAGE_NS - the NFS server is not running, so restarting it proves nothing"
        kubectl get pods -n "$CI_ASSERT_STORAGE_NS" -o wide >&2 || true
        return 1
    fi

    _ci_stamp="$(date +%s)"
    _ci_pod="ci-estale-$_ci_stamp"
    _ci_dir="$CI_ASSERT_MOUNT/.ci-stable-identity-$_ci_stamp"

    # Unpinned: the scheduler places it, and the mount it ends up holding is the
    # one that has to survive.
    if ! _ci_start_helper_pod "$_ci_pod" "" "$_ci_img" "$_ci_c"; then
        _ci_fail "client pod could not start with $_ci_c mounted at $CI_ASSERT_MOUNT"
        _ci_delete_pods "$_ci_pod"
        return 1
    fi

    _ci_exec_script "$_ci_pod" "$_ci_dir" <<'PRE' || _ci_run_rc=1
set -e
mkdir -p "$1"
printf 'before-restart' > "$1/before"
ls -1 "$1" >/dev/null
PRE
    if [ "$_ci_run_rc" -ne 0 ]; then
        _ci_fail "the client could not write to $_ci_dir before the restart, so there is nothing left to prove"
        _ci_delete_pods "$_ci_pod"
        return 1
    fi

    printf 'deleting NFS server pod %s in %s\n' "$_ci_before" "$CI_ASSERT_STORAGE_NS"
    if ! kubectl delete pod -n "$CI_ASSERT_STORAGE_NS" "$_ci_before" --wait=true --timeout="${CI_ASSERT_RESTART_TIMEOUT}s" >/dev/null; then
        _ci_fail "could not delete the NFS server pod $_ci_before"
        _ci_delete_pods "$_ci_pod"
        return 1
    fi

    # A pod with a *new uid* has to come back Ready. Matching on the name
    # would never fire - a StatefulSet reuses it - and `kubectl wait --all`
    # would accept an empty namespace as success.
    _ci_deadline=$(( $(date +%s) + CI_ASSERT_RESTART_TIMEOUT ))
    _ci_after_uid=""
    while [ "$(date +%s)" -lt "$_ci_deadline" ]; do
        _ci_row="$(_ci_ready_pods "$CI_ASSERT_STORAGE_NS" | awk -F'\t' -v old="$_ci_before_uid" '$2 != "" && $2 != old { print; exit }')"
        _ci_after="$(printf '%s' "$_ci_row" | cut -f1)"
        _ci_after_uid="$(printf '%s' "$_ci_row" | cut -f2)"
        if [ -n "$_ci_after_uid" ]; then
            break
        fi
        sleep 5
    done
    if [ -z "$_ci_after_uid" ]; then
        _ci_fail "no replacement NFS server pod became Ready within ${CI_ASSERT_RESTART_TIMEOUT}s of deleting $_ci_before"
        kubectl get pods -n "$CI_ASSERT_STORAGE_NS" -o wide >&2 || true
        kubectl describe pods -n "$CI_ASSERT_STORAGE_NS" >&2 || true
        _ci_delete_pods "$_ci_pod"
        return 1
    fi
    printf 'NFS server came back as %s (uid %s -> %s)\n' "$_ci_after" "$_ci_before_uid" "$_ci_after_uid"

    _ci_exec_script "$_ci_pod" "$_ci_dir" <<'POST' || _ci_run_rc=1
d="$1"
rc=0
err=/tmp/ci-stale-err
: > "$err"

# Bound every operation: a wedged `hard` mount blocks in uninterruptible sleep
# and `kubectl exec` has no timeout of its own. Generous, because NFSv4.1's
# ~90s grace period refuses state-mutating operations while it runs and a hard
# mount simply retries through it.
TMO=""
if command -v timeout >/dev/null 2>&1; then
    TMO="timeout 240"
fi

# The create is the load-bearing one: unlike a re-read it cannot be answered out
# of this client's cache, so it has to reach the server carrying a file handle
# obtained before the restart.
if ! $TMO sh -c 'printf after-restart > "$1/after"' sh "$d" 2>>"$err"; then
    echo "creating a file through the pre-restart mount failed"
    rc=1
fi

if ! got="$($TMO cat "$d/before" 2>>"$err")"; then
    echo "reading back the pre-restart file failed"
    rc=1
fi
if [ "$got" != "before-restart" ]; then
    echo "read '$got' from $d/before, expected 'before-restart'"
    rc=1
fi

if ! $TMO ls -1 "$d" >/dev/null 2>>"$err"; then
    echo "listing $d failed"
    rc=1
fi

if grep -qi 'stale' "$err"; then
    echo "ESTALE on the mount this client held across the restart:"
    rc=1
fi
if [ "$rc" -ne 0 ] && [ -s "$err" ]; then
    cat "$err"
fi
exit "$rc"
POST

    _ci_exec_script "$_ci_pod" "$_ci_dir" <<'CLEAN' >/dev/null 2>&1 || true
rm -rf "$1"
CLEAN
    _ci_delete_pods "$_ci_pod"

    if [ "$_ci_run_rc" -ne 0 ]; then
        _ci_fail "the client did not come through the restart of $_ci_before with its file handles intact"
        _ci_rc=1
    fi
    if [ "$_ci_rc" -ne 0 ]; then
        return 1
    fi
    _ci_pass "file handles survive an NFS server restart ($_ci_before, uid $_ci_before_uid -> $_ci_after_uid)"
    return 0
}

assert_netpol_string_matches_overlay() {
    # The storage root is deliberately prefix-free and cannot see the prod
    # overlay's commonLabels, so the NetworkPolicy that opens 2049 has to
    # hardcode both the `app` value and the namespace it admits. Drift shows up
    # as a mount that hangs at 3am rather than as a lint error, so it is checked
    # here, where it costs nothing.
    #
    # Comparing the `app` literal alone is not enough, and every gap below has
    # been mutation-tested against this tree:
    #
    #   - splitting namespaceSelector and podSelector into two `from` elements
    #     turns the AND into an OR, which admits every pod in `openms` (NuXL
    #     included) and every pod anywhere carrying the label. Both selectors
    #     therefore have to sit in ONE element.
    #   - pointing namespaceSelector at another namespace breaks every real
    #     mount while leaving the `app` string correct, so it is compared with
    #     `namespace:` in k8s/base/kustomization.yaml.
    #   - moving the port off 2049 silently closes the export, so the ports are
    #     compared too - and a rule with no `ports` at all opens every port on
    #     the server, which is worse than the drift being guarded against.
    _ci_require kubectl helm jq yq || return 1
    _ci_rc=0

    _ci_expected="$(yq '.commonLabels.app' "$CI_ASSERT_OVERLAY/kustomization.yaml" 2>/dev/null || true)"
    if [ -z "$_ci_expected" ] || [ "$_ci_expected" = "null" ]; then
        _ci_fail "$CI_ASSERT_OVERLAY/kustomization.yaml has no commonLabels.app - there is nothing for the NetworkPolicy to match"
        return 1
    fi
    _ci_expected_ns="$(yq '.namespace' "$CI_ASSERT_BASE/kustomization.yaml" 2>/dev/null || true)"
    if [ -z "$_ci_expected_ns" ] || [ "$_ci_expected_ns" = "null" ]; then
        _ci_fail "$CI_ASSERT_BASE/kustomization.yaml sets no namespace - there is nothing for the NetworkPolicy's namespaceSelector to match"
        return 1
    fi

    # stdout and stderr to separate files: helm and kustomize both warn on
    # stderr, and a warning folded into the rendered stream would be parsed as
    # part of the manifests.
    _ci_rendered="$(mktemp)"
    _ci_err="$(mktemp)"
    if ! _ci_kustomize_storage > "$_ci_rendered" 2>"$_ci_err"; then
        _ci_fail "kubectl kustomize --enable-helm $CI_ASSERT_STORAGE_ROOT failed"
        cat "$_ci_err" >&2 || true
        rm -f "$_ci_rendered" "$_ci_err"
        return 1
    fi
    rm -f "$_ci_err"
    if [ ! -s "$_ci_rendered" ]; then
        _ci_fail "$CI_ASSERT_STORAGE_ROOT rendered nothing - the label check would pass vacuously"
        rm -f "$_ci_rendered"
        return 1
    fi

    if ! grep -q '^kind: NetworkPolicy' "$_ci_rendered"; then
        _ci_fail "$CI_ASSERT_STORAGE_ROOT renders no NetworkPolicy at all, so the export is open to every pod in the cluster"
        rm -f "$_ci_rendered"
        return 1
    fi

    # One JSON document per line, then jq into tagged rows: RULE per ingress
    # rule, FROM per peer, PORT per port. A peer is flattened to
    # <namespace-or-dash> <app-or-dash> <cidr-or-dash>, which is what makes the
    # AND/OR distinction visible - two peers show up as two FROM rows, each with
    # half of the pair missing.
    _ci_rows="$(yq -o=json -I=0 '.' "$_ci_rendered" 2>/dev/null | jq -r '
        select(.kind == "NetworkPolicy")
        | .metadata.name as $n
        | (.spec.ingress // []) as $rules
        | $rules[]
        | . as $r
        | "RULE\t\($n)\t\(($r.from // []) | length)\t\(($r.ports // []) | length)",
          (($r.from // [])[]
           | "FROM\t\($n)\t\(if has("namespaceSelector") then (.namespaceSelector.matchLabels["kubernetes.io/metadata.name"] // "<any>") else "-" end)\t\(if has("podSelector") then (.podSelector.matchLabels.app // "<any>") else "-" end)\t\(if has("ipBlock") then (.ipBlock.cidr // "<any>") else "-" end)"),
          (($r.ports // [])[]
           | "PORT\t\($n)\t\(.protocol // "TCP")\t\(.port)")
    ' 2>/dev/null || true)"
    rm -f "$_ci_rendered"

    if [ -z "$_ci_rows" ]; then
        _ci_fail "$CI_ASSERT_STORAGE_ROOT renders NetworkPolicies but not one ingress rule, so nothing can reach 2049 and every mount hangs"
        return 1
    fi
    printf '%s\n' "$_ci_rows"

    # Every rule has to name its ports. A rule with `from` but no `ports` opens
    # the whole pod, not just NFS.
    _ci_bad="$(printf '%s\n' "$_ci_rows" | awk -F'\t' '$1 == "RULE" && $3 > 0 && $4 == 0 { print $2 }')"
    if [ -n "$_ci_bad" ]; then
        _ci_fail "these NetworkPolicy rules admit traffic on every port, not just NFS: $(printf '%s' "$_ci_bad" | tr '\n' ' ')"
        _ci_rc=1
    fi

    # Ports: TCP 2049 and nothing else.
    _ci_bad="$(printf '%s\n' "$_ci_rows" | awk -F'\t' '$1 == "PORT" && !($3 == "TCP" && $4 == "2049") { printf "%s/%s ", $3, $4 }')"
    if [ -n "$_ci_bad" ]; then
        _ci_fail "the storage NetworkPolicy opens $_ci_bad; NFSv4.1 needs TCP 2049 and only 2049, and anything else is either a hole or a mount that cannot connect"
        _ci_rc=1
    fi

    # Peers that carry a podSelector must carry a namespaceSelector in the SAME
    # element, and vice versa. An element with only one of the two is an OR in
    # disguise.
    _ci_bad="$(printf '%s\n' "$_ci_rows" | awk -F'\t' '$1 == "FROM" && $5 == "-" && $3 == "-" && $4 != "-" { printf "app=%s ", $4 }')"
    if [ -n "$_ci_bad" ]; then
        _ci_fail "the storage NetworkPolicy admits $_ci_bad from ANY namespace - the namespaceSelector and podSelector have to share one 'from' element, or they are ORed"
        _ci_rc=1
    fi
    _ci_bad="$(printf '%s\n' "$_ci_rows" | awk -F'\t' '$1 == "FROM" && $5 == "-" && $3 != "-" && $4 == "-" { printf "%s ", $3 }')"
    if [ -n "$_ci_bad" ]; then
        _ci_fail "the storage NetworkPolicy admits EVERY pod in namespace $_ci_bad, which on the de.NBI cluster includes app=nuxl-app and hands it root over every workspace"
        _ci_rc=1
    fi

    # Values, for the peers that pair the two selectors up.
    _ci_apps="$(printf '%s\n' "$_ci_rows" | awk -F'\t' '$1 == "FROM" && $4 != "-" { print $4 }' | sort -u)"
    if [ -z "$_ci_apps" ]; then
        _ci_fail "$CI_ASSERT_STORAGE_ROOT renders NetworkPolicies, but none of them admits clients by their 'app' label - nothing can be compared with $CI_ASSERT_OVERLAY"
        _ci_rc=1
    else
        _ci_bad="$(printf '%s\n' "$_ci_apps" | grep -Fxv -- "$_ci_expected" || true)"
        if [ -n "$_ci_bad" ]; then
            _ci_fail "the storage NetworkPolicy admits app='$(printf '%s' "$_ci_bad" | tr '\n' ' ')' but $CI_ASSERT_OVERLAY labels its pods app='$_ci_expected', so those pods cannot reach 2049"
            _ci_rc=1
        fi
    fi

    _ci_found_ns="$(printf '%s\n' "$_ci_rows" | awk -F'\t' '$1 == "FROM" && $3 != "-" { print $3 }' | sort -u)"
    if [ -n "$_ci_found_ns" ]; then
        _ci_bad="$(printf '%s\n' "$_ci_found_ns" | grep -Fxv -- "$_ci_expected_ns" || true)"
        if [ -n "$_ci_bad" ]; then
            _ci_fail "the storage NetworkPolicy admits clients from namespace '$(printf '%s' "$_ci_bad" | tr '\n' ' ')' but $CI_ASSERT_BASE/kustomization.yaml deploys the app into '$_ci_expected_ns', so no real client matches"
            _ci_rc=1
        fi
    fi

    # The node rule is informational here: kubelet-side mounts come from a node
    # address, so its CIDR is cluster-specific and cannot be derived from the
    # manifests. Print it, and say so when it is still the shipped placeholder.
    _ci_cidrs="$(printf '%s\n' "$_ci_rows" | awk -F'\t' '$1 == "FROM" && $5 != "-" { print $5 }' | sort -u)"
    if [ -z "$_ci_cidrs" ]; then
        _ci_fail "$CI_ASSERT_STORAGE_ROOT admits no ipBlock on 2049. The provisioner emits in-tree 'nfs:' PVs, which the kubelet mounts from the node's own address - that matches no podSelector, so on a policy-enforcing CNI every mount hangs"
        _ci_rc=1
    else
        printf 'storage NetworkPolicy admits nodes in: %s\n' "$(printf '%s' "$_ci_cidrs" | tr '\n' ' ')"
        if printf '%s\n' "$_ci_cidrs" | grep -q '^192\.0\.2\.'; then
            printf 'NOTE: that is RFC 5737 TEST-NET-1, the shipped placeholder. Set it to the cluster node CIDR before deploying, or every mount will hang (k8s/storage/networkpolicy.yaml).\n'
        fi
    fi

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_pass "the storage NetworkPolicy admits exactly app='$_ci_expected' in namespace '$_ci_expected_ns', ANDed in one peer, on TCP 2049 alone"
    fi
    return "$_ci_rc"
}

assert_netpol_admits_every_node() {
    # The runtime companion to assert_netpol_string_matches_overlay, which can
    # only note that the shipped node CIDR is a placeholder - it reads
    # manifests, and a node address cannot be derived from a manifest.
    #
    # This one has a cluster, so it can answer the question that actually
    # decides whether the storage tier works: is every node's kubelet allowed
    # to reach 2049? The provisioner emits in-tree `nfs:` PVs, which the
    # KUBELET mounts from the node's own address in the host network namespace.
    # That matches no podSelector, so on a policy-enforcing CNI the only thing
    # standing between a worker and an indefinitely hanging mount is an ipBlock
    # covering its node - and the value shipped in networkpolicy.yaml is RFC
    # 5737 TEST-NET-1, which covers nothing.
    #
    # Without this, the CI rewrite that patches that CIDR is an unverified sed:
    # if its target string ever moves, the rewrite no-ops and the suite fails
    # forty minutes later as a Deployment availability timeout that names
    # nothing.
    _ci_require kubectl jq python3 || return 1
    _ci_rc=0

    # Rules are filtered by PORT before their CIDRs are collected. Reading
    # `.from[].ipBlock.cidr` without descending into the sibling `.ports` -
    # and flattening across every policy in the namespace while doing it -
    # produces a check whose PASS string claims 2049 without ever having
    # looked at a port. It is accidentally right on today's single-rule
    # policy; change `port: 2049` to 111, or add any unrelated policy with a
    # broad ipBlock, and it still reports "admitted on 2049" while every
    # cross-node mount hangs. That is exactly the forty-minute Deployment
    # timeout this assertion exists to pre-empt.
    #
    # A rule with no `ports` at all means all ports, so it is kept. `endPort`
    # ranges and named ports are dropped by the equality: fail-safe, since the
    # result is a spurious red rather than a false green.
    _ci_cidrs="$(kubectl get networkpolicy -n "$CI_ASSERT_STORAGE_NS" -o json 2>/dev/null \
        | jq -r '[.items[].spec.ingress[]?
                  | select((.ports // []) | length == 0
                           or any(.[]?; (.port == 2049) and ((.protocol // "TCP") == "TCP")))
                  | .from[]?.ipBlock.cidr // empty] | .[]' 2>/dev/null || true)"
    if [ -z "$_ci_cidrs" ]; then
        _ci_fail "the NetworkPolicies in $CI_ASSERT_STORAGE_NS admit no ipBlock on TCP 2049, so no kubelet can mount the share"
        return 1
    fi

    _ci_nodes="$(kubectl get nodes \
        -o jsonpath='{range .items[*]}{.status.addresses[?(@.type=="InternalIP")].address}{"\n"}{end}' \
        2>/dev/null || true)"
    if [ -z "$_ci_nodes" ]; then
        _ci_fail "could not read any node InternalIP; cannot tell whether the storage NetworkPolicy admits them"
        return 1
    fi

    # python3 rather than shell arithmetic: these are CIDRs, and a prefix-length
    # comparison written in awk is exactly the kind of thing that silently
    # passes on /16 and fails on /12.
    _ci_missing=""
    for _ci_n in $_ci_nodes; do
        if ! CI_NODE_IP="$_ci_n" CI_CIDRS="$_ci_cidrs" python3 -c '
import ipaddress, os, sys
ip = ipaddress.ip_address(os.environ["CI_NODE_IP"])
for c in os.environ["CI_CIDRS"].split():
    try:
        if ip in ipaddress.ip_network(c, strict=False):
            sys.exit(0)
    except ValueError:
        continue
sys.exit(1)
' 2>/dev/null; then
            _ci_missing="$_ci_missing $_ci_n"
        fi
    done

    if [ -n "$_ci_missing" ]; then
        _ci_fail "node InternalIP(s) not admitted on 2049 by the storage NetworkPolicy, so their kubelets cannot mount the workspace share:$_ci_missing (policy admits: $(printf '%s' "$_ci_cidrs" | tr '\n' ' '))"
        _ci_rc=1
    fi

    if [ "$_ci_rc" -eq 0 ]; then
        _ci_pass "every node InternalIP is admitted on 2049 by the storage NetworkPolicy: $(printf '%s' "$_ci_cidrs" | tr '\n' ' ')"
    fi
    return "$_ci_rc"
}
