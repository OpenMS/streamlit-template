"""utils/dependency_licenses.py and its Claude Code hook, without network."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from utils import dependency_licenses as dl

ROOT = Path(__file__).resolve().parents[1]

LICENSES = {
    "requests": "Apache-2.0",
    "gplpkg": "GPL-3.0-or-later",
    "mplpkg": "Mozilla Public License 2.0 (MPL 2.0)",
    "nolicense": "",
    "dual": "GPL-2.0-only OR MIT",
    "sirius-ms": "AGPL-3.0-only",
    "left-pad": "WTFPL",
}


@pytest.fixture(autouse=True)
def fake_lookup(monkeypatch):
    monkeypatch.setattr(dl, "lookup", lambda dep: (LICENSES.get(dep.name, "MIT"), False))


def git(root, *args):
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
             "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(root), "PATH": "/usr/bin:/bin"},
    )


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.33.0\n    # via x\n")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


@pytest.mark.parametrize(
    "license,status",
    [
        ("MIT", dl.OK),
        ("BSD License", dl.OK),
        ("Apache Software License OR BSD License", dl.OK),
        ("BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0", dl.OK),
        ("GNU General Public License v3 (GPLv3)", dl.RESTRICTED),
        ("GPL-3.0-or-later", dl.RESTRICTED),
        ("AGPL-3.0-only", dl.RESTRICTED),
        ("GNU Lesser General Public License v3 (LGPLv3)", dl.REVIEW),
        ("MPL-2.0 AND MIT", dl.REVIEW),
        ("GPL-2.0-only OR MIT", dl.OK),
        ("GPL-2.0 WITH Classpath-exception-2.0", dl.REVIEW),
        ("(MIT OR BSD-3-Clause) AND GPL-2.0 WITH Classpath-exception-2.0", dl.REVIEW),
        ("(MIT OR GPL-3.0-only) AND Apache-2.0", dl.OK),
        ("MIT AND (GPL-3.0-only OR AGPL-3.0-only)", dl.RESTRICTED),
        ("Apache-2.0 WITH GPL-3.0-only", dl.REVIEW),
        ("Mozilla Public License 2.0 (MPL 2.0)", dl.REVIEW),
        ("MIT (", dl.OK),
        ("Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSL-1.0 AND Zlib", dl.OK),
        ("Apache-2.0 WITH LLVM-exception AND MPL-2.0", dl.REVIEW),
        ("Other/Proprietary License", dl.REVIEW),
        ("Free for non-commercial use", dl.RESTRICTED),
        ("", dl.REVIEW),
        ("UNKNOWN", dl.REVIEW),
    ],
)
def test_classify(license, status):
    assert dl.classify(license) == status


def test_parsers():
    pip = dl.parse_requirements(
        "# header\nFoo_Bar[extra]==1.2 ; python_version>'3'\n    # via x\n"
        "baz>=2\n-r other.txt\nxlsxwriter\n", "requirements.txt"
    )
    assert [(d.name, d.version) for d in pip] == [("foo-bar", "1.2"), ("baz", ">=2"), ("xlsxwriter", "")]
    conda = dl.parse_conda("sirius-ms==5.8.6  # [x86_64]\nconda-forge::mono\n", "conda-requirements.txt")
    assert [(d.name, d.version) for d in conda] == [("sirius-ms", "5.8.6"), ("mono", "")]
    npm = dl.parse_package_json(
        json.dumps({"dependencies": {"a": "^1"}, "devDependencies": {"b": "2"}}), "x/package.json"
    )
    assert {(d.name, d.version) for d in npm} == {("a", "^1"), ("b", "2")}
    assert dl.is_dependency_file("gdpr_consent/package.json")
    assert dl.is_dependency_file("requirements-nodeps.txt")
    assert not dl.is_dependency_file("gdpr_consent/node_modules/x/package.json")
    assert not dl.is_dependency_file("README.md")


def test_only_added_or_repinned_dependencies_are_checked(repo):
    (repo / "requirements.txt").write_text("requests==2.33.0\ngplpkg==1.0\n")
    findings = dl.run(repo)
    assert [f.dep.name for f in findings] == ["gplpkg"]
    assert findings[0].fails

    (repo / "requirements.txt").write_text("requests==2.34.0\n")
    findings = dl.run(repo)
    assert [(f.dep.name, f.dep.version, f.fails) for f in findings] == [("requests", "2.34.0", False)]


def test_new_files_and_base_revision(repo):
    (repo / "conda-requirements.txt").write_text("sirius-ms==5.8.6\n")
    (repo / "web").mkdir()
    (repo / "web" / "package.json").write_text(json.dumps({"dependencies": {"left-pad": "1"}}))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "deps")
    findings = {f.dep.name: f for f in dl.run(repo, base="HEAD~1")}
    assert findings["sirius-ms"].fails and findings["sirius-ms"].dep.ecosystem == "conda"
    assert not findings["left-pad"].fails


def test_accepted_entries_cover_their_license_only(repo):
    (repo / "requirements.txt").write_text("requests==2.33.0\nmplpkg==1\nnolicense==1\n")
    policy = {"accepted": {
        "mplpkg": {"license": "MPL-2.0", "reason": "file-level copyleft"},
        "nolicense": {"license": "MIT", "reason": "LICENSE file in the wheel"},
    }}
    (repo / dl.POLICY_FILE).write_text(json.dumps(policy))
    findings = {f.dep.name: f for f in dl.run(repo)}
    assert not findings["mplpkg"].fails  # classifier name and SPDX id match
    assert not findings["nolicense"].fails
    assert findings["nolicense"].license == "MIT"

    LICENSES["mplpkg"] = "MPL-2.0 AND GPL-3.0-only"
    try:
        assert dl.run(repo)[0].fails  # a license added to the expression too
    finally:
        LICENSES["mplpkg"] = "Mozilla Public License 2.0 (MPL 2.0)"

    LICENSES["mplpkg"] = "GPL-3.0-only"
    try:
        assert dl.run(repo)[0].fails  # a changed license is asked about again
    finally:
        LICENSES["mplpkg"] = "Mozilla Public License 2.0 (MPL 2.0)"


def test_entry_without_license_accepts_nothing(repo):
    (repo / "requirements.txt").write_text("requests==2.33.0\nnolicense==1\n")
    (repo / dl.POLICY_FILE).write_text(json.dumps({"accepted": {"nolicense": {"reason": "looked"}}}))
    [finding] = dl.run(repo)
    assert finding.fails


def test_every_baseline_pin_counts(repo):
    text = "requests==2.33.0\ngplpkg==1 ; sys_platform=='win32'\ngplpkg==2 ; sys_platform!='win32'\n"
    (repo / "requirements.txt").write_text(text)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "pins")
    assert dl.run(repo) == []


def test_failed_lookup_warns_but_does_not_fail(repo, monkeypatch):
    monkeypatch.setattr(dl, "lookup", lambda dep: ("", True))
    (repo / "requirements.txt").write_text("requests==2.33.0\nnew==1\n")
    [finding] = dl.run(repo)
    assert finding.lookup_failed and not finding.fails
    assert "by hand" in finding.note


def test_render_names_attribution_and_the_policy_file(repo):
    (repo / "requirements.txt").write_text("requests==2.33.0\ngplpkg==1\n")
    text = dl.render(dl.run(repo))
    assert "About and licenses dialog" in text
    assert dl.POLICY_FILE in text
    assert "| `gplpkg` |" in dl.render(dl.run(repo), markdown=True)


def test_template_dependencies_need_no_new_decision(monkeypatch):
    """Every dependency the template ships passes with its policy file."""
    known = {"certifi": "Mozilla Public License 2.0 (MPL 2.0)", "streamlit-js-eval": ""}
    monkeypatch.setattr(dl, "lookup", lambda dep: (known.get(dep.name, "MIT"), False))
    findings = dl.run(ROOT, everything=True)
    assert findings and not [f.dep.name for f in findings if f.fails]


def run_hook(repo, file_path):
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(file_path)}, "cwd": str(repo)})
    # The hook imports utils from the project; point it at the template and
    # replace the network lookup through a sitecustomize-free shim.
    shim = repo / "shim.py"
    shim.write_text(
        "import runpy, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from utils import dependency_licenses as dl\n"
        f"L = {LICENSES!r}\n"
        "dl.lookup = lambda dep: (L.get(dep.name, 'MIT'), False)\n"
        f"runpy.run_path({str(ROOT / '.claude/hooks/dependency_licenses.py')!r}, run_name='__main__')\n"
    )
    out = subprocess.run(
        [sys.executable, str(shim)], input=payload, capture_output=True, text=True,
        env={"CLAUDE_PROJECT_DIR": str(ROOT), "PATH": "/usr/bin:/bin"}, check=True,
    )
    return json.loads(out.stdout) if out.stdout.strip() else None


def test_hook(repo):
    assert run_hook(repo, repo / "README.md") is None
    assert run_hook(repo, repo / "requirements.txt") is None  # unchanged

    (repo / "requirements.txt").write_text("requests==2.33.0\nleft-pad==1\n")
    out = run_hook(repo, repo / "requirements.txt")
    assert "left-pad" in out["hookSpecificOutput"]["additionalContext"]

    (repo / "requirements.txt").write_text("requests==2.33.0\ngplpkg==1\n")
    out = run_hook(repo, repo / "requirements.txt")
    assert out["decision"] == "block" and "gplpkg" in out["reason"]
