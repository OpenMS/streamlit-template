#!/usr/bin/env bash
# Inject the cluster's own node addresses into the storage NetworkPolicy.
#
#   kubectl kustomize --enable-helm k8s/storage/ \
#     | k8s/storage/set-node-cidrs.sh \
#     | kubectl apply -f -
#
# WHY THIS EXISTS
#
# `allow-nfs-from-nodes` in networkpolicy.yaml ships an ipBlock of
# 192.0.2.0/24 - RFC 5737 TEST-NET-1, routed nowhere - because the addresses it
# actually needs are a property of the cluster, not of this repository. The
# provisioner emits in-tree `nfs:` PersistentVolumes, which the KUBELET mounts
# from the node's own address in the host network namespace. That matches no
# podSelector, so on a policy-enforcing CNI an ipBlock covering the nodes is the
# only thing standing between a worker and an indefinitely hanging mount.
#
# Until now the documented procedure was to hand-edit that value before the
# first deploy. That is the wrong shape for a template: it puts cluster-specific
# configuration inside a tracked manifest, so every fork's tree diverges from
# upstream on exactly one line and every `git pull` can conflict on it. Worse,
# the edit is easy to forget and its failure mode is a forty-minute hang whose
# message ("mount.nfs: Connection timed out") names nothing.
#
# So the placeholder STAYS as the shipped default - an operator who bypasses
# this script still gets the loud, safe failure rather than a wide-open policy -
# and the real value is computed here and patched into the RENDERED STREAM.
# Nothing on disk is modified. This is the same shape the CI kind jobs have used
# since the storage tier landed, which is the only version of this mechanism
# that has ever been exercised.
#
# WHAT IT EMITS
#
# One /32 per node, not a covering range. The tightest possible rule, and
# tighter than a human would reasonably pick by hand: a hostNetwork pod shares
# its node's address and is admitted by this rule whatever its labels say, so
# every address in the range that is not a node is a hole.
#
# Requires: kubectl (pointed at the target cluster), yq.

set -euo pipefail

POLICY_NAME="${POLICY_NAME:-allow-nfs-from-nodes}"
PLACEHOLDER="${PLACEHOLDER:-192.0.2.0/24}"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*" >&2; }

for tool in kubectl yq; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is not on PATH"
done

manifest="$(cat)"
[ -n "$manifest" ] || die "no manifests on stdin; pipe 'kubectl kustomize --enable-helm k8s/storage/' into this script"

# Refuse if the placeholder is gone. Without this the patch below silently
# no-ops on a manifest someone has already hand-edited, and the operator is
# left believing this script set the value when it did not.
printf '%s' "$manifest" | grep -q "cidr: $PLACEHOLDER" \
    || die "the rendered manifests do not contain 'cidr: $PLACEHOLDER'.
       Either networkpolicy.yaml no longer carries the placeholder - in which
       case this patch would silently do nothing - or the value has already
       been set by hand, which this script is meant to replace."

# --- the addresses -----------------------------------------------------------

nodes="$(kubectl get nodes \
    -o jsonpath='{range .items[*]}{.status.addresses[?(@.type=="InternalIP")].address}{"\n"}{end}' \
    2>/dev/null | grep -v '^$' || true)"
[ -n "$nodes" ] || die "kubectl returned no node InternalIPs. Is kubectl pointed at the target cluster?"

node_count="$(printf '%s\n' "$nodes" | wc -l | tr -d ' ')"
note "nodes: $(printf '%s' "$nodes" | tr '\n' ' ')"

# --- the safety check that matters -------------------------------------------
#
# The export is no_root_squash: anything that can reach 2049 acts as root on
# every user's workspace. A rule admitting the POD network would therefore hand
# every pod in the cluster - including other tenants' - root over every
# workspace, and nothing about that is visible from outside.
#
# A node address should never sit inside the pod or service CIDR, so this
# should never fire. It is here because the consequence of it firing unnoticed
# is unbounded, and because the check costs one API read.

pod_cidr="$(kubectl -n kube-system get cm cilium-config \
    -o jsonpath='{.data.cluster-pool-ipv4-cidr}' 2>/dev/null || true)"
if [ -z "$pod_cidr" ]; then
    pod_cidr="$(kubectl get nodes -o jsonpath='{.items[0].spec.podCIDR}' 2>/dev/null || true)"
fi

if [ "${SKIP_POD_CIDR_CHECK:-}" = "1" ]; then
    note "WARNING: SKIP_POD_CIDR_CHECK=1 - the pod-network overlap check was skipped."
