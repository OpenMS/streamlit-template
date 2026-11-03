"""Load and check an app spec (``app.yaml``).

The spec says what an app built from this template is: identity, inputs,
workflows, result views, deployment targets and which files the app owns.
Generators (the ``new-app-from-spec`` skill), the template-sync job and CI read
it, so the names that used to be repeated across settings.json and the k8s
overlay have one source.

Streamlit-free on purpose: CI and the sync job import it.

    python -m utils.app_spec            # checks ./app.yaml
    python -m utils.app_spec path/to/app.yaml
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).with_name("app_spec.schema.json")
DEFAULT_SPEC = Path("app.yaml")


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a repeated key instead of keeping the last one.

    A second `sync:` block would otherwise silently replace the ownership rules
    the template-sync job applies to conflicts.
    """

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_spec(path: Path | str = DEFAULT_SPEC) -> dict:
    with open(path, encoding="utf-8") as f:
        spec = yaml.load(f, Loader=_UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass
    if not isinstance(spec, dict):
        raise ValueError(f"{path} does not hold a YAML mapping")
    return spec


def schema_errors(spec: dict) -> list[str]:
    validator = Draft202012Validator(load_schema())
    errors = []
    for err in sorted(validator.iter_errors(spec), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in err.path) or "(top level)"
        errors.append(f"{where}: {err.message}")
    return errors


_MISSING = object()


def _yaml_doc(path: Path):
    """Parsed single-document YAML file, None if absent, _MISSING if unparsable."""
    if not path.is_file():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return _MISSING


def _field(doc, *keys):
    for key in keys:
        if isinstance(doc, dict):
            doc = doc.get(key)
        elif isinstance(doc, list) and isinstance(key, int) and key < len(doc):
            doc = doc[key]
        else:
            return None
    return doc


def _overlay_storage(overlay_doc):
    """The workspace claim size an overlay patches in, or None."""
    if not isinstance(overlay_doc, dict):
        return None
    for patch in overlay_doc.get("patches") or []:
        target = patch.get("target") or {}
        if target.get("kind") != "PersistentVolumeClaim":
            continue
        try:
            ops = yaml.safe_load(patch.get("patch") or "") or []
        except yaml.YAMLError:
            continue
        for op in ops if isinstance(ops, list) else []:
            if (isinstance(op, dict) and op.get("op") in ("replace", "add")
                    and op.get("path") == "/spec/resources/requests/storage"):
                return op.get("value")
    return None


# Paths the template keeps current for every app. An app that lists one of
# them in sync.app_owned keeps its own copy at every conflict and stops
# receiving the template's fixes there; app values belong in the overlay,
# CLAUDE.app.md or app.yaml instead.
TEMPLATE_INFRA = (
    "k8s/base/workspace-pvc.yaml",
    "k8s/base/rq-worker-deployment.yaml",
    "k8s/components/memory-tier-low/worker-resources.yaml",
    "CLAUDE.md",
    ".github/workflows/ci.yml",
    ".github/workflows/template-sync.yml",
    ".github/workflows/openms-release.yml",
    "src/workflow/WorkflowManager.py",
)


def owned_template_files(spec: dict) -> list[str]:
    """Template-maintained paths that sync.app_owned claims for the app."""
    return [f for f in TEMPLATE_INFRA if is_app_owned(spec, f)]


def consistency_errors(spec: dict, root: Path | str = ".") -> list[str]:
    """Check the spec against the files it is the source for.

    Only checks what exists: an app without k8s/ is not asked for a namePrefix.
    """
    root = Path(root)
    errors: list[str] = []
    app = spec.get("app", {})
    slug = app.get("slug")

    settings_path = root / "settings.json"
    if settings_path.is_file():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if app.get("name") and settings.get("app-name") != app["name"]:
            errors.append(
                f"app.name is {app['name']!r} but settings.json app-name is "
                f"{settings.get('app-name')!r}"
            )
        online = spec.get("deploy", {}).get("online_deployment")
        if online is not None and settings.get("online_deployment") != online:
            errors.append(
                f"deploy.online_deployment is {online} but settings.json has "
                f"{settings.get('online_deployment')}"
            )

    overlay = root / "k8s" / "overlays" / "prod" / "kustomization.yaml"
    overlay_doc = _yaml_doc(overlay)
    rel = overlay.relative_to(root) if overlay_doc is not None else None
    if overlay_doc is _MISSING:
        errors.append(f"{rel} is not valid YAML")
    elif overlay_doc is not None:
        prefix = _field(overlay_doc, "namePrefix")
        if not prefix:
            errors.append(f"{rel} has no namePrefix")
        elif slug and prefix != f"{slug}-":
            errors.append(
                f"app.slug is {slug!r} but {rel} has namePrefix {prefix!r} "
                f"(expected {slug + '-'!r})"
            )
        image = app.get("image")
        new_name = _field(overlay_doc, "images", 0, "newName")
        if image and new_name and new_name != image:
            errors.append(
                f"app.image is {image!r} but {rel} deploys {new_name!r} "
                "(images[0].newName)"
            )
        overlay_text = overlay.read_text(encoding="utf-8")
        for host in spec.get("deploy", {}).get("k8s", {}).get("hosts", []):
            if f"Host(`{host}`)" not in overlay_text:
                errors.append(
                    f"deploy.k8s.hosts lists {host!r}, but {rel} has no "
                    f"Host(`{host}`) route"
                )

    # The storage tier (k8s/storage/) is shared by every app on a cluster and
    # carries no app name; what is per app is the size of its workspace share.
    # The size is an app value, so it lives in the prod overlay as a patch on
    # the claim; the base value is only the default for an overlay without one.
    want_size = spec.get("deploy", {}).get("k8s", {}).get("storage")
    pvc = root / "k8s" / "base" / "workspace-pvc.yaml"
    pvc_doc = _yaml_doc(pvc)
    if pvc_doc is _MISSING:
        errors.append(f"{pvc.relative_to(root)} is not valid YAML")
    elif pvc_doc is not None and want_size:
        size = _field(pvc_doc, "spec", "resources", "requests", "storage")
        where = pvc.relative_to(root)
        patched = _overlay_storage(overlay_doc)
        if patched is not None:
            size, where = patched, rel
        if size != want_size:
            errors.append(
                f"deploy.k8s.storage is {want_size!r} but {where} requests {size!r}"
            )

    input_keys = set(spec.get("inputs", {}))
    for wf in spec.get("workflows", []):
        for key in wf.get("inputs", []):
            if key not in input_keys:
                errors.append(
                    f"workflow {wf.get('name')!r} uploads into {key!r}, "
                    "which is not a key of inputs"
                )
        for step in wf.get("steps", []):
            script = step.get("python")
            if script and not (root / "src" / "python-tools" / f"{script}.py").is_file():
                errors.append(
                    f"workflow {wf.get('name')!r} runs python tool {script!r}, "
                    f"but src/python-tools/{script}.py does not exist"
                )

    for page in spec.get("pages", []):
        if not (root / page).is_file():
            errors.append(f"pages lists {page}, which does not exist")

    return errors


def check(path: Path | str = DEFAULT_SPEC, root: Path | str | None = None) -> list[str]:
    path = Path(path)
    spec = load_spec(path)
    errors = schema_errors(spec)
    if not errors:
        errors = consistency_errors(spec, path.parent if root is None else root)
    return errors


def is_app_owned(spec: dict, file_path: str) -> bool:
    """True if ``file_path`` (repo-relative, forward slashes) is app-owned."""
    patterns = spec.get("sync", {}).get("app_owned", [])
    return any(fnmatch.fnmatch(file_path, p) for p in patterns)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_SPEC
    if not path.is_file():
        print(f"{path}: not found", file=sys.stderr)
        return 2
    errors = check(path)
    for e in errors:
        print(f"{path}: {e}", file=sys.stderr)
    if not errors:
        print(f"{path}: ok")
        spec = load_spec(path)
        for f in owned_template_files(spec):
            print(
                f"{path}: note: sync.app_owned covers {f}, so template syncs "
                "keep this app's copy and drop the template's changes there",
                file=sys.stderr,
            )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
