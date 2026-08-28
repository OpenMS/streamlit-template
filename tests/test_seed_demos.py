"""
Red tests for the ``.demos`` seeding race (Step 2 of the multi-node plan).

``k8s/base/streamlit-deployment.yaml`` seeds the demo workspaces from an
initContainer that runs, under ``replicas: 2``::

    mkdir -p /workspaces-streamlit-template/.demos
    cp -rn /app/example-data/workspaces/. /workspaces-streamlit-template/.demos/

``cp -rn`` has two failure branches, one silent and one fatal (docs/a16-storage-runbook.md
section 2):

* **Silent** - ``cp`` writes in place with no temp-and-rename, so replica B can
  see a file replica A is still writing, decide it exists, and skip it. Worse, a
  replica killed mid-copy (eviction, node drain, OOM) leaves a truncated file
  that every later run skips, because ``-n`` only looks at existence. The demo
  workspace is then permanently broken and never repairs itself.
* **Fatal** - ``-n`` does not apply to directories; ``mkdirat`` /
  ``openat(O_EXCL)`` returning ``EEXIST`` is a hard ``exit 1``, so the losing pod
  ends in ``Init:CrashLoopBackOff`` and never self-resolves.

Both get sharper once the workspace volume is ``ReadWriteMany``, because the two
replicas can then genuinely run at the same instant on different nodes.

The fix is copy-to-private-temp plus ``mv -T``: ``rename(2)`` on a directory is
already atomic, so the winner renames and the loser cleans up and exits 0. A
lock file is the wrong tool.

------------------------------------------------------------------------------
Contract these tests pin
------------------------------------------------------------------------------

``docker/seed-demos.sh`` - one copy of the logic, referenced by both the
Kubernetes manifest and this test, so the shipped script is the tested script.

* Invocation: ``sh docker/seed-demos.sh <SOURCE_DIR> <DEST_DIR>``. Both are also
  accepted from the environment as ``SEED_SOURCE_DIR`` / ``SEED_DEST_DIR``, and
  the destination may default to ``${WORKSPACES_DIR}/.demos``; the tests below
  pass all three, so any of those wirings satisfies them.
* Exit status is **always 0**. The initContainer blocks pod start on a shared
  mount, so a seeding failure must degrade the demos, never the app.
* stdout carries one machine-readable line, ``seed-demos: outcome=<outcome>``,
  naming the branch taken: ``seeded``, ``backfilled``, ``present``,
  ``lost-race`` or ``skipped``. The tests read that line and not the prose
  around it, so re-wording a message cannot turn a correct implementation red -
  and the outcomes are distinct enough to tell the ``mv -T`` loss apart from a
  run that simply found the destination already there.
* The run is bounded by ``timeout`` - an unbounded ``cp`` against a wedged NFS
  mount holds the pod in ``Init`` forever - and the bound is asserted by wedging
  a ``cp`` for ten minutes, not by grepping the source for the word.
* A run that does not complete leaves **no** destination directory behind, so
  the next pod re-seeds from scratch.
* An existing destination is **merged into**, never skipped:
  docs/kubernetes-deployment.md promises that demos shipped in a new image
  appear after a redeploy while entries already on the volume survive, and a
  half-seeded ``.demos/`` - what ``mkdir -p`` + ``cp -rn`` leaves behind when a
  pod is killed mid-copy - must repair itself rather than short-circuit every
  later run forever.
"""

import hashlib
import os
import random
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = REPO_ROOT / "docker" / "seed-demos.sh"
STREAMLIT_DEPLOYMENT = REPO_ROOT / "k8s" / "base" / "streamlit-deployment.yaml"
DOCKERFILES = (
    REPO_ROOT / "Dockerfile",
    REPO_ROOT / "Dockerfile.arm",
    REPO_ROOT / "Dockerfile_simple",
    REPO_ROOT / "Dockerfile_simple.arm",
)

DEST_NAME = ".demos"

# Big enough that a concurrent run is still copying when the second one starts.
_BULK_FILES = 48
_BULK_BYTES = 384 * 1024

