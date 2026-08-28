#!/bin/sh
#
# Seed the demo workspaces onto the shared workspaces volume.
#
# Run by the `seed-demos` initContainer in k8s/base/streamlit-deployment.yaml
# and executed directly by tests/test_seed_demos.py, so the shipped logic and
# the tested logic are the same file. Do not inline a second copy in the
# manifest.
#
# Usage: sh seed-demos.sh [SOURCE_DIR] [DEST_DIR]
#   SOURCE_DIR  defaults to $SEED_SOURCE_DIR, then /app/example-data/workspaces
#   DEST_DIR    defaults to $SEED_DEST_DIR, then ${WORKSPACES_DIR}/.demos
#
# This replaces `cp -rn /app/example-data/workspaces/. <dest>/`, which had two
# failure branches under `replicas: 2` and gets sharper once the volume is
# ReadWriteMany and the replicas can genuinely run at the same instant:
#
#   silent  cp writes in place with no temp-and-rename, so a replica can see a
#           file another one is still writing, decide it exists, and skip it.
#           A replica killed mid-copy leaves a truncated file that `-n` makes
#           every later run skip forever, so the demos never repair themselves.
#   fatal   `-n` does not apply to directories, and EEXIST is a hard exit 1, so
#           the losing pod ends in Init:CrashLoopBackOff and never resolves.
#
# The fix is to copy into a private staging directory and rename it into place.
# rename(2) on a directory is atomic and fails on a non-empty target, which is
# exactly the arbitration wanted: the winner renames, the loser cleans up and
# exits 0. A lock file would be the wrong tool.
#
# An existing destination is *merged into*, not skipped: entries the volume is
# missing are copied to a staging name and renamed in one at a time, and
# entries that already exist are never touched. That keeps the two documented
# guarantees (docs/kubernetes-deployment.md, "Demo workspaces") - demos shipped
# in a new image appear after a redeploy, and admin-saved demos and edits on
# the volume survive - while repairing a half-seeded `.demos/` that the old
# `mkdir -p` + `cp -rn` could leave behind forever.
#
# Exit status is always 0. This container gates pod start on a shared network
# filesystem, so a seeding failure must degrade the demos, never the app.
#
# stdout carries one machine-readable line, `seed-demos: outcome=<outcome>`,
# alongside the human-readable ones. tests/test_seed_demos.py reads that line
# rather than the prose, so re-wording a message cannot turn a correct
# implementation red, and the outcomes distinguish the branches that matter:
#
#   seeded      this run copied the tree and renamed it into place
#   backfilled  the destination existed and was missing entries, now restored
#   present     the destination existed and was complete
#   lost-race   another replica renamed its copy in first
#   skipped     nothing was done (no source, copy failed, or ran out of time)
#
set -eu

SOURCE_DIR="${1:-${SEED_SOURCE_DIR:-/app/example-data/workspaces}}"
DEST_DIR="${2:-${SEED_DEST_DIR:-${WORKSPACES_DIR:-/workspaces-streamlit-template}/.demos}}"
SEED_TIMEOUT="${SEED_TIMEOUT:-300}"
SEED_KILL_AFTER="${SEED_KILL_AFTER:-30}"
# Minutes of inactivity after which a staging directory is assumed abandoned.
# Far longer than SEED_TIMEOUT, so a run still in progress is never reaped.
SEED_STAGE_REAP_MINUTES="${SEED_STAGE_REAP_MINUTES:-120}"

# Trailing slashes are stripped before anything derives a path from DEST_DIR.
# With `<ws>/.demos/` the staging directory would be created *inside* the
# destination, `mkdir -p` would bring the destination into existence as a side
# effect, `mv -T` would then fail EINVAL (the target is a path prefix of the
# source), and the empty `.demos/` left behind would short-circuit every later,
# healthy run. SEED_DEST_DIR and argv are both documented inputs, so this is
# reachable without touching the manifest.
while [ "$DEST_DIR" != "/" ] && [ "${DEST_DIR%/}" != "$DEST_DIR" ]; do
    DEST_DIR="${DEST_DIR%/}"
done
while [ "$SOURCE_DIR" != "/" ] && [ "${SOURCE_DIR%/}" != "$SOURCE_DIR" ]; do
    SOURCE_DIR="${SOURCE_DIR%/}"
done

