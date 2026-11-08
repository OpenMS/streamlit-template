"""The assistant's own analysis (src/agent_access/analysis.py): every step is
recorded the way a workflow's are, so the processing report says how each
result was made. A stand-in TOPP tool on PATH plays FeatureFinderMetabo."""

import json
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from src.agent_access import analysis
from src.agent_access.config import agent_settings
from src.agent_access.tools import ToolError, Tools
from src.workflow.processing_report import report_for, to_markdown

WF = "topp-workflow"
SETTINGS = {"app-name": "Test App", "version": "1.2.3", "online_deployment": False,
            "agent_access": {"enabled": True, "workflows": {WF: {"class": "src.Workflow:Workflow"}}}}

INI = """<?xml version="1.0" encoding="ISO-8859-1"?>
<PARAMETERS version="1.7.0">
  <NODE name="FeatureFinderMetabo" description="">
    <ITEM name="version" value="3.6.0" type="string" description="" />
    <NODE name="1" description="">
      <ITEM name="in" value="" type="input-file" description="Centroided mzML" supported_formats="*.mzML" />
      <ITEM name="out" value="" type="output-file" description="Features" supported_formats="*.featureXML" />
      <ITEM name="log" value="" type="string" description="" />
      <ITEM name="threads" value="1" type="int" description="" />
      <ITEM name="force" value="false" type="bool" description="Force" />
      <NODE name="algorithm" description="">
        <NODE name="common" description="">
          <ITEM name="noise_threshold_int" value="10.0" type="double" description="Noise" />
          <ITEM name="chrom_fwhm" value="5.0" type="double" description="FWHM" advanced="true" />
        </NODE>
      </NODE>
    </NODE>
  </NODE>
</PARAMETERS>
"""

TOOL = textwrap.dedent('''\
    #!{python}
    import sys, shutil, pathlib
    args = sys.argv[1:]
    if args[0] == "-write_ini":
        pathlib.Path(args[1]).write_text({ini!r}, encoding="utf-8")
        sys.exit(0)
    pathlib.Path({calls!r}).open("a").write(" ".join(args) + "\\n")
    out = args[args.index("-out") + 1]
    shutil.copy(args[args.index("-in") + 1], out)
    print("Progress of 'finding features': 100 %")
''')