# One large file, so an interrupted run is killed while that file is being
# written rather than after the copy already finished. Killing a process tree
# costs ~150ms on Windows, so the copy has to outlast that comfortably.
_HUGE_BYTES = 64 * 1024 * 1024


# ---------------------------------------------------------------------------
# POSIX shell discovery
#
# CI runs on ubuntu-latest, where `sh` is on PATH. On Windows the only usable
# `sh` is the one Git for Windows ships; `bash` in system32 is the WSL launcher,
# which rewrites paths into a different filesystem namespace.
# ---------------------------------------------------------------------------
def _find_posix_shell():
    found = shutil.which("sh")
    if found:
        return found
    candidates = []
    git = shutil.which("git")
    if git:
        git_root = Path(git).resolve().parents[1]
        candidates += [git_root / "bin" / "sh.exe", git_root / "usr" / "bin" / "sh.exe"]
    candidates += [
        Path("C:/Program Files/Git/bin/sh.exe"),
        Path("C:/Program Files/Git/usr/bin/sh.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


SHELL = _find_posix_shell()

pytestmark = pytest.mark.skipif(
    SHELL is None, reason="no POSIX shell available to run docker/seed-demos.sh"
)


def _sh_path(path) -> str:
    """
    Render a path the way the POSIX shell under test expects it.

    A trailing separator is preserved: `Path.as_posix()` drops it, and one test
    passes `<ws>/.demos/` deliberately, because a script that derives its
    staging directory from `${DEST_DIR}.tmp...` behaves very differently when
    the destination ends in a slash.
    """
    text = Path(path).as_posix()
    if os.name == "nt" and len(text) > 1 and text[1] == ":":
        text = "/" + text[0].lower() + text[2:]
    if str(path).endswith(("/", "\\")) and not text.endswith("/"):
        text += "/"
    return text


def _require_seed_script():
    if not SEED_SCRIPT.exists():
        pytest.fail(
            f"{SEED_SCRIPT} does not exist.\n"
            "The seeding logic is still inlined in "
            "k8s/base/streamlit-deployment.yaml, where it cannot be tested. "
            "Extract it to docker/seed-demos.sh and have the manifest run that "
            "one copy (docs/a16-storage-runbook.md section 2)."
        )


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------
def _write_source_tree(root: Path) -> None:
    """A stand-in for example-data/workspaces: nested dirs and bulky files."""
    rng = random.Random(20260817)

    (root / "demo-workspace").mkdir(parents=True)
    (root / "demo-workspace" / "params.json").write_text(
        '{"example-x-dimension": 100}\n', encoding="utf-8"
    )
    (root / "demo-workspace" / "nested" / "deep").mkdir(parents=True)
    (root / "demo-workspace" / "nested" / "deep" / "note.txt").write_text(
        "kept\n", encoding="utf-8"
    )

    mzml = root / "demo-workspace" / "mzML-files"
    mzml.mkdir()
    for index in range(_BULK_FILES):
        (mzml / f"Sample_{index:02d}.mzML").write_bytes(rng.randbytes(_BULK_BYTES))


@pytest.fixture(scope="session")
def source_tree(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("example-data-workspaces")
    _write_source_tree(root)
    return root


@pytest.fixture(scope="session")
def source_snapshot(source_tree) -> dict:
    return _snapshot(source_tree)


@pytest.fixture(scope="session")
def huge_source_tree(tmp_path_factory) -> Path:
    """A tree dominated by one large file, so the copy is slow to finish."""
    root = tmp_path_factory.mktemp("example-data-huge")
    mzml = root / "demo-workspace" / "mzML-files"
    mzml.mkdir(parents=True)
    (root / "demo-workspace" / "params.json").write_text("{}\n", encoding="utf-8")
    block = random.Random(20260818).randbytes(1024 * 1024)
    with open(mzml / "Huge.mzML", "wb") as handle:
        for _ in range(_HUGE_BYTES // len(block)):
            handle.write(block)
    return root


@pytest.fixture
def workspaces_root(tmp_path) -> Path:
    root = tmp_path / "workspaces-streamlit-template"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# Shims
#
# The script calls `cp` by name, so a directory in front of PATH can replace it
# with one that hangs or dawdles. That is the only portable way to reproduce
# what a wedged NFS server does to a copy, and it is what lets the bounding and
# the rename arbitration be asserted as behaviour rather than as source text.
# ---------------------------------------------------------------------------
@pytest.fixture
def shim_dir(tmp_path) -> Path:
    directory = tmp_path / "shim-bin"
    directory.mkdir()
    return directory


def _install_shim(directory: Path, name: str, body: str) -> Path:
    shim = directory / name
    shim.write_text(f"#!/bin/sh\n{body}", encoding="utf-8", newline="\n")
    shim.chmod(0o755)
    return shim


def _shim_env(directory: Path, **extra) -> dict:
    # Native form, not the shell's: PATH is handed to the shell by the OS, and
    # the MSYS runtime converts a well-formed Windows PATH into POSIX form for
    # the child. A POSIX entry spliced into a Windows PATH survives neither.
    separator = ";" if os.name == "nt" else ":"
    entry = str(directory) if os.name == "nt" else _sh_path(directory)
    env = {"PATH": entry + separator + os.environ.get("PATH", "")}
    env.update(extra)
    return env


def _shell_has(command: str) -> bool:
    """Whether the POSIX shell under test can find `command` on its PATH."""
    if SHELL is None:
        return False
    probe = subprocess.run(
        [SHELL, "-c", f"command -v {command}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0 and probe.stdout.strip() != ""


def _require_shell_timeout() -> None:
    if not _shell_has("timeout"):
        pytest.skip("no `timeout` for the shell to bound the run with")


def _real_cp() -> str:
    """The `cp` the shim delegates to, as an absolute path the shell resolves."""
    probe = subprocess.run(
        [SHELL, "-c", "command -v cp"], capture_output=True, text=True, check=False
    )
    path = probe.stdout.strip().splitlines()[0] if probe.stdout.strip() else ""
    if not path.startswith("/"):
        pytest.skip("cannot locate a real `cp` for the slow-copy shim")
    return path


def _snapshot(root: Path) -> dict:
    """Map every entry under ``root`` to its type and content digest."""
    snapshot = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(str(path)))
        elif path.is_dir():
            snapshot[relative] = ("dir", None)
        else:
            snapshot[relative] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
    return snapshot


def _total_bytes(root: Path) -> int:
    """Bytes currently under ``root``, tolerating a tree being written to."""
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _describe(actual: dict, expected: dict) -> str:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    differing = sorted(
        name for name in set(actual) & set(expected) if actual[name] != expected[name]
    )
    return f"missing={missing} extra={extra} differing={differing}"


def _assert_complete(dest: Path, expected: dict) -> None:
    assert dest.is_dir(), f"{dest} was not created"
    actual = _snapshot(dest)
    assert actual == expected, (
        "seeded tree is not a byte-complete copy of the source: "
        + _describe(actual, expected)
    )


def _popen_seed(source, dest, workspaces_root, script=None, extra_env=None):
    env = dict(os.environ)
    env["WORKSPACES_DIR"] = _sh_path(workspaces_root)
    env["SEED_SOURCE_DIR"] = _sh_path(source)
    env["SEED_DEST_DIR"] = _sh_path(dest)
    env.update(extra_env or {})
    kwargs = {}
    if os.name != "nt":
        # Own process group, so an interrupted run takes `cp` down with the
        # shell instead of orphaning it to finish the copy behind our back.
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [SHELL, _sh_path(script or SEED_SCRIPT), _sh_path(source), _sh_path(dest)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        **kwargs,
    )


def _kill_tree(proc) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()


def _run_seed(source, dest, workspaces_root, timeout: int = 300, **kwargs):
    proc = _popen_seed(source, dest, workspaces_root, **kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        pytest.fail(
            f"docker/seed-demos.sh did not finish within {timeout}s. The copy "
            "must be bounded so a wedged mount cannot hold the pod in Init."
        )
    return proc.returncode, stdout, stderr


# The documented outcomes, and whether each one means the run installed
# something. Reading a declared token rather than the prose keeps a correct
# implementation from going red over a re-worded message - `_NOOP_MARKERS`
# containing "race" would have failed a winner that announced "won the race".
_OUTCOMES = {
    "seeded": "seeded",
    "backfilled": "seeded",
    "present": "noop",
    "lost-race": "noop",
    "skipped": "noop",
}
_OUTCOME_PREFIX = "seed-demos: outcome="


def _outcome(stdout: str) -> str:
    """The outcome token the run declared, as its own line on stdout."""
    declared = [
        line.strip()[len(_OUTCOME_PREFIX):].strip()
        for line in stdout.splitlines()
        if line.strip().startswith(_OUTCOME_PREFIX)
    ]
    assert declared, (
        "the run declared no outcome. docker/seed-demos.sh must print exactly "
        f"one `{_OUTCOME_PREFIX}<outcome>` line so a test reads a declared "
        f"branch rather than guessing from prose.\nstdout: {stdout!r}"
    )
    # The last one wins: a run killed by its own `timeout` prints the child's
    # verdict and then the parent's, and the parent's is the authoritative one.
    outcome = declared[-1]
    assert outcome in _OUTCOMES, (
        f"unknown outcome {outcome!r}; the documented set is "
        f"{sorted(_OUTCOMES)}\nstdout: {stdout!r}"
    )
    return outcome


def _classify(stdout: str) -> str:
    """Whether a run installed anything, from the outcome it declared."""
    return _OUTCOMES[_outcome(stdout)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_seed_demos_copies_the_whole_tree(source_tree, source_snapshot, workspaces_root):
    _require_seed_script()
    dest = workspaces_root / DEST_NAME

    code, stdout, stderr = _run_seed(source_tree, dest, workspaces_root)

    assert code == 0, f"exit {code}\nstdout: {stdout}\nstderr: {stderr}"
    assert _classify(stdout) == "seeded", f"unexpected stdout: {stdout!r}"
    _assert_complete(dest, source_snapshot)
    assert sorted(p.name for p in workspaces_root.iterdir()) == [DEST_NAME], (
        "the staging directory must not survive a successful seed"
    )


def test_second_run_is_a_noop_and_exits_zero(
    source_tree, source_snapshot, workspaces_root
):
    """The already-seeded path. `cp -rn` fails here with EEXIST -> exit 1."""
    _require_seed_script()
    dest = workspaces_root / DEST_NAME

    first_code, _, first_err = _run_seed(source_tree, dest, workspaces_root)
    assert first_code == 0, first_err

    code, stdout, stderr = _run_seed(source_tree, dest, workspaces_root)

    assert code == 0, (
        "a pod restarting against an already-seeded volume must exit 0, not "
        f"land in Init:CrashLoopBackOff.\nexit {code}\nstdout: {stdout}\n"
        f"stderr: {stderr}"
    )
    assert _classify(stdout) == "noop", f"unexpected stdout: {stdout!r}"
    _assert_complete(dest, source_snapshot)
    assert sorted(p.name for p in workspaces_root.iterdir()) == [DEST_NAME]


def test_concurrent_seed_no_corruption(source_tree, source_snapshot, workspaces_root):
    """
    Two replicas seeding one volume at the same moment.

    Exactly one may report seeding; the other must exit 0 having done nothing;
    and the result must be a byte-complete copy with no staging leftovers.
    """
    _require_seed_script()
    dest = workspaces_root / DEST_NAME

    first = _popen_seed(source_tree, dest, workspaces_root)
    second = _popen_seed(source_tree, dest, workspaces_root)
    results = []
    for proc in (first, second):
        try:
            stdout, stderr = proc.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            pytest.fail("a concurrent seeding run never finished")
        results.append((proc.returncode, stdout, stderr))

    for index, (code, stdout, stderr) in enumerate(results):
        assert code == 0, (
            f"replica {index} exited {code}; the loser of the race must exit 0 "
            f"or its pod never leaves Init.\nstdout: {stdout}\nstderr: {stderr}"
        )

    outcomes = [_classify(stdout) for _, stdout, _ in results]
    assert outcomes.count("seeded") == 1, (
        f"expected exactly one replica to seed, got {outcomes} from "
        f"{[stdout for _, stdout, _ in results]!r}"
    )
    assert outcomes.count("noop") == 1, (
        f"expected exactly one replica to stand down, got {outcomes}"
    )

    _assert_complete(dest, source_snapshot)
    assert sorted(p.name for p in workspaces_root.iterdir()) == [DEST_NAME], (
        "the loser must clean up its staging directory; leaking one per pod "
        "start fills the shared volume with duplicate demo trees"
    )


def test_destination_is_never_observable_in_a_partial_state(
    huge_source_tree, workspaces_root
):
    """
    `.demos` must go from absent to complete in one step, because the step is a
    `rename(2)`. Nothing else makes an interrupted run safe: a replica killed
    mid-copy (eviction, drain, OOM) leaves behind exactly whatever the
    destination looked like at that instant.

    This is the silent branch of the `cp -rn` bug, asserted directly instead of
    by killing a process - `cp -rn` creates `.demos` and copies into it in
    place, so a kill leaves a truncated file that `-n` makes every later run
    skip forever, and the demo workspace never repairs itself.

    Sampling can only miss the partial state, never invent one: for a correct
    implementation the observation below is impossible at any instant.
    """
    _require_seed_script()
    expected = _snapshot(huge_source_tree)
    total = _total_bytes(huge_source_tree)
    dest = workspaces_root / DEST_NAME

    proc = _popen_seed(huge_source_tree, dest, workspaces_root)
    partial = None
    deadline = time.monotonic() + 300
    while proc.poll() is None and time.monotonic() < deadline:
        try:
            if dest.exists():
                seen = _total_bytes(dest)
                if seen < total:
                    partial = seen
                    break
        except OSError:
            continue
    try:
        stdout, stderr = proc.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        pytest.fail("the seeding run never finished")

    assert partial is None, (
        f"{DEST_NAME} was observable holding {partial} of {total} bytes while "
        "the copy was still running; a replica killed at that instant leaves "
        "a truncated demo workspace that no later run repairs. Stage the copy "
        "elsewhere and rename it into place."
    )
    assert proc.returncode == 0, f"stdout: {stdout}\nstderr: {stderr}"
    _assert_complete(dest, expected)


def test_unreachable_source_exits_zero_without_seeding(workspaces_root):
    """
    A failed copy must not block pod start, and must not leave a destination
    directory behind that a later, healthy run would treat as already seeded.
    """
    _require_seed_script()
    missing = workspaces_root.parent / "no-such-source"
    dest = workspaces_root / DEST_NAME

    code, stdout, stderr = _run_seed(missing, dest, workspaces_root)

    assert code == 0, (
        "seeding failure must degrade the demos, not the pod.\n"
        f"exit {code}\nstdout: {stdout}\nstderr: {stderr}"
    )
    assert not dest.exists(), (
        "a failed run left .demos behind; every later run would then short-"
        "circuit on it and the demos would stay empty forever"
    )
    assert list(workspaces_root.iterdir()) == [], "staging leftovers"


def test_a_wedged_copy_cannot_hold_the_pod_in_init(source_tree, workspaces_root, shim_dir):
    """
    The initContainer blocks pod start on the shared mount. An unbounded `cp`
    against a wedged NFS server holds the pod in Init indefinitely, which is
    exactly the outcome the storage design is meant to avoid.

    Asserted by wedging the copy for ten minutes and requiring the run back
    inside its own `SEED_TIMEOUT`. Grepping the source for the word "timeout"
    would pass on any script carrying it in a comment, including one that still
    runs a plain `cp -rn`.
    """
    _require_seed_script()
    _require_shell_timeout()
    _install_shim(shim_dir, "cp", "sleep 600\n")
    dest = workspaces_root / DEST_NAME

    started = time.monotonic()
    code, stdout, stderr = _run_seed(
        source_tree,
        dest,
        workspaces_root,
        timeout=180,
        extra_env=_shim_env(shim_dir, SEED_TIMEOUT="3", SEED_KILL_AFTER="1"),
    )
    elapsed = time.monotonic() - started

    assert elapsed < 120, (
        f"the run took {elapsed:.0f}s against a `cp` wedged for 600s; the whole "
        "run must be bounded, not just hoped to finish"
    )
    assert code == 0, (
        "a run that ran out of time must still let the pod start.\n"
        f"exit {code}\nstdout: {stdout}\nstderr: {stderr}"
    )
    assert _classify(stdout) == "noop", f"unexpected stdout: {stdout!r}"
    assert not dest.exists(), (
        "a run that gave up left .demos behind; every later run would then "
        "short-circuit on it and the demos would stay empty forever"
    )
    assert list(workspaces_root.iterdir()) == [], (
        "the staging directory outlived the run that gave up on it"
    )


def test_runs_without_the_executable_bit(source_tree, source_snapshot, tmp_path):
    """
    The script is invoked as `sh /app/docker/seed-demos.sh` from the manifest,
    so nothing requires it to carry the executable bit - and git records a new
    file as 100644 wherever `core.fileMode` is false, which is every Windows
    clone. A run that re-execs itself as `"$0"` under `timeout` needs the bit
    anyway: the exec fails EACCES, `timeout` reports 126, and the script
    diagnoses an instant exec failure as a wedged mount and seeds nothing.
    """
    _require_seed_script()
    copied = tmp_path / "seed-demos.sh"
    copied.write_bytes(SEED_SCRIPT.read_bytes())
    os.chmod(copied, 0o644)
    workspaces_root = tmp_path / "workspaces-streamlit-template"
    workspaces_root.mkdir()
    dest = workspaces_root / DEST_NAME

    code, stdout, stderr = _run_seed(source_tree, dest, workspaces_root, script=copied)

    assert code == 0, f"exit {code}\nstdout: {stdout}\nstderr: {stderr}"
    assert _classify(stdout) == "seeded", (
        "a non-executable copy of the script seeded nothing, so the run must "
        f"be re-execing itself rather than an interpreter.\nstdout: {stdout!r}"
    )
    _assert_complete(dest, source_snapshot)


def test_the_rename_is_what_arbitrates(
    source_tree, source_snapshot, workspaces_root, shim_dir
):
    """
    Two replicas that both start with the destination absent: the loser must
    lose *at the rename*, not by noticing a finished `.demos` before it began.

    Without the delay the loser can legitimately short-circuit on the
    already-present check, and the concurrency test cannot tell the two apart -
    so an implementation whose `mv -T` arbitration was broken could still pass
    it. A `cp` that takes two seconds puts both replicas past that check before
    either can rename.
    """
    _require_seed_script()
    _install_shim(shim_dir, "cp", 'sleep 2\nexec %s "$@"\n' % _real_cp())
    dest = workspaces_root / DEST_NAME
    env = _shim_env(shim_dir)

    first = _popen_seed(source_tree, dest, workspaces_root, extra_env=env)
    second = _popen_seed(source_tree, dest, workspaces_root, extra_env=env)
    results = []
    for proc in (first, second):
        try:
            stdout, stderr = proc.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            pytest.fail("a concurrent seeding run never finished")
        results.append((proc.returncode, stdout, stderr))

    for index, (code, stdout, stderr) in enumerate(results):
        assert code == 0, (
            f"replica {index} exited {code}\nstdout: {stdout}\nstderr: {stderr}"
        )

    outcomes = sorted(_outcome(stdout) for _, stdout, _ in results)
    assert outcomes == ["lost-race", "seeded"], (
        "with both replicas past the already-present check, one must seed and "
        "the other must lose the rename; got "
        f"{outcomes} from {[stdout for _, stdout, _ in results]!r}"
    )
    _assert_complete(dest, source_snapshot)
    assert sorted(p.name for p in workspaces_root.iterdir()) == [DEST_NAME]


def test_a_half_seeded_destination_repairs_itself(
    source_tree, source_snapshot, workspaces_root
):
    """
    A pod killed mid-copy under the old `mkdir -p` + `cp -rn` leaves `.demos/`
    existing and incomplete - in the worst case existing and *empty*. Skipping
    on the mere existence of the directory makes that permanent: nothing else
    repairs it either, because clean-up-workspaces.py skips top-level dot
    entries.

    So an existing destination is merged into, not stepped around.
    """
    _require_seed_script()
    dest = workspaces_root / DEST_NAME
    dest.mkdir()

    code, stdout, stderr = _run_seed(source_tree, dest, workspaces_root)

    assert code == 0, f"exit {code}\nstdout: {stdout}\nstderr: {stderr}"
    assert _outcome(stdout) == "backfilled", f"unexpected stdout: {stdout!r}"
    _assert_complete(dest, source_snapshot)
    assert sorted(p.name for p in workspaces_root.iterdir()) == [DEST_NAME]


def test_new_image_demos_appear_and_existing_entries_survive(
    source_tree, source_snapshot, workspaces_root
):
    """
    The documented contract (docs/kubernetes-deployment.md, "Demo workspaces"):
    demos shipped in a newer image appear after a redeploy, and everything
    already on the volume - admin-saved demos, hand edits - is preserved
    byte-for-byte.
    """
    _require_seed_script()
    dest = workspaces_root / DEST_NAME

    code, _, stderr = _run_seed(source_tree, dest, workspaces_root)
    assert code == 0, stderr

    # Two things the volume has that the image does not: a demo an admin saved,
    # and an edit to a demo the image ships.
    admin_demo = dest / "admin-saved" / "params.json"
    admin_demo.parent.mkdir(parents=True)
    admin_demo.write_text('{"saved": true}\n', encoding="utf-8")
    edited = dest / "demo-workspace" / "params.json"
    edited.write_text('{"edited": true}\n', encoding="utf-8")

    # ... and one the newer image ships that the volume has never seen.
    added = source_tree / "demo-workspace" / "nested" / "added-by-new-image.txt"
    added.write_text("new\n", encoding="utf-8")
    try:
        code, stdout, stderr = _run_seed(source_tree, dest, workspaces_root)
    finally:
        added.unlink()

    assert code == 0, f"exit {code}\nstdout: {stdout}\nstderr: {stderr}"
    assert _outcome(stdout) == "backfilled", f"unexpected stdout: {stdout!r}"
    assert (dest / "demo-workspace" / "nested" / "added-by-new-image.txt").read_text(
        encoding="utf-8"
    ) == "new\n", "a demo added in a newer image never reached the volume"
    assert admin_demo.read_text(encoding="utf-8") == '{"saved": true}\n', (
        "an admin-saved demo was destroyed by re-seeding"
    )
    assert edited.read_text(encoding="utf-8") == '{"edited": true}\n', (
        "an edit to a shipped demo was overwritten by re-seeding"
    )
    assert sorted(p.name for p in workspaces_root.iterdir()) == [DEST_NAME]


def test_a_trailing_slash_on_the_destination_is_harmless(
    source_tree, source_snapshot, workspaces_root
):
    """
    `SEED_DEST_DIR` and argv are documented inputs, so `<ws>/.demos/` is
    reachable without touching the manifest. Deriving the staging directory
    from it naively puts the staging copy *inside* the destination, brings the
    destination into existence as a side effect of `mkdir -p`, fails the
    `mv -T` with EINVAL, and leaves an empty `.demos/` that short-circuits
    every later run forever.
    """
    _require_seed_script()
    dest = workspaces_root / DEST_NAME

    code, stdout, stderr = _run_seed(
        source_tree, f"{_sh_path(dest)}/", workspaces_root
    )

    assert code == 0, f"exit {code}\nstdout: {stdout}\nstderr: {stderr}"
    assert _classify(stdout) == "seeded", f"unexpected stdout: {stdout!r}"
    _assert_complete(dest, source_snapshot)
    assert sorted(p.name for p in workspaces_root.iterdir()) == [DEST_NAME]


def test_abandoned_staging_directories_are_reclaimed(
    source_tree, source_snapshot, workspaces_root
):
    """
    The EXIT trap does not run on SIGKILL - an eviction, a drain, an OOM - so a
    staging directory can outlive the pod that made it. It is dot-named, and
    clean-up-workspaces.py skips every top-level entry starting with a dot, so
    nothing else on the volume would ever reclaim it: each replacement pod
    arrives under a new ReplicaSet suffix and leaks another full copy of
    example-data/workspaces.
    """
    _require_seed_script()
    dest = workspaces_root / DEST_NAME
    abandoned = workspaces_root / f"{DEST_NAME}.tmp.evicted-pod.1"
    (abandoned / "demo-workspace").mkdir(parents=True)
    (abandoned / "demo-workspace" / "params.json").write_text("{}\n", encoding="utf-8")
    stale = time.time() - 6 * 3600
    os.utime(abandoned, (stale, stale))

    # An in-flight run's staging directory, from a replica still copying.
    in_flight = workspaces_root / f"{DEST_NAME}.tmp.busy-pod.1"
    in_flight.mkdir()

    code, stdout, stderr = _run_seed(source_tree, dest, workspaces_root)

    assert code == 0, f"exit {code}\nstdout: {stdout}\nstderr: {stderr}"
    assert not abandoned.exists(), (
        "an abandoned staging directory survived; on a shared volume it is a "
        "full duplicate of the demo tree that nothing will ever remove"
    )
    assert in_flight.exists(), (
        "a staging directory that was just created was reaped; that would "
        "delete a concurrent replica's copy out from under it mid-run"
    )
    _assert_complete(dest, source_snapshot)


def test_manifest_invokes_the_shared_seed_script():
    manifest = STREAMLIT_DEPLOYMENT.read_text(encoding="utf-8")

    assert "cp -rn" not in manifest, (
        "k8s/base/streamlit-deployment.yaml still seeds with `cp -rn`, which "
        "either skips a partially written file or exits 1 on EEXIST"
    )
    assert SEED_SCRIPT.name in manifest, (
        "the seed-demos initContainer must run docker/seed-demos.sh so the "
        "shipped logic is the tested logic, not a second inline copy"
    )


def _in_image_paths(dockerfile_text: str) -> set:
    """In-image destinations a COPY line could give docker/seed-demos.sh."""
    paths = set()
    for line in dockerfile_text.splitlines():
        parts = line.strip().split()
        if len(parts) < 3 or parts[0].upper() != "COPY":
            continue
        sources, destination = parts[1:-1], parts[-1]
        for source in sources:
            if source.startswith("--"):
                continue
            normalized = source.replace("\\", "/")
            if normalized.endswith(SEED_SCRIPT.name):
                paths.add(
                    destination + SEED_SCRIPT.name
                    if destination.endswith("/")
                    else destination
                )
            elif normalized.rstrip("/") in ("docker", "./docker"):
                paths.add(destination.rstrip("/") + "/" + SEED_SCRIPT.name)
    return paths


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda p: p.name)
def test_every_image_installs_the_seed_script(dockerfile):
    """
    The manifest names a path inside the image. `docker/` is not copied
    wholesale - each Dockerfile installs `docker/entrypoint.sh` by name - so a
    seed script that is never COPYed lands the initContainer in
    Init:CrashLoopBackOff with `not found`, on every image variant.
    """
    manifest = STREAMLIT_DEPLOYMENT.read_text(encoding="utf-8")
    referenced = {
        token
        for token in manifest.replace('"', " ").replace("'", " ").split()
        if token.endswith(SEED_SCRIPT.name)
    }
    assert referenced, "the manifest does not reference docker/seed-demos.sh at all"

    installed = _in_image_paths(dockerfile.read_text(encoding="utf-8"))
    assert referenced & installed, (
        f"{dockerfile.name} does not COPY {SEED_SCRIPT.name} to any path the "
        f"manifest runs ({sorted(referenced)}); it installs it at "
        f"{sorted(installed) or 'nowhere'}"
    )