# The staging directory is a sibling of the destination so the rename stays
# within one filesystem.
#
# It is named for the pod *and* the pid. The pid alone is not unique here: each
# pod has its own pid namespace, so two replicas on two nodes writing to one
# ReadWriteMany volume are routinely both pid 1, and would then share a staging
# directory and clobber each other's copy. $HOSTNAME is the pod name, which
# carries the ReplicaSet's random suffix. A restarted pod reuses its name, which
# is why the staging directory is removed before it is created: the leftover can
# only belong to a previous incarnation of this same pod.
seed_host() {
    if [ -n "${HOSTNAME:-}" ]; then
        printf '%s' "$HOSTNAME"
    elif command -v hostname >/dev/null 2>&1; then
        hostname
    else
        printf 'unknown-host'
    fi
}
SEED_STAGE_DIR="${SEED_STAGE_DIR:-${DEST_DIR}.tmp.$(seed_host).$$}"

outcome() {
    echo "seed-demos: outcome=$1"
}

# Bound the whole run rather than just the copy: every syscall below touches
# the shared mount, the `stat` behind `[ -d ]` included, and any of them can
# block. Re-exec under `timeout` so one bound covers all of them, then swallow
# the result. (A process wedged in uninterruptible sleep on a `hard` mount
# survives even SIGKILL; this bounds the reachable-but-slow cases, which are
# the ones a restarting NFS server actually produces.)
#
# The re-exec goes through an interpreter, never `"$0"` on its own: the script
# is installed by `COPY` in four Dockerfiles and run as `sh /app/.../seed-demos.sh`
# from the manifest, so nothing else in the chain needs it to carry the
# executable bit, and a checkout where it does not (git records 100644 for a
# new file when core.fileMode is false, which is every Windows clone) would
# otherwise fail the exec with EACCES - reported by `timeout` as exit 126, and
# indistinguishable from a wedged mount unless the status is inspected.
if [ -z "${SEED_DEMOS_BOUNDED:-}" ] && command -v timeout >/dev/null 2>&1; then
    SEED_DEMOS_BOUNDED=1
    export SEED_DEMOS_BOUNDED SEED_STAGE_DIR
    SEED_SHELL="${SEED_SHELL:-/bin/sh}"
    if [ ! -x "$SEED_SHELL" ]; then
        SEED_SHELL=sh
    fi
    seed_status=0
    timeout -k "$SEED_KILL_AFTER" "$SEED_TIMEOUT" \
        "$SEED_SHELL" "$0" "$SOURCE_DIR" "$DEST_DIR" || seed_status=$?
    if [ "$seed_status" -eq 0 ]; then
        exit 0
    fi
    case "$seed_status" in
        124|137)
            echo "seed-demos: seeding did not finish within ${SEED_TIMEOUT}s, skipping demos"
            echo "seed-demos: pod start must not wait on a wedged mount" >&2
            ;;
        126|127)
            echo "seed-demos: could not run the seeding script, skipping demos"
            echo "seed-demos: $SEED_SHELL $0 exited $seed_status (not executable, or not found)" >&2
            ;;
        *)
            echo "seed-demos: seeding failed, skipping demos"
            echo "seed-demos: $SEED_SHELL $0 exited $seed_status" >&2
            ;;
    esac
    outcome skipped
    # Best-effort, and bounded too: the staging directory is ours alone, and
    # leaking one per pod start would fill the shared volume.
    timeout -k 5 30 rm -rf "$SEED_STAGE_DIR" >/dev/null 2>&1 || true
    exit 0
fi

