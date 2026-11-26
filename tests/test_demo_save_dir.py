"""Demos are read from the image first and saved to the volume.

On Kubernetes a new workspace links to its demo's files, so the demo it
starts from must be read from the container's own disk: read from the
workspace volume (S3-backed storage on some clusters), seeding a workspace
took minutes. The admin's "Save as Demo" must still write to the volume.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from src.common import admin

ROOT = Path(__file__).resolve().parent.parent


def _target(demo_config):
    fake_st = SimpleNamespace(
        session_state=SimpleNamespace(settings={"demo_workspaces": demo_config})
    )
    with patch.object(admin, "st", fake_st):
        return admin.get_demo_target_dir()


def test_save_dir_wins_over_source_dirs():
    config = {"source_dirs": ["/image/demos", "/volume/.demos"], "save_dir": "/volume/.demos"}
    assert _target(config) == Path("/volume/.demos")


def test_without_save_dir_first_source_dir_is_target():
    assert _target({"source_dirs": ["/a", "/b"]}) == Path("/a")
    assert _target({"source_dir": "/legacy"}) == Path("/legacy")


def test_k8s_reads_image_demos_first_and_saves_to_volume():
    config_map = yaml.safe_load((ROOT / "k8s/base/configmap.yaml").read_text())
    demos = json.loads(config_map["data"]["settings-overrides.json"])["demo_workspaces"]
    assert demos["source_dirs"][0] == "/app/example-data/workspaces"
    assert demos["save_dir"] in demos["source_dirs"][1:]
    assert demos["save_dir"].startswith("/workspaces-streamlit-template/")
