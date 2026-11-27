"""The image runs as an unprivileged user, uid 1000, in every runtime.

Docker and docker compose start the image as the user its Dockerfile names,
so everything the entrypoint starts (Redis, nginx, the workers, Streamlit)
must work without root, and an earlier volume, written as root, is handed
over by docker compose's one-off ``own-workspaces`` service.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
# An app may ship only some of the four (FLASHApp has no simple image).
DOCKERFILES = [
    name
    for name in ("Dockerfile", "Dockerfile.arm", "Dockerfile_simple", "Dockerfile_simple.arm")
    if (ROOT / name).exists()
]
ENTRYPOINT = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")


def _instructions(text):
    """Dockerfile instructions in order, continuation lines joined."""
    joined = re.sub(r"\\\n", " ", text)
    for line in joined.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            yield line.split(None, 1)[0].upper(), line


@pytest.mark.parametrize("name", DOCKERFILES)
def test_image_ends_as_uid_1000(name):
    steps = list(_instructions((ROOT / name).read_text(encoding="utf-8")))
    users = [i for i, (op, _) in enumerate(steps) if op == "USER"]
    assert users, name
    last_user = users[-1]
    assert steps[last_user][1] == "USER 1000:1000", name
    # Nothing after it runs as root or switches back.
    assert not [op for op, _ in steps[last_user + 1:] if op in ("RUN", "USER")], name


@pytest.mark.parametrize("name", DOCKERFILES)
def test_state_and_workspaces_belong_to_the_user(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert "useradd -u 1000 -g 1000" in text, name
    assert "chown 1000:1000 /var/lib/openms /workspaces-streamlit-template" in text, name
    # cron needs root; the entrypoint runs the cleanup itself.
    assert "crontab" not in text, name


def test_some_dockerfile_is_checked():
    assert DOCKERFILES


def test_entrypoint_needs_no_root():
    assert "service cron" not in ENTRYPOINT
    assert "STATE_DIR=/var/lib/openms" in ENTRYPOINT
    assert "/var/run/redis.pid" not in ENTRYPOINT
    assert 'NGINX_CONF_DIR="/etc/nginx"' not in ENTRYPOINT
    # nginx: no write to /var/log/nginx or /var/lib/nginx.
    assert 'NGINX_EARLY_LOG="-e stderr"' in ENTRYPOINT
    assert "access_log off;" in ENTRYPOINT
    for temp in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi"):
        assert f"{temp}_temp_path $NGINX_CONF_DIR/" in ENTRYPOINT
    assert "python clean-up-workspaces.py" in ENTRYPOINT


def test_compose_hands_over_old_volumes():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    own = services["own-workspaces"]
    assert own["user"] == "0:0"
    assert own["cap_drop"] == ["ALL"]
    assert set(own["cap_add"]) == {"CHOWN", "DAC_OVERRIDE", "FOWNER"}
    script = own["command"][0]
    # The top folder last: its owner marks the hand-over as done.
    assert script.rstrip().splitlines()[-1].strip() == 'chown 1000:1000 "$$root"'
    assert "|| exit 1" in script
    for name, service in services.items():
        if name == "own-workspaces":
            continue
        assert "user" not in service, name
        needs = service["depends_on"]["own-workspaces"]
        assert needs["condition"] == "service_completed_successfully", name