@pytest.fixture
def tools_on_path(tmp_path, monkeypatch):
    bin_dir = Path(tmp_path, "openms-bin")
    bin_dir.mkdir()
    calls = Path(tmp_path, "calls.txt")
    for name, body in (("FeatureFinderMetabo", TOOL.format(python=sys.executable, ini=INI, calls=str(calls))),
                       ("FileInfo", "#!/bin/sh\nexit 0\n")):
        exe = Path(bin_dir, name)
        exe.write_text(body, encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return calls


@pytest.fixture
def workspace(tmp_path):
    ws = Path(tmp_path, "workspaces", "ws")
    inputs = Path(ws, WF, "input-files", "mzML-files")
    inputs.mkdir(parents=True)
    Path(inputs, "a.mzML").write_text("<mzML/>", encoding="utf-8")
    return ws


def _tools(ws):
    return Tools(Path.cwd(), ws, agent_settings(SETTINGS))


def test_an_analysis_records_every_step_with_why(tools_on_path, workspace):
    tools = _tools(workspace)
    begun = tools.call("begin_analysis", {"name": "Noise check", "question": "How many features?"})
    aid = begun["analysis"]
    assert begun["files"]["inputs"][f"{WF}/mzML-files"] == [f"{WF}/input-files/mzML-files/a.mzML"]

    described = tools.call("describe_tool", {"tool": "FeatureFinderMetabo"})
    assert [f["name"] for f in described["files"]] == ["in", "out"]
    assert [p["name"] for p in described["parameters"]] == ["algorithm:common:noise_threshold_int"]

    step = tools.call("run_tool", {
        "analysis": aid, "tool": "FeatureFinderMetabo",
        "inputs": {"in": f"{WF}/input-files/mzML-files/a.mzML"}, "outputs": {"out": "a.featureXML"},
        "params": {"algorithm:common:noise_threshold_int": 500.0, "force": True},
        "why": "Find features above a higher noise level", "wait": 60})
    assert step["ok"], step
    assert step["written"] == [{"file": "a.featureXML", "size": 7}]
    command = tools_on_path.read_text().split()
    assert "-force" in command and command[command.index("-force") + 1] != "true"
    assert command[command.index("-algorithm:common:noise_threshold_int") + 1] == "500.0"

    tools.call("save_figure", {"analysis": aid, "file": "counts.json",
                               "figure": {"data": [{"type": "bar", "x": ["a"], "y": [3]}], "layout": {}},
                               "made_from": ["a.featureXML"], "why": "Features per file"})
    tools.call("save_table", {"analysis": aid, "file": "counts.tsv", "columns": ["file", "features"],
                              "rows": [["a", 3]], "made_from": ["a.featureXML"]})
    assert tools.call("read_result", {"analysis": aid, "path": "counts.tsv"})["rows"] == [{"file": "a", "features": 3}]
    tools.call("finish_analysis", {"analysis": aid, "summary": "Three features."})

    md = tools.call("get_processing_report", {"analysis": aid})["markdown"]
    assert "Question | How many features?" in md
    assert "## Summary" in md and "Three features." in md
    assert "The AI assistant: Find features above a higher noise level" in md
    assert "FeatureFinderMetabo | 3.6.0" in md
    # The figure is traced back to the input file through the tool's output
    report = report_for(Path(workspace, analysis.ROOT), aid)
    calls = report["inputs"][0]["calls"]
    assert report["inputs"][0]["name"] == "a.mzML"
    assert [c["tool"] for c in calls] == ["FeatureFinderMetabo", "Figure by the AI assistant",
                                          "Table by the AI assistant"]


def test_a_step_checks_the_tool_and_its_files(tools_on_path, workspace):
    tools = _tools(workspace)
    aid = tools.call("begin_analysis", {"name": "x"})["analysis"]
    a_mzml = f"{WF}/input-files/mzML-files/a.mzML"
    with pytest.raises(ToolError, match="not an OpenMS tool"):
        tools.call("run_tool", {"analysis": aid, "tool": "bash", "outputs": {"out": "x"}})
    with pytest.raises(ToolError, match="stay in the analysis"):
        tools.call("run_tool", {"analysis": aid, "tool": "FeatureFinderMetabo",
                                "inputs": {"in": a_mzml}, "outputs": {"out": "../../x.featureXML"}})
    with pytest.raises(ToolError, match="No file"):
        tools.call("run_tool", {"analysis": aid, "tool": "FeatureFinderMetabo",
                                "inputs": {"in": "../../../etc/passwd"}, "outputs": {"out": "x"}})
    bad = tools.call("run_tool", {"analysis": aid, "tool": "FeatureFinderMetabo",
                                  "inputs": {"in": a_mzml}, "outputs": {"out": "x"},
                                  "params": {"log": "/tmp/elsewhere"}})
    assert not bad["ok"] and "is a file" in bad["error"]
    assert not tools_on_path.exists()


def test_an_analysis_built_on_a_run_starts_from_its_steps(tools_on_path, workspace):
    from src.workflow.RunManager import FINISHED, RunManager
    from src.workflow.progress import RunProgress
    wf_dir = Path(workspace, WF)
    runs = RunManager(wf_dir)
    run_id = runs.new_run("First run")
    run_dir = runs.run_dir(run_id)
    Path(run_dir, "results", "a.featureXML").write_text("<f/>", encoding="utf-8")
    progress = RunProgress(run_dir)
    step = progress.start_step("FeatureFinderMetabo", ["a.mzML"], provenance={
        "kind": "topp", "program": "FeatureFinderMetabo", "version": "3.6.0", "params": {},
        "io": [{"inputs": [str(Path(wf_dir, "input-files", "mzML-files", "a.mzML"))],
                "outputs": [str(Path(run_dir, "results", "a.featureXML"))]}]})
    progress.end_step(step)
    runs.finish(run_id, FINISHED)
    tools = _tools(workspace)
    begun = tools.call("begin_analysis", {"name": "More", "workflow": WF})
    result = f"{WF}/runs/{run_id}/results/a.featureXML"
    assert begun["based_on"] == "First run"
    assert begun["files"]["run_results"] == [result]
    aid = begun["analysis"]
    tools.call("save_table", {"analysis": aid, "file": "t.tsv", "columns": ["n"], "rows": [[1]],
                              "made_from": [result]})
    report = report_for(Path(workspace, analysis.ROOT), aid)
    assert report["run"]["follows"] == "First run"
    assert [c["tool"] for c in report["inputs"][0]["calls"]] == ["FeatureFinderMetabo", "Table by the AI assistant"]


def test_show_analysis_opens_the_analysis_page(tools_on_path, workspace):
    from src.agent_access import show
    tools = _tools(workspace)
    aid = tools.call("begin_analysis", {"name": "x"})["analysis"]
    tools.call("save_figure", {"analysis": aid, "file": "f.json", "figure": {"data": []}})
    with pytest.raises(ToolError, match="No result file"):
        tools.call("show_analysis", {"analysis": aid, "items": [{"file": "nope.json"}]})
    out = tools.call("show_analysis", {"analysis": aid, "items": [{"file": "f.json", "title": "F"}],
                                       "note": "Look at F"})
    assert out["shown"] == 1
    request = show.latest(workspace)
    assert request["analysis"] == aid and request["page_file"] == "content/assistant_analyses.py"
    assert analysis.shown(analysis.run_dir(workspace, aid))[0] == {
        "file": "f.json", "kind": "plot", "title": "F", "caption": ""}
