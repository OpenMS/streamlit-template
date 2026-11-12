"""Memory of a run: cgroup and /proc readers, the warning, and its places."""

from pathlib import Path

import pytest

from src.workflow import memory


@pytest.fixture
def fake_proc(tmp_path, monkeypatch):
    def setup(meminfo=None, v2_max=None, v2_current=None, v1_limit=None, v1_usage=None):
        files = {
            "MEMINFO": meminfo, "CGROUP_V2_MEMORY_MAX": v2_max,
            "CGROUP_V2_MEMORY_CURRENT": v2_current,
            "CGROUP_V1_MEMORY_LIMIT": v1_limit, "CGROUP_V1_MEMORY_USAGE": v1_usage,
        }
        for name, text in files.items():
            path = tmp_path / name
            if text is not None:
                path.write_text(text)
            monkeypatch.setattr(memory, name, path)
    return setup


MEMINFO = "MemTotal:       16000000 kB\nMemFree:  1000 kB\nMemAvailable:    8000000 kB\n"


@pytest.mark.parametrize("text, expected", [
    ("16Gi", 16 * 1024 ** 3), ("512Mi", 512 * 1024 ** 2), ("2G", 2 * 1000 ** 3),
    ("1048576", 1048576), ("1.5Gi", int(1.5 * 1024 ** 3)), ("", None), ("lots", None), (None, None),
])
def test_parse_quantity(text, expected):
    assert memory.parse_quantity(text) == expected


def test_no_cgroup_uses_meminfo(fake_proc):
    fake_proc(meminfo=MEMINFO)
    assert memory.cgroup_memory_limit() is None
    assert memory.memory_limit() == 16000000 * 1024
    assert memory.available_memory() == 8000000 * 1024


def test_cgroup_v2_limit_and_use(fake_proc):
    fake_proc(meminfo=MEMINFO, v2_max=str(4 * 1024 ** 3), v2_current=str(1024 ** 3))
    assert memory.memory_limit() == 4 * 1024 ** 3
    assert memory.available_memory() == 3 * 1024 ** 3


def test_cgroup_v2_unlimited(fake_proc):
    fake_proc(meminfo=MEMINFO, v2_max="max", v2_current="123")
    assert memory.cgroup_memory_limit() is None
    assert memory.available_memory() == 8000000 * 1024


def test_cgroup_v1_no_limit_is_huge_number(fake_proc):
    fake_proc(meminfo=MEMINFO, v1_limit=str(9223372036854771712), v1_usage="0")
    assert memory.cgroup_memory_limit() is None
    fake_proc(meminfo=MEMINFO, v1_limit=str(2 * 1024 ** 3), v1_usage=str(1024 ** 3))
    assert memory.available_memory() == 1024 ** 3


def test_nothing_readable(fake_proc):
    fake_proc()
    assert memory.memory_limit() is None
    assert memory.available_memory() is None


def test_worker_limit_online(fake_proc, monkeypatch):
    fake_proc(meminfo=MEMINFO)
    monkeypatch.setenv("WORKER_MEMORY_LIMIT", "16Gi")
    assert memory.run_memory(online=True) == (16 * 1024 ** 3, "the server that runs analyses")
    # Local runs on this computer, whatever the variable says
    assert memory.run_memory(online=False) == (8000000 * 1024, "this computer")
    monkeypatch.delenv("WORKER_MEMORY_LIMIT")
    assert memory.run_memory(online=True)[1] == "the server"


def test_warning():
    gb = 1000 ** 3
    assert memory.memory_warning(None, 8 * gb) is None
    assert memory.memory_warning(5 * gb, None) is None
    assert memory.memory_warning(7 * gb, 8 * gb) is None  # within the headroom
    text = memory.memory_warning(12 * gb, 8 * gb, "this computer", "Use fewer threads.")
    assert text.startswith("This analysis may need about 12.0 GB of memory, and this computer has 8.0 GB")
    assert text.endswith("Use fewer threads.")
    assert "850 MB" == memory.format_bytes(850 * 1000 ** 2)


def test_worker_logs_the_warning(monkeypatch):
    from src.workflow import tasks

    lines = []

    class Log:
        def log(self, msg, level=0):
            lines.append((msg, level))

    class Wf:
        def memory_estimate(self, params):
            return 100 * 1000 ** 3

        def memory_advice(self, params):
            return "Do less."

    monkeypatch.setattr(memory, "available_memory", lambda: 8 * 1000 ** 3)
    tasks._log_memory_warning(Wf(), {}, Log())
    assert lines and lines[0][0].startswith("WARNING: This analysis may need about 100.0 GB")
    assert lines[0][1] == 0

    class Broken(Wf):
        def memory_estimate(self, params):
            raise RuntimeError("no")

    lines.clear()
    tasks._log_memory_warning(Broken(), {}, Log())
    assert lines == []


def test_run_page_shows_the_warning(tmp_path):
    """The Run page of a workflow whose estimate does not fit warns above Start."""
    from streamlit.testing.v1 import AppTest

    page = tmp_path / "page.py"
    page.write_text(
        "import streamlit as st\n"
        "from src.common.common import page_setup\n"
        "page_setup()\n"
        "from src.workflow.WorkflowManager import WorkflowManager\n"
        "class Big(WorkflowManager):\n"
        "    def __init__(self):\n"
        "        super().__init__('Memory Check', st.session_state['workspace'])\n"
        "    def memory_estimate(self, params):\n"
        "        return 10 ** 15\n"
        "    def memory_advice(self, params):\n"
        "        return 'Pick fewer files.'\n"
        "Big().show_execution_section()\n"
    )
    at = AppTest.from_file(str(page), default_timeout=60)
    import json
    at.session_state["settings"] = json.loads(Path("settings.json").read_text())
    at.run()
    assert not at.exception
    warnings = [w.value for w in at.warning]
    assert any("may need about 1000000.0 GB" in w and "Pick fewer files." in w for w in warnings), warnings
