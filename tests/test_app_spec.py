"""app.yaml is valid and agrees with the files it is the source for."""

import copy
import json
from pathlib import Path

import pytest

from utils import app_spec

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def spec():
    return app_spec.load_spec(REPO / "app.yaml")


def test_repo_spec_is_valid():
    assert app_spec.check(REPO / "app.yaml") == []


def test_schema_rejects_bad_slug(spec):
    bad = copy.deepcopy(spec)
    bad["app"]["slug"] = "Template_App"
    assert any("app/slug" in e for e in app_spec.schema_errors(bad))


def test_schema_rejects_unknown_key(spec):
    bad = copy.deepcopy(spec)
    bad["app"]["colour"] = "blue"
    assert app_spec.schema_errors(bad)


def test_schema_rejects_unknown_result_role(spec):
    bad = copy.deepcopy(spec)
    bad["results"] = [{"role": "pie-chart"}]
    assert app_spec.schema_errors(bad)


def _app_tree(tmp_path, slug="myapp", name="My App", prefix=None, storage_ns=None):
    (tmp_path / "settings.json").write_text(
        json.dumps({"app-name": name, "online_deployment": False})
    )
    overlay = tmp_path / "k8s" / "overlays" / "prod"
    overlay.mkdir(parents=True)
    (overlay / "kustomization.yaml").write_text(f"namePrefix: {prefix or slug + '-'}\n")
    storage = tmp_path / "k8s" / "storage"
    storage.mkdir(parents=True)
    (storage / "kustomization.yaml").write_text(
        f"namespace: {storage_ns or slug + '-storage'}\n"
    )
    (tmp_path / "src" / "python-tools").mkdir(parents=True)
    return tmp_path


def _spec(slug="myapp", name="My App"):
    return {
        "spec_version": 1,
        "template": {"repository": "OpenMS/streamlit-template", "branch": "main"},
        "app": {"slug": slug, "name": name, "repository": "OpenMS/myapp", "domain": "other"},
        "inputs": {"mzML-files": {"types": ["mzML"]}},
        "workflows": [{"name": "W", "inputs": ["mzML-files"], "steps": [{"tool": "FileInfo"}]}],
    }


def test_consistent_tree_passes(tmp_path):
    root = _app_tree(tmp_path)
    assert app_spec.schema_errors(_spec()) == []
    assert app_spec.consistency_errors(_spec(), root) == []


def test_name_must_match_settings(tmp_path):
    root = _app_tree(tmp_path, name="Other Name")
    errors = app_spec.consistency_errors(_spec(), root)
    assert any("settings.json app-name" in e for e in errors)


def test_slug_must_match_name_prefix(tmp_path):
    root = _app_tree(tmp_path, prefix="template-app-")
    errors = app_spec.consistency_errors(_spec(), root)
    assert any("namePrefix" in e for e in errors)


def test_slug_must_match_storage_namespace(tmp_path):
    root = _app_tree(tmp_path, storage_ns="template-app-storage")
    errors = app_spec.consistency_errors(_spec(), root)
    assert any("storage tier" in e for e in errors)


def test_missing_python_tool_and_unknown_input(tmp_path):
    root = _app_tree(tmp_path)
    s = _spec()
    s["workflows"][0]["inputs"] = ["fasta-file"]
    s["workflows"][0]["steps"].append({"python": "does_not_exist"})
    errors = app_spec.consistency_errors(s, root)
    assert any("fasta-file" in e for e in errors)
    assert any("does_not_exist" in e for e in errors)


def test_is_app_owned(spec):
    assert app_spec.is_app_owned(spec, "content/quickstart.py")
    assert app_spec.is_app_owned(spec, "src/python-tools/example.py")
    assert not app_spec.is_app_owned(spec, "src/workflow/WorkflowManager.py")
