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


def _app_tree(tmp_path, slug="myapp", name="My App", prefix=None, pvc_size="400Gi"):
    (tmp_path / "settings.json").write_text(
        json.dumps({"app-name": name, "online_deployment": False})
    )
    overlay = tmp_path / "k8s" / "overlays" / "prod"
    overlay.mkdir(parents=True)
    (overlay / "kustomization.yaml").write_text(f"namePrefix: {prefix or slug + '-'}\n")
    base = tmp_path / "k8s" / "base"
    base.mkdir(parents=True)
    (base / "workspace-pvc.yaml").write_text(
        f"spec:\n  resources:\n    requests:\n      storage: {pvc_size}\n"
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


def test_storage_size_must_match_workspace_pvc(tmp_path):
    root = _app_tree(tmp_path, pvc_size="100Gi")
    s = _spec()
    s["deploy"] = {"k8s": {"storage": "400Gi"}}
    errors = app_spec.consistency_errors(s, root)
    assert any("deploy.k8s.storage" in e for e in errors)


def test_missing_python_tool_and_unknown_input(tmp_path):
    root = _app_tree(tmp_path)
    s = _spec()
    s["workflows"][0]["inputs"] = ["fasta-file"]
    s["workflows"][0]["steps"].append({"python": "does_not_exist"})
    errors = app_spec.consistency_errors(s, root)
    assert any("fasta-file" in e for e in errors)
    assert any("does_not_exist" in e for e in errors)


def test_is_app_owned():
    # A spec built here, not the repo's: a derived app edits its own list, and
    # this test must not fail on that.
    s = {"sync": {"app_owned": ["content/*", "src/python-tools/*", "app.yaml"]}}
    assert app_spec.is_app_owned(s, "content/quickstart.py")
    assert app_spec.is_app_owned(s, "src/python-tools/example.py")
    assert app_spec.is_app_owned(s, "app.yaml")
    assert not app_spec.is_app_owned(s, "src/workflow/WorkflowManager.py")
    assert not app_spec.is_app_owned({"sync": {"app_owned": []}}, "app.yaml")


def test_duplicate_keys_are_rejected(tmp_path):
    p = tmp_path / "app.yaml"
    p.write_text("sync:\n  app_owned: [a]\nsync:\n  app_owned: [b]\n")
    with pytest.raises(Exception, match="duplicate key"):
        app_spec.load_spec(p)


def test_overlay_without_name_prefix_fails(tmp_path):
    root = _app_tree(tmp_path)
    (root / "k8s/overlays/prod/kustomization.yaml").write_text("resources: [../../base]\n")
    errors = app_spec.consistency_errors(_spec(), root)
    assert any("no namePrefix" in e for e in errors)


def test_image_and_hosts_must_match_overlay(tmp_path):
    root = _app_tree(tmp_path)
    (root / "k8s/overlays/prod/kustomization.yaml").write_text(
        "namePrefix: myapp-\n"
        "images:\n  - name: openms-streamlit\n    newName: ghcr.io/openms/streamlit-template\n"
        "patches:\n  - patch: (Host(`template.webapps.openms.de`))\n"
    )
    s = _spec()
    s["app"]["image"] = "ghcr.io/openms/myapp"
    s["deploy"] = {"k8s": {"hosts": ["myapp.webapps.openms.de"]}}
    errors = app_spec.consistency_errors(s, root)
    assert any("images[0].newName" in e for e in errors)
    assert any("myapp.webapps.openms.de" in e for e in errors)


def test_sync_auto_merge_is_a_boolean(spec):
    ok = copy.deepcopy(spec)
    ok.setdefault("sync", {})["auto_merge"] = False
    assert app_spec.schema_errors(ok) == []
    bad = copy.deepcopy(spec)
    bad.setdefault("sync", {})["auto_merge"] = "yes"
    assert any("sync/auto_merge" in e for e in app_spec.schema_errors(bad))
