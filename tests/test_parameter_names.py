"""Display names for TOPP parameters from parameter-names.json."""
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.workflow import parameter_names as pn


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    # A later write within the same mtime tick must still be read
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    return path


def test_name_and_help(tmp_path):
    f = write(
        tmp_path / "names.json",
        {
            "_comment": "ignored",
            "FLASHDeconv": {
                "SD:tol": "Mass tolerance (ppm)",
                "SD:min_charge": {"name": "Lowest charge", "help": "Below it, no charge."},
                "SD:max_charge": {"help": "no name: ignored"},
                "SD:min_mass": "  ",
                "SD:max_mass": {"name": None, "help": "null name: ignored"},
                "SD:tol_ppm": {"name": 5},
            },
        },
    )
    assert pn.display_name("FLASHDeconv", "SD:tol", path=f) == {
        "name": "Mass tolerance (ppm)",
        "help": None,
    }
    assert pn.display_name("FLASHDeconv", "SD:min_charge", path=f) == {
        "name": "Lowest charge",
        "help": "Below it, no charge.",
    }
    assert pn.display_name("FLASHDeconv", "SD:max_charge", path=f) is None
    assert pn.display_name("FLASHDeconv", "SD:min_mass", path=f) is None
    assert pn.display_name("FLASHDeconv", "SD:max_mass", path=f) is None
    assert pn.display_name("FLASHDeconv", "SD:tol_ppm", path=f) is None
    assert pn.display_name("FLASHTnT", "SD:tol", path=f) is None
    assert pn.display_name("_comment", "x", path=f) is None


def test_instance_entry_wins_and_falls_back_to_tool(tmp_path):
    f = write(
        tmp_path / "names.json",
        {
            "IDFilter": {"score:psm": "PSM score cutoff", "best:n_peptide_hits": "Hits per spectrum"},
            "IDFilter-strict": {"score:psm": "Strict PSM score cutoff"},
        },
    )
    assert pn.display_name("IDFilter", "score:psm", "IDFilter-strict", path=f)["name"] == (
        "Strict PSM score cutoff"
    )
    assert pn.display_name("IDFilter", "best:n_peptide_hits", "IDFilter-strict", path=f)[
        "name"
    ] == "Hits per spectrum"
    assert pn.display_name("IDFilter", "score:psm", path=f)["name"] == "PSM score cutoff"


def test_missing_invalid_and_changed_file(tmp_path):
    missing = tmp_path / "none.json"
    assert pn.load_parameter_names(missing) == {}
    assert pn.display_name("Tool", "a", path=missing) is None

    f = tmp_path / "names.json"
    f.write_text("{not json", encoding="utf-8")
    assert pn.load_parameter_names(f) == {}
    write(f, ["a list"])
    assert pn.load_parameter_names(f) == {}

    # Edited while the app runs: the new names are read
    write(f, {"Tool": {"a": "First"}})
    assert pn.display_name("Tool", "a", path=f)["name"] == "First"
    write(f, {"Tool": {"a": "Second"}})
    assert pn.display_name("Tool", "a", path=f)["name"] == "Second"


def test_replacement_with_the_same_mtime_is_read(tmp_path):
    """A file copied in with its timestamp kept is still read again."""
    f = tmp_path / "names.json"
    f.write_text(json.dumps({"Tool": {"a": "First"}}), encoding="utf-8")
    mtime_ns = os.stat(f).st_mtime_ns
    assert pn.display_name("Tool", "a", path=f)["name"] == "First"
    f.write_text(json.dumps({"Tool": {"a": "A longer name"}}), encoding="utf-8")
    os.utime(f, ns=(mtime_ns, mtime_ns))
    assert pn.display_name("Tool", "a", path=f)["name"] == "A longer name"

def test_shipped_file_is_valid():
    """Every entry of the repository's file is a name or a {name, help} object."""
    data = json.loads(open(os.path.join(PROJECT_ROOT, pn.PARAMETER_NAMES_FILE), encoding="utf-8").read())
    assert isinstance(data, dict)
    for tool, names in data.items():
        if tool.startswith("_"):
            continue
        assert isinstance(names, dict), tool
        for parameter, entry in names.items():
            if parameter.startswith("_"):
                continue
            assert ":1:" not in parameter, (tool, parameter)
            if isinstance(entry, dict):
                name = entry.get("name")
                assert isinstance(name, str) and name.strip(), (tool, parameter)
                assert set(entry) <= {"name", "help"}, (tool, parameter)
            else:
                assert isinstance(entry, str) and entry.strip(), (tool, parameter)
