"""Every container in k8s/base runs without the default extra rights.

No privilege escalation, the runtime's default seccomp profile, and all
capabilities dropped except the few a container needs by name. The app
containers run as uid 1000 with no capabilities at all; only the containers
that change owners on the shared workspace volume (own-workspaces, the
nightly cleanup) keep root with file capabilities, and Redis keeps what its
entrypoint needs to switch to the redis user.
"""

from pathlib import Path

import pytest
import yaml

BASE = Path(__file__).resolve().parent.parent / "k8s" / "base"

ALLOWED_CAPABILITIES = {
    "openms-streamlit": {"CHOWN", "DAC_OVERRIDE", "FOWNER"},
    "redis": {"CHOWN", "SETGID", "SETUID"},
}

# Containers of the app image that run as root, to change file owners.
ROOT_CONTAINERS = {
    "streamlit-deployment.yaml:own-workspaces",
    "rq-worker-deployment.yaml:own-workspaces",
    "sync-deployment.yaml:own-workspaces",
    "cleanup-cronjob.yaml:cleanup",
}
APP_USER = 1000


def _containers():
    for path in sorted(BASE.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if not doc or doc.get("kind") not in ("Deployment", "CronJob"):
                continue
            spec = doc["spec"]
            if doc["kind"] == "CronJob":
                spec = spec["jobTemplate"]["spec"]
            pod = spec["template"]["spec"]
            for container in pod.get("initContainers", []) + pod["containers"]:
                yield f"{path.name}:{container['name']}", container


CONTAINERS = list(_containers())


def test_base_has_containers():
    assert CONTAINERS


@pytest.mark.parametrize("name,container", CONTAINERS, ids=[n for n, _ in CONTAINERS])
def test_container_security_context(name, container):
    context = container.get("securityContext")
    assert context, f"{name} has no securityContext"
    assert context.get("allowPrivilegeEscalation") is False, name
    assert context.get("privileged", False) is False, name
    assert context.get("seccompProfile", {}).get("type") == "RuntimeDefault", name
    capabilities = context.get("capabilities", {})
    assert capabilities.get("drop") == ["ALL"], name
    image = container["image"].split(":")[0]
    allowed = ALLOWED_CAPABILITIES.get(image, set())
    assert set(capabilities.get("add", [])) <= allowed, name


APP_CONTAINERS = [
    (n, c) for n, c in CONTAINERS if c["image"].split(":")[0] == "openms-streamlit"
]


@pytest.mark.parametrize("name,container", APP_CONTAINERS, ids=[n for n, _ in APP_CONTAINERS])
def test_app_container_user(name, container):
    context = container["securityContext"]
    if name in ROOT_CONTAINERS:
        # The image runs as the app's user, so root must be named.
        assert context.get("runAsUser") == 0, name
        return
    assert context.get("runAsNonRoot") is True, name
    assert context.get("runAsUser") == APP_USER, name
    assert context.get("runAsGroup") == APP_USER, name
    assert not context.get("capabilities", {}).get("add"), name


def test_root_containers_exist():
    names = {n for n, _ in APP_CONTAINERS}
    assert ROOT_CONTAINERS <= names


def _pods():
    for path in sorted(BASE.glob("*-deployment.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if doc and doc.get("kind") == "Deployment":
                yield path.name, doc["spec"]["template"]["spec"]


@pytest.mark.parametrize("name,pod", list(_pods()), ids=[n for n, _ in _pods()])
def test_settings_need_no_write_access_to_app(name, pod):
    """The merged settings.json comes from an init container's volume, and
    the volume is handed to the app's user before any app container starts."""
    init = [c["name"] for c in pod.get("initContainers", [])]
    assert init[:2] == ["own-workspaces", "settings"], name
    for container in pod["containers"]:
        script = " ".join(container.get("args", []))
        assert "/app/settings.json" not in script, name
        mounts = {m["mountPath"]: m for m in container.get("volumeMounts", [])}
        assert mounts["/app/settings.json"]["name"] == "settings", name
    volumes = {v["name"]: v for v in pod["volumes"]}
    assert "emptyDir" in volumes["settings"], name


@pytest.mark.parametrize("name,pod", list(_pods()), ids=[n for n, _ in _pods()])
def test_init_containers_keep_guaranteed_qos(name, pod):
    """Guaranteed QoS needs requests == limits on init containers too."""
    for container in pod.get("initContainers", []):
        if container["name"] not in ("own-workspaces", "settings"):
            continue
        resources = container.get("resources", {})
        assert resources.get("requests"), (name, container["name"])
        assert resources["requests"] == resources.get("limits"), (name, container["name"])


def test_hand_over_marks_done_only_after_the_walk():
    for path in sorted(BASE.glob("*-deployment.yaml")):
        script = path.read_text(encoding="utf-8")
        walk = script.index("! -uid 1000 -exec chown")
        line = script[walk:script.index("\n", walk)]
        assert line.rstrip().endswith("|| exit 1"), path.name
        assert script.index('chown 1000:1000 "$root"') > walk, path.name