cleanup() {
    if [ -n "$SEED_STAGE_DIR" ]; then
        rm -rf "$SEED_STAGE_DIR" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

# Reclaim staging directories abandoned by a SIGKILL - an eviction, a drain, an
# OOM - which the trap above cannot cover. They are dot-named siblings of
# `.demos`, and clean-up-workspaces.py skips every top-level entry starting with
# a dot, so nothing else on the volume would ever remove them: a pod replaced
# under a new ReplicaSet suffix comes back with a different name and leaks
# another full copy of example-data/workspaces. Best effort and bounded by the
# same `timeout` as the rest of the run.
sweep_abandoned_stages() {
    stage_parent=$(dirname "$DEST_DIR")
    stage_base=$(basename "$DEST_DIR")
    [ -d "$stage_parent" ] || return 0
    find "$stage_parent" -maxdepth 1 -type d -name "${stage_base}.tmp.*" \
        -mmin "+${SEED_STAGE_REAP_MINUTES}" -exec rm -rf {} + >/dev/null 2>&1 || true
    return 0
}
sweep_abandoned_stages

# Copy the entries the destination is missing, one atomic rename each.
#
# Directories are created empty and filled; files and symlinks are staged
# outside the destination and renamed in, so no reader ever sees a half-written
# demo file. Anything that already exists is left exactly as it is - that is
# what preserves admin-saved demos and hand edits, and it is why this can run on
# every pod start.
backfill_missing() {
    restored=0
    rm -rf "$SEED_STAGE_DIR"
    mkdir -p "$SEED_STAGE_DIR"
    # `find` walks pre-order, so a directory is always created before the
    # entries that go inside it. The list is materialised first: piping into
    # `while` would run the loop in a subshell and lose the counter.
    if ! (cd "$SOURCE_DIR" && find . -mindepth 1) > "$SEED_STAGE_DIR/manifest" 2>/dev/null; then
        return 0
    fi
    while IFS= read -r relative; do
        relative="${relative#./}"
        [ -n "$relative" ] || continue
        target="$DEST_DIR/$relative"
        # -e is false for a broken symlink, so -L is asked as well: a dangling
        # link is still an entry somebody put there deliberately.
        if [ -e "$target" ] || [ -L "$target" ]; then
            continue
        fi
        source_entry="$SOURCE_DIR/$relative"
        if [ -d "$source_entry" ] && [ ! -L "$source_entry" ]; then
            mkdir -p "$target" >/dev/null 2>&1 || true
            continue
        fi
        staged="$SEED_STAGE_DIR/entry.$restored"
        # `mv -T`, not plain `mv`: if a racing replica created the target as a
        # directory between the check above and here, plain `mv` would move the
        # staged copy *inside* it and leave a stray `entry.N` in the tree.
        if cp -R "$source_entry" "$staged" >/dev/null 2>&1 &&
            mv -T "$staged" "$target" >/dev/null 2>&1; then
            restored=$((restored + 1))
        else
            rm -rf "$staged" >/dev/null 2>&1 || true
        fi
    done < "$SEED_STAGE_DIR/manifest"
    rm -rf "$SEED_STAGE_DIR"
    return 0
}

if [ -d "$DEST_DIR" ]; then
    if [ ! -d "$SOURCE_DIR" ]; then
        echo "seed-demos: demos already present, no source tree to merge"
        outcome present
        exit 0
    fi
    backfill_missing
    if [ "$restored" -gt 0 ]; then
        echo "seed-demos: demos already present, restored $restored missing entries"
        outcome backfilled
    else
        echo "seed-demos: demos already present, nothing to do"
        outcome present
    fi
    exit 0
fi

if [ ! -d "$SOURCE_DIR" ]; then
    # No destination directory is created here on purpose: one left behind
    # would short-circuit every later, healthy run.
    echo "seed-demos: no demo source tree, skipping demos"
    echo "seed-demos: $SOURCE_DIR is not a directory" >&2
    outcome skipped
    exit 0
fi

rm -rf "$SEED_STAGE_DIR"
mkdir -p "$SEED_STAGE_DIR"

if ! cp -r "$SOURCE_DIR/." "$SEED_STAGE_DIR/"; then
    echo "seed-demos: copy failed, skipping demos"
    echo "seed-demos: could not copy $SOURCE_DIR into $SEED_STAGE_DIR" >&2
    outcome skipped
    exit 0
fi

if mv -T "$SEED_STAGE_DIR" "$DEST_DIR" 2>/dev/null; then
    SEED_STAGE_DIR=""
    echo "seed-demos: demo workspaces seeded"
    outcome seeded
elif [ -d "$DEST_DIR" ]; then
    # `mv -T` onto an existing non-empty directory fails, which is the whole
    # arbitration mechanism. Another replica got there first.
    echo "seed-demos: another replica seeded the demos first"
    outcome lost-race
else
    echo "seed-demos: could not install the demos, skipping them"
    echo "seed-demos: mv -T $SEED_STAGE_DIR $DEST_DIR failed" >&2
    outcome skipped
fi

exit 0
