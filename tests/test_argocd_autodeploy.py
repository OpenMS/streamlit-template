"""k8s/argocd/ deploys the latest release by itself.

Argo CD syncs the folder through the `<app>-argocd` Application, and the
ImageUpdater picks the newest release image. These checks keep the pieces
consistent in every app that has the folder (the folder is app-owned, this
test is template-owned): the parent syncs this repo's folder and leaves the
updater's tag on the app's Application alone, and allowTags matches release
images, pre-releases included, and nothing else (a version needs a dot:
the short commit SHA tag `0193571-full` is all digits).
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
ARGOCD = ROOT / "k8s" / "argocd"
OVERLAY = ROOT / "k8s" / "overlays" / "prod" / "kustomization.yaml"

pytestmark = pytest.mark.skipif(
    not (ARGOCD / "kustomization.yaml").exists(),
    reason="no self-synced k8s/argocd in this app",
)


def _load(name):
    return yaml.safe_load((ARGOCD / name).read_text(encoding="utf-8"))


def _docs():
    resources = _load("kustomization.yaml")["resources"]
    docs = [_load(r) for r in resources]
    by_kind = {}
    for d in docs:
        by_kind.setdefault(d["kind"], []).append(d)
    return by_kind


def _apps():
    apps = _docs()["Application"]
    parent = next(a for a in apps if a["spec"]["source"]["path"] == "k8s/argocd")
    child = next(
        a for a in apps if a["spec"]["source"]["path"] == "k8s/overlays/prod"
    )
    return parent, child


def test_parent_syncs_this_folder_from_the_deployed_repo_and_branch():
    parent, child = _apps()
    for key in ("repoURL", "targetRevision"):
        assert parent["spec"]["source"][key] == child["spec"]["source"][key]
    assert parent["spec"]["destination"]["namespace"] == "argocd"
    assert parent["metadata"]["name"] == child["metadata"]["name"] + "-argocd"
    assert parent["spec"]["syncPolicy"]["automated"]["selfHeal"] is True


def test_parent_keeps_the_image_updater_tag():
    parent, child = _apps()
    ignored = [
        d
        for d in parent["spec"].get("ignoreDifferences", [])
        if d.get("kind") == "Application"
        and d.get("name") == child["metadata"]["name"]
    ]
    assert ignored, "self-heal would undo every image update"
    assert any(
        ".spec.source.kustomize" in p
        for d in ignored
        for p in d.get("jqPathExpressions", [])
    )
    assert "RespectIgnoreDifferences=true" in parent["spec"]["syncPolicy"]["syncOptions"]


def test_applications_are_never_pruned():
    for app in _docs()["Application"]:
        opts = app["metadata"].get("annotations", {}).get(
            "argocd.argoproj.io/sync-options", ""
        )
        assert "Prune=false" in opts and "Delete=false" in opts, app["metadata"]["name"]


def test_image_updater_targets_the_app_and_its_image():
    _, child = _apps()
    (updater,) = _docs()["ImageUpdater"]
    (ref,) = updater["spec"]["applicationRefs"]
    assert ref["namePattern"] == child["metadata"]["name"]
    overlay = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    (image,) = ref["images"]
    assert image["imageName"] == overlay["images"][0]["newName"]
    assert image["manifestTargets"]["kustomize"]["name"] == overlay["images"][0]["name"]
    assert updater["spec"]["writeBackConfig"]["method"] == "argocd"


def _allow_tags():
    (updater,) = _docs()["ImageUpdater"]
    settings = updater["spec"]["applicationRefs"][0]["images"][0]["commonUpdateSettings"]
    assert settings["updateStrategy"] == "newest-build"
    allow = settings["allowTags"]
    assert allow.startswith("regexp:")
    return re.compile(allow[len("regexp:"):])


def _release_tag():
    """The overlay's starting tag is a release image: `<release>-<variant>`."""
    overlay = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    tag = str(overlay["images"][0]["newTag"])
    release, _, variant = tag.rpartition("-")
    assert variant in ("full", "simple") and release, tag
    # The starting tag may itself be a pre-release (`2.0.0-alpha`): keep the
    # prefix and version only.
    match = re.fullmatch(r"(.*?[0-9]+(?:\.[0-9]+)+)(?:-[0-9A-Za-z.]+)?", release)
    assert match, tag
    return match.group(1), variant


