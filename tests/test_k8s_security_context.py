"""Every container in k8s/base runs without the default extra rights.

No privilege escalation, the runtime's default seccomp profile, and all
capabilities dropped except the few a container needs by name: the app
containers keep file access on the shared workspace volume, Redis keeps
what its entrypoint needs to switch to the redis user.
"""

from pathlib import Path

import pytest
import yaml

BASE = Path(__file__).resolve().parent.parent / "k8s" / "base"

ALLOWED_CAPABILITIES = {
    "openms-streamlit": {"CHOWN", "DAC_OVERRIDE", "FOWNER"},
    "redis": {"CHOWN", "SETGID", "SETUID"},
}


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