elif [ -n "$pod_cidr" ]; then
    # Exit codes, not output. `command -v python3 && python3 ... || true` looks
    # equivalent and is not: an interpreter that EXISTS but fails to run - the
    # Windows Store stub is one, a broken venv shim is another - yields empty
    # output, which is indistinguishable from "checked, found nothing" and
    # passes silently. That is the failure this whole check exists to prevent,
    # reproduced one level up. So: 0 = clean, 1 = overlap, anything else = the
    # check did not run, and the caller must not read that as clean.
    set +e
    overlap="$(NODES="$nodes" POD_CIDR="$pod_cidr" python3 -c '
import ipaddress, os, sys
try:
    net = ipaddress.ip_network(os.environ["POD_CIDR"], strict=False)
except ValueError:
    sys.exit(3)
bad = [n for n in os.environ["NODES"].split()
       if ipaddress.ip_address(n) in net]
if bad:
    print(" ".join(bad))
    sys.exit(1)
sys.exit(0)' 2>/dev/null)"
    rc=$?
    set -e
    case "$rc" in
        0) note "pod network $pod_cidr contains no node address - ok" ;;
        1) die "node address(es) $overlap fall inside the pod network $pod_cidr.
       Admitting them would also admit every pod in the cluster, and the NFS
       export is no_root_squash - that is root on every user's workspace.
       Refusing." ;;
        *) die "could not evaluate whether the node addresses overlap the pod
       network $pod_cidr (python3 exited $rc). Refusing rather than assuming
       they do not: getting this wrong exposes every workspace to every pod.
       Install a working python3, or set SKIP_POD_CIDR_CHECK=1 having checked
       by hand that no node address falls inside $pod_cidr." ;;
    esac
else
    note "NOTE: could not determine the pod CIDR, so the overlap check did not run.
      Confirm by hand that no node address above falls inside the pod network."
fi

# --- Cilium ------------------------------------------------------------------
#
# Cilium is what the de.NBI user clusters run, and from 1.14 remote nodes carry
# the `remote-node` identity. CIDR rules do NOT select node identities unless
# the agent runs with policy-cidr-match-mode=nodes, so on a default Cilium the
# rule this script writes is correct and still ignored - and the symptom is the
# same silent hang the placeholder produces.
#
# CI cannot catch this: kind runs kindnetd, which enforces ipBlock normally. So
# eight green kind jobs say nothing about whether Cilium will honour this.

if kubectl -n kube-system get cm cilium-config >/dev/null 2>&1; then
    mode="$(kubectl -n kube-system get cm cilium-config \
        -o jsonpath='{.data.policy-cidr-match-mode}' 2>/dev/null || true)"
    if [ "$mode" != "nodes" ]; then
        if [ "${ALLOW_CILIUM_WITHOUT_NODE_CIDR_MATCH:-}" = "1" ]; then
            note "WARNING: Cilium has policy-cidr-match-mode='${mode:-<unset>}', not 'nodes'.
         Proceeding because ALLOW_CILIUM_WITHOUT_NODE_CIDR_MATCH=1. If mounts
         hang, this is the first thing to re-check."
        else
            die "Cilium is installed and policy-cidr-match-mode is '${mode:-<unset>}', not 'nodes'.
       From Cilium 1.14 remote nodes carry the 'remote-node' identity, and CIDR
       rules do not select node identities unless that flag is set - so the
       policy this script writes would be correct and silently ignored, and
       every cross-node mount would hang with no message naming the cause.

       Fix the cluster (set policy-cidr-match-mode=nodes on the Cilium agent),
       or re-run with ALLOW_CILIUM_WITHOUT_NODE_CIDR_MATCH=1 if you know this
       cluster admits node traffic some other way.

       Do NOT widen the CIDR to work around this. A range wide enough to be
       matched by a different mechanism is a range wide enough to expose the
       export."
        fi
    else
        note "Cilium policy-cidr-match-mode=nodes - CIDR rules select node identities, ok"
    fi
fi

# --- patch -------------------------------------------------------------------

blocks="["
for ip in $nodes; do
    blocks="$blocks{\"ipBlock\":{\"cidr\":\"$ip/32\"}},"
done
blocks="${blocks%,}]"

note "admitting $node_count node(s) on TCP 2049, one /32 each"

printf '%s' "$manifest" | yq "
  (select(.kind == \"NetworkPolicy\" and .metadata.name == \"$POLICY_NAME\")
   | .spec.ingress[0].from) = $blocks"