def test_allow_tags_match_releases_and_pre_releases():
    allow = _allow_tags()
    release, variant = _release_tag()
    for tag in (
        release,
        f"{release}-alpha",
        f"{release}-beta2",
        f"{release}-rc.1",
    ):
        assert allow.fullmatch(f"{tag}-{variant}"), tag


def test_allow_tags_skip_everything_else():
    allow = _allow_tags()
    release, variant = _release_tag()
    other = "simple" if variant == "full" else "full"
    for tag in (
        f"{release}-{other}",
        f"{release}-{variant}-amd64",
        f"{release}-{variant}-arm64",
        f"main-{variant}",
        f"develop-{variant}",
        f"claude-project-thread-abc123-{variant}",
        f"1a2b3c4-{variant}",
        f"0193571-{variant}",  # a short commit SHA can be all digits
        "latest",
        "buildcache-amd64",
    ):
        assert not allow.fullmatch(tag), tag


def _projects():
    return {p["metadata"]["name"]: p for p in _docs().get("AppProject", [])}


def _needs_projects():
    if not _projects():
        pytest.skip(
            "no AppProject in k8s/argocd yet: add appproject.yaml and "
            "argocd-appproject.yaml (docs/kubernetes-deployment.md)"
        )


def test_applications_run_in_their_own_projects():
    _needs_projects()
    projects = _projects()
    for app in _docs()["Application"]:
        project = app["spec"]["project"]
        assert project != "default", app["metadata"]["name"]
        assert project in projects, (app["metadata"]["name"], project)
        assert projects[project]["metadata"]["namespace"] == "argocd"


def test_projects_allow_only_this_repository_and_one_namespace():
    _needs_projects()
    parent, child = _apps()
    projects = _projects()
    for app, namespace in ((child, "openms"), (parent, "argocd")):
        spec = projects[app["spec"]["project"]]["spec"]
        assert spec["sourceRepos"] == [app["spec"]["source"]["repoURL"]]
        assert spec["destinations"] == [
            {"server": app["spec"]["destination"]["server"], "namespace": namespace}
        ]
        assert app["spec"]["destination"]["namespace"] == namespace


def test_app_project_allows_no_rbac_and_at_most_the_namespace():
    _needs_projects()
    _, child = _apps()
    spec = _projects()[child["spec"]["project"]]["spec"]
    for entry in spec.get("clusterResourceWhitelist", []):
        assert entry == {"group": "", "kind": "Namespace"}, entry
    overlay = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    if "namespace.yaml" not in overlay.get("resources", []):
        assert not spec.get("clusterResourceWhitelist"), (
            "the overlay deploys no Namespace: drop it from the whitelist"
        )
    assert {"group": "rbac.authorization.k8s.io", "kind": "*"} in spec.get(
        "namespaceResourceBlacklist", []
    )


def test_folder_project_allows_only_the_folders_kinds():
    _needs_projects()
    parent, _ = _apps()
    spec = _projects()[parent["spec"]["project"]]["spec"]
    assert spec.get("clusterResourceWhitelist") == []
    allowed = {(e["group"], e["kind"]) for e in spec["namespaceResourceWhitelist"]}
    groups = {
        "Application": "argoproj.io",
        "AppProject": "argoproj.io",
        "ImageUpdater": "argocd-image-updater.argoproj.io",
    }
    in_folder = {(groups[kind], kind) for kind in _docs()}
    assert in_folder <= allowed, in_folder - allowed
    assert allowed <= set((g, k) for k, g in groups.items())
