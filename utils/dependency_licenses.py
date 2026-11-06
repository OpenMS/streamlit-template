"""Check the licenses of dependencies an app adds or changes.

Reads the dependency files an app declares its dependencies in, compares them
with a git revision, looks up the license of every dependency that is new or
has a new version, and says where each one has to be attributed. A license
that is not plainly permissive must be listed in ``dependency-licenses.json``
(app-owned) with the reason it is fine, or the check fails.

Dependency files:

- ``requirements*.txt``: Python packages from PyPI
- ``conda-requirements.txt``: command line tools from conda-forge
- ``package.json`` (any folder, ``node_modules`` left out): npm packages

Standard library only, because the Claude Code hook
(``.claude/hooks/dependency_licenses.py``) may run it with a bare interpreter.

    python -m utils.dependency_licenses                     # against HEAD
    python -m utils.dependency_licenses --base origin/main  # what CI runs
    python -m utils.dependency_licenses --all               # every dependency
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

POLICY_FILE = "dependency-licenses.json"

# Plainly permissive: attribution is all they ask for.
OK = "ok"
# Conditions beyond attribution (weak copyleft, source offers, unknown terms):
# someone has to read them once and record the decision.
REVIEW = "review"
# Strong copyleft, non-commercial or proprietary terms: they can change the
# terms the app itself is distributed under, or forbid redistributing it.
RESTRICTED = "restricted"
_RANK = {OK: 0, REVIEW: 1, RESTRICTED: 2}

_RESTRICTED_TERMS = (
    "AGPL", "AFFERO", "SSPL", "SERVER SIDE PUBLIC", "BUSL", "BUSINESS SOURCE",
    "NON-COMMERCIAL", "NONCOMMERCIAL", "CC-BY-NC", "CC BY-NC", "PROPRIETARY",
    "COMMERCIAL", "ALL RIGHTS RESERVED", "ELASTIC LICENSE", "COMMONS CLAUSE",
)
_REVIEW_TERMS = (
    "LGPL", "LESSER GENERAL", "LIBRARY GENERAL", "MPL", "MOZILLA", "EPL",
    "ECLIPSE", "CDDL", "COMMON DEVELOPMENT", "CC-BY-SA", "CC BY-SA", "OSL",
    "EUPL", "ARTISTIC", "CPL", "MS-RL", "APSL", "QPL", "OTHER/PROPRIETARY",
)
_GPL_TERMS = ("GPL", "GENERAL PUBLIC LICENSE")
_OK_TERMS = (
    "MIT", "BSD", "APACHE", "ISC", "PSF", "PYTHON SOFTWARE FOUNDATION",
    "ZLIB", "UNLICENSE", "CC0", "HPND", "BSL-1.0", "BOOST SOFTWARE", "0BSD",
    "PUBLIC DOMAIN", "X11", "WTFPL", "UNICODE", "CC-BY-3.0", "CC-BY-4.0",
    "PYTHON-2.0", "UPL", "BLUEOAK", "NCSA", "W3C", "CURL", "POSTGRESQL",
)

# Where an ecosystem's dependencies end up and what attributes them.
ATTRIBUTION = {
    "pip": (
        "Listed with its license text in the app's About and licenses dialog "
        "(Python packages), read from the installed package. Nothing to add "
        "unless the license asks for more than its notice."
    ),
    "conda": (
        "A program shipped in the Docker images, not listed by the About "
        "dialog: name it with its license and source in the README's "
        "third-party section, and ship its license text if the license asks "
        "for it."
    ),
    "npm": (
        "If its code ends up in shipped JavaScript (a component bundle) or "
        "the desktop installer, keep its license notice in the build output "
        "(webpack keeps license comments in *.LICENSE.txt, electron-builder "
        "ships Electron's LICENSE files). A build tool that ships nothing "
        "needs no attribution."
    ),
}


@dataclass(frozen=True)
class Dependency:
    name: str
    version: str  # pinned version or the spec as written, "" if none
    ecosystem: str  # pip | conda | npm
    source: str  # the file it is declared in


@dataclass
class Finding:
    dep: Dependency
    license: str
    status: str
    accepted: dict | None = None
    note: str = ""
    lookup_failed: bool = False

    @property
    def fails(self) -> bool:
        if self.status == OK or self.lookup_failed:
            return False
        return self.accepted is None

    def to_dict(self) -> dict:
        return {
            "name": self.dep.name,
            "version": self.dep.version,
            "ecosystem": self.dep.ecosystem,
            "file": self.dep.source,
            "license": self.license,
            "status": self.status,
            "accepted": bool(self.accepted),
            "lookup_failed": self.lookup_failed,
            "attribution": ATTRIBUTION[self.dep.ecosystem],
            "note": self.note,
        }


# --------------------------------------------------------------------------
# Dependency files
# --------------------------------------------------------------------------


def is_dependency_file(path: str | os.PathLike) -> bool:
    p = PurePosixPath(str(path).replace("\\", "/"))
    if "node_modules" in p.parts:
        return False
    return (
        fnmatch.fnmatch(p.name, "requirements*.txt")
        or p.name == "conda-requirements.txt"
        or p.name == "package.json"
    )


def normalize_pip(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


_PIP_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")


def parse_requirements(text: str, source: str) -> list[Dependency]:
    deps = []
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].split("\t#", 1)[0].strip()
        if not line or line.startswith(("#", "-", "git+", "http:", "https:")):
            continue
        m = _PIP_LINE.match(line)
        if not m:
            continue
        rest = m.group(3).split(";", 1)[0].strip()
        pin = re.match(r"^===?\s*([^\s,]+)$", rest)
        version = pin.group(1) if pin else rest
        deps.append(Dependency(normalize_pip(m.group(1)), version, "pip", source))
    return deps


def parse_conda(text: str, source: str) -> list[Dependency]:
    deps = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        spec = line.split("::", 1)[-1]
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$", spec)
        if not m:
            continue
        version = m.group(2).strip()
        pin = re.match(r"^==?\s*([^\s,]+)$", version)
        deps.append(
            Dependency(m.group(1).lower(), pin.group(1) if pin else version, "conda", source)
        )
    return deps


def parse_package_json(text: str, source: str) -> list[Dependency]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    deps = []
    for key, eco in (
        ("dependencies", "npm"),
        ("optionalDependencies", "npm"),
        ("peerDependencies", "npm"),
        ("devDependencies", "npm"),
    ):
        for name, version in (data.get(key) or {}).items():
            deps.append(Dependency(name, str(version), eco, source))
    return deps


def parse(path: str, text: str) -> list[Dependency]:
    name = PurePosixPath(path.replace("\\", "/")).name
    if name == "package.json":
        return parse_package_json(text, path)
    if name == "conda-requirements.txt":
        return parse_conda(text, path)
    return parse_requirements(text, path)


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout


def tracked_dependency_files(root: Path, base: str | None = None) -> list[str]:
    """Dependency files in the working tree, plus those only ``base`` has."""
    files = set()
    listed = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    if listed is not None:
        files |= {f for f in listed.splitlines() if is_dependency_file(f)}
    else:
        for p in root.rglob("*"):
            rel = p.relative_to(root).as_posix()
            if p.is_file() and is_dependency_file(rel) and ".git" not in p.parts:
                files.add(rel)
    if base:
        at_base = _git(root, "ls-tree", "-r", "--name-only", base)
        if at_base:
            files |= {f for f in at_base.splitlines() if is_dependency_file(f)}
    return sorted(files)


def changed_dependencies(
    root: Path, files: list[str], base: str | None, everything: bool = False
) -> list[Dependency]:
    """Dependencies in ``files`` that ``base`` (default HEAD) lacks or pins
    differently. A removed dependency needs no check."""
    ref = base or "HEAD"
    found = []
    for rel in files:
        path = root / rel
        if not path.is_file():
            continue
        now = parse(rel, path.read_text(encoding="utf-8", errors="replace"))
        if everything:
            found.extend(now)
            continue
        old_text = _git(root, "show", f"{ref}:{rel}")
        # Every pin counts: a file may pin one package per platform marker.
        before = {(d.name, d.ecosystem, d.version) for d in parse(rel, old_text or "")}
        for d in now:
            if (d.name, d.ecosystem, d.version) not in before:
                found.append(d)
    # One finding per package, even when several files declare it.
    unique = {}
    for d in found:
        unique.setdefault((d.name, d.ecosystem, d.version), d)
    return list(unique.values())


# --------------------------------------------------------------------------
# License lookup
# --------------------------------------------------------------------------

_TIMEOUT = float(os.environ.get("DEPENDENCY_LICENSES_TIMEOUT", "8"))


def _get_json(url: str) -> dict | None:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "dependency-licenses"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.load(resp)
    except Exception:  # noqa: BLE001 - any failure means "could not look up"
        return None


_CLASSIFIER = "License :: "


def license_from_pypi(info: dict) -> str:
    expr = (info.get("license_expression") or "").strip()
    if expr:
        return expr
    names = [
        c.split(" :: ")[-1]
        for c in info.get("classifiers") or []
        if c.startswith(_CLASSIFIER) and c != "License :: OSI Approved"
    ]
    if names:
        return " OR ".join(dict.fromkeys(names)) if len(names) > 1 else names[0]
    text = (info.get("license") or "").strip()
    if text and len(text) <= 80 and "\n" not in text:
        return text
    if text:
        # The whole license text pasted into the field: its first line names it.
        return text.splitlines()[0].strip()[:80]
    return ""


def lookup(dep: Dependency) -> tuple[str, bool]:
    """(license, lookup_failed)."""
    name = urllib.parse.quote(dep.name, safe="@")
    if dep.ecosystem == "pip":
        pinned = re.fullmatch(r"[0-9][0-9A-Za-z.+!-]*", dep.version or "")
        data = None
        if pinned:
            # The pinned release only: another release may carry another license.
            data = _get_json(f"https://pypi.org/pypi/{name}/{dep.version}/json")
        else:
            data = _get_json(f"https://pypi.org/pypi/{name}/json")
        if not data:
            return "", True
        return license_from_pypi(data.get("info") or {}), False
    if dep.ecosystem == "conda":
        data = _get_json(f"https://api.anaconda.org/package/conda-forge/{name}")
        if not data:
            return "", True
        return (data.get("license") or "").strip(), False
    data = _get_json(f"https://registry.npmjs.org/{name.replace('/', '%2F')}/latest")
    if not data:
        return "", True
    lic = data.get("license")
    if isinstance(lic, dict):
        lic = lic.get("type", "")
    if not lic and isinstance(data.get("licenses"), list):
        lic = " OR ".join(
            x.get("type", "") for x in data["licenses"] if isinstance(x, dict)
        )
    return (lic or "").strip(), False


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


def _classify_one(term: str) -> str:
    t = term.strip(" ()").upper()
    if not t or t in {"UNKNOWN", "NONE", "NOASSERTION", "OTHER", "UNLICENSED"}:
        return REVIEW
    if any(x in t for x in _RESTRICTED_TERMS) and "OTHER/PROPRIETARY" not in t:
        return RESTRICTED
    if any(x in t for x in _REVIEW_TERMS):
        return REVIEW
    if any(x in t for x in _GPL_TERMS):
        return RESTRICTED
    if any(x in t for x in _OK_TERMS):
        return OK
    return REVIEW


_TOKEN = re.compile(r"\(|\)|;|[^\s();]+")
_OPERATORS = {"AND", "OR", "WITH", ";"}


def _group_end(tokens: list[str], i: int) -> int:
    """Index after the parenthesis group that opens at ``tokens[i]``."""
    depth = 0
    for j in range(i, len(tokens)):
        depth += {"(": 1, ")": -1}.get(tokens[j], 0)
        if depth == 0:
            return j + 1
    raise ValueError("unbalanced parentheses")


def _words(tokens: list[str], i: int) -> tuple[str, int]:
    """A license name: words up to the next operator. A parenthesis group
    without an operator in it is part of the name, as in ``GNU General Public
    License v3 (GPLv3)``."""
    words = []
    while i < len(tokens) and tokens[i] not in _OPERATORS and tokens[i] != ")":
        if tokens[i] == "(":
            end = _group_end(tokens, i)
            if _OPERATORS & set(tokens[i:end]):
                break
            words.extend(tokens[i:end])
            i = end
        else:
            words.append(tokens[i])
            i += 1
    return " ".join(words), i


def _parse_or(tokens: list[str], i: int) -> tuple[str, int]:
    status, i = _parse_and(tokens, i)
    while i < len(tokens) and tokens[i] == "OR":
        other, i = _parse_and(tokens, i + 1)
        status = min(status, other, key=_RANK.get)
    return status, i


def _parse_and(tokens: list[str], i: int) -> tuple[str, int]:
    status, i = _parse_with(tokens, i)
    while i < len(tokens) and tokens[i] in {"AND", ";"}:
        other, i = _parse_with(tokens, i + 1)
        status = max(status, other, key=_RANK.get)
    return status, i


def _parse_with(tokens: list[str], i: int) -> tuple[str, int]:
    if i < len(tokens) and tokens[i] == "(":
        status, i = _parse_or(tokens, i + 1)
        if i >= len(tokens) or tokens[i] != ")":
            raise ValueError("unbalanced parentheses")
        i += 1
    else:
        name, i = _words(tokens, i)
        if not name:
            raise ValueError("missing license")
        status = _classify_one(name)
    if i < len(tokens) and tokens[i] == "WITH":
        exception, i = _words(tokens, i + 1)
        # An exception only adds permissions to a permissive license. Anything
        # else after WITH, or an exception to another license, needs a person.
        if status != OK or "EXCEPTION" not in exception.upper():
            status = REVIEW
    return status, i


def classify(license: str) -> str:
    """Status of an SPDX expression or a license name.

    ``A OR B`` lets the app pick, so the most permissive option counts;
    ``A AND B`` binds to both, so the strictest counts; parentheses group as in
    SPDX. An exception only adds permissions, so ``Apache-2.0 WITH
    LLVM-exception`` is as permissive as Apache-2.0; one on any other license
    (``GPL-2.0 WITH Classpath-exception-2.0``), or a WITH operand that is not
    an exception, is left to a person. An expression that does not parse is
    read as one license name.
    """
    tokens = _TOKEN.findall(license)
    if not tokens:
        return REVIEW
    try:
        status, i = _parse_or(tokens, 0)
        if i != len(tokens):
            raise ValueError("unexpected token")
    except ValueError:
        return _classify_one(license)
    return status


# --------------------------------------------------------------------------
# Policy and report
# --------------------------------------------------------------------------


def load_policy(root: Path) -> dict:
    path = root / POLICY_FILE
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in (data.get("accepted") or {}).items()}


_ALIASES = (
    # (pattern in the upper-cased, alphanumeric-only name, SPDX id)
    (r"MPL20|MOZILLAPUBLICLICENSE20", "MPL-2.0"),
    (r"LGPLV?21|LESSERGENERALPUBLICLICENSEV?21|LGPLV2\b", "LGPL-2.1"),
    (r"LGPLV?3|LESSERGENERALPUBLICLICENSEV?3", "LGPL-3.0"),
    (r"EPL20|ECLIPSEPUBLICLICENSE20", "EPL-2.0"),
)


def canonical(license: str) -> str:
    """Spelling-independent form, so PyPI's classifier name and the SPDX id
    of the same license compare equal. Each operand of an expression is
    canonicalized on its own, so ``MPL-2.0 AND GPL-3.0-only`` does not compare
    equal to ``MPL-2.0``."""
    parts = re.split(r"\s+(AND|OR|WITH)\s+|\s*;\s*", license.strip())
    if len(parts) > 1:
        return " ".join(
            _canonical_one(p) if i % 2 == 0 else (p or "AND")
            for i, p in enumerate(parts)
        )
    return _canonical_one(license)


def _canonical_one(license: str) -> str:
    flat = re.sub(r"[^A-Z0-9]", "", license.upper())
    for pattern, spdx in _ALIASES:
        if re.search(pattern, flat):
            return spdx
    return flat


def _accepted(policy: dict, dep: Dependency, license: str) -> dict | None:
    key = normalize_pip(dep.name) if dep.ecosystem == "pip" else dep.name
    entry = policy.get(key) or policy.get(dep.name)
    if not entry:
        return None
    # A decision covers the license it was made for. A package that changes
    # its license is asked about again.
    recorded = entry.get("license") or ""
    recorded = [r for r in ([recorded] if isinstance(recorded, str) else recorded) if r]
    if not recorded:
        # A decision has to name the license it accepts.
        return None
    if license and canonical(license) not in {canonical(r) for r in recorded}:
        return None
    return entry


def check(deps: list[Dependency], policy: dict, offline: bool = False) -> list[Finding]:
    def one(dep: Dependency) -> Finding:
        license, failed = ("", True) if offline else lookup(dep)
        status = classify(license)
        accepted = _accepted(policy, dep, license)
        if accepted and not license:
            # Looked up nothing (no metadata, or offline): the reviewed entry
            # says what the license is.
            license = accepted.get("license", "")
            license = license if isinstance(license, str) else " OR ".join(license)
            status = classify(license)
        note = ""
        if failed and not accepted:
            note = "License could not be looked up; check it by hand."
        elif accepted and status != OK:
            note = f"Accepted in {POLICY_FILE}: {accepted.get('reason', '')}".strip()
        elif status != OK:
            note = (
                f"Read the license, then record the decision in {POLICY_FILE} "
                '("accepted": {name: {license, reason, attribution}}).'
            )
        return Finding(dep, license or "unknown", status, accepted, note, failed)

    if not deps:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(deps))) as pool:
        return list(pool.map(one, deps))


def render(findings: list[Finding], markdown: bool = False) -> str:
    if not findings:
        return "No new or changed dependencies."
    lines = []
    if markdown:
        lines += [
            "| Dependency | Version | File | License | Status |",
            "|---|---|---|---|---|",
        ]
        for f in findings:
            status = f.status + (" (accepted)" if f.accepted and f.status != OK else "")
            if f.lookup_failed and not f.accepted:
                status = "not looked up"
            lines.append(
                f"| `{f.dep.name}` | {f.dep.version or '-'} | `{f.dep.source}` "
                f"| {f.license} | {status} |"
            )
        lines.append("")
    else:
        for f in findings:
            mark = "FAIL" if f.fails else ("WARN" if f.lookup_failed or f.status != OK else "ok")
            lines.append(
                f"[{mark}] {f.dep.name} {f.dep.version} ({f.dep.ecosystem}, "
                f"{f.dep.source}): {f.license} -> {f.status}"
            )
            if f.note:
                lines.append(f"       {f.note}")
        lines.append("")
    lines.append("Where to attribute them:")
    for eco in dict.fromkeys(f.dep.ecosystem for f in findings):
        lines.append(f"- {eco}: {ATTRIBUTION[eco]}")
    failing = [f for f in findings if f.fails]
    if failing:
        lines += [
            "",
            "Not accepted yet: "
            + ", ".join(f"{f.dep.name} ({f.license}, {f.status})" for f in failing)
            + f". Read each license and add a reviewed entry to {POLICY_FILE}, "
            "or pick another package.",
        ]
    return "\n".join(lines)


def run(
    root: Path,
    base: str | None = None,
    files: list[str] | None = None,
    everything: bool = False,
    offline: bool = False,
) -> list[Finding]:
    root = Path(root)
    if files is None:
        files = tracked_dependency_files(root, base)
    deps = changed_dependencies(root, files, base, everything)
    return check(deps, load_policy(root), offline=offline)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", help="git revision to compare with (default HEAD)")
    ap.add_argument("--all", action="store_true", help="check every dependency")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument("--summary", help="also write a Markdown report to this file")
    ap.add_argument("files", nargs="*", help="dependency files (default: all)")
    args = ap.parse_args(argv)

    findings = run(Path.cwd(), args.base, args.files or None, args.all)
    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        print(render(findings))
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write("## Dependency licenses\n\n" + render(findings, markdown=True) + "\n")
    return 1 if any(f.fails for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
