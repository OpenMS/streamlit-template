"""The methods section written from a run's processing report."""

from pathlib import Path

from src.workflow.methods_text import OPENMS_REFERENCE, WEBAPPS_REFERENCE, methods_text
from src.workflow.processing_report import build_report, command_io
from src.workflow.progress import RunProgress, read_progress


def _step(progress, tool, io, params=None, version="3.6.0", kind="topp", ok=True, program=None):
    step = progress.start_step(
        tool,
        [Path(c["inputs"][0]).name for c in io],
        provenance={"kind": kind, "program": program or tool, "version": version,
                    "params": params or {}, "io": io},
    )
    for i in range(len(io)):
        progress.file_started(step, i)
        progress.file_finished(step, i, ok, returncode=0 if ok else 1)
    progress.end_step(step)


def _report(tmp_path, failed_last=False):
    progress = RunProgress(tmp_path)
    _step(progress, "FeatureFinderMetabo",
          command_io({"in": ["/d/A.mzML", "/d/B.mzML"], "out": ["/r/A.featureXML", "/r/B.featureXML"]}, 2),
          params={"algorithm:common:noise_threshold_int": "1000.0"})
    _step(progress, "FeatureLinkerUnlabeledKD",
          command_io({"in": [["/r/A.featureXML", "/r/B.featureXML"]], "out": ["/r/m.consensusXML"]}, 1))
    _step(progress, "export.py", command_io({"in": ["/r/m.consensusXML"], "out": ["/r/m.tsv"]}, 1),
          version=None, kind="python", ok=not failed_last)
    return build_report(read_progress(tmp_path), app_name="App", app_version="1.0", workflow="WF")


def _no_names(tool, parameter, instance=None):
    return None


def test_sentences_follow_the_tool_calls(tmp_path):
    text = methods_text(_report(tmp_path), names=_no_names)
    assert text.startswith("The 2 input files")
    assert ("The 2 input files (A.mzML and B.mzML) were processed with App 1.0, a web application "
            "built on the OpenMS WebApps framework [1] that runs the tools of OpenMS 3.6.0 [2].") in text
    assert ("First, FeatureFinderMetabo was run on each file, with "
            "algorithm:common:noise_threshold_int set to 1000.0.") in text
    assert "Then, FeatureLinkerUnlabeledKD was run on all files together, with default parameters." in text
    assert "Finally, the Python script export.py was run on all files together." in text
    assert f"\n\nReferences\n1. {WEBAPPS_REFERENCE}\n2. {OPENMS_REFERENCE}\n" in text


def test_parameter_display_names_are_used(tmp_path):
    names = {("FeatureFinderMetabo", "algorithm:common:noise_threshold_int"): "Noise threshold"}
    text = methods_text(_report(tmp_path), names=lambda t, p, i=None: (
        {"name": names[(t, p)]} if (t, p) in names else None))
    assert "with Noise threshold set to 1000.0." in text


def test_app_wording_and_references(tmp_path):
    settings = {"methods": {
        "reference": "App paper.",
        "tools": {"FeatureLinkerUnlabeledKD": {"text": "Features were linked across files with "
                                               "FeatureLinkerUnlabeledKD", "reference": "Linker paper."}},
    }}
    text = methods_text(_report(tmp_path), settings, names=_no_names)
    assert ("processed with App 1.0 [1], a web application built on the OpenMS WebApps framework [2] "
            "that runs the tools of OpenMS 3.6.0 [3].") in text
    assert "Then, features were linked across files with FeatureLinkerUnlabeledKD [4] on all files" in text
    assert text.endswith(f"1. App paper.\n2. {WEBAPPS_REFERENCE}\n3. {OPENMS_REFERENCE}\n4. Linker paper.\n")


def test_an_instance_uses_its_own_wording(tmp_path):
    progress = RunProgress(tmp_path)
    _step(progress, "CometAdapter (CometAdapter-TMT)",
          command_io({"in": ["/d/A.mzML"], "out": ["/r/A.idXML"]}, 1), program="CometAdapter")
    report = build_report(read_progress(tmp_path), app_name="App")
    settings = {"methods": {"tools": {"CometAdapter-TMT": {"text": "Spectra were searched for TMT peptides"}}}}
    text = methods_text(report, settings, names=_no_names)
    assert "The input file A.mzML was processed with App" in text
    assert "Spectra were searched for TMT peptides, with default parameters." in text


def test_steps_that_did_not_finish_are_left_out(tmp_path):
    text = methods_text(_report(tmp_path, failed_last=True), names=_no_names)
    assert "export.py" not in text
    assert "Then, FeatureLinkerUnlabeledKD" in text


def test_a_tool_of_another_openms_version_names_it(tmp_path):
    progress = RunProgress(tmp_path)
    _step(progress, "A", command_io({"in": ["/d/x.mzML"], "out": ["/r/x.a"]}, 1))
    _step(progress, "B", command_io({"in": ["/r/x.a"], "out": ["/r/x.b"]}, 1))
    _step(progress, "C", command_io({"in": ["/r/x.b"], "out": ["/r/x.c"]}, 1), version="3.5.0")
    text = methods_text(build_report(read_progress(tmp_path), app_name="App"), names=_no_names)
    assert "OpenMS 3.6.0" in text
    assert "Finally, C was run (version 3.5.0), with default parameters." in text


def test_no_finished_step_no_text(tmp_path):
    assert methods_text(build_report(read_progress(tmp_path))) == ""


def test_a_step_on_some_files_together_says_so(tmp_path):
    progress = RunProgress(tmp_path)
    files = [f"/d/{x}.mzML" for x in "ABCD"]
    _step(progress, "FeatureFinderMetabo",
          command_io({"in": files, "out": [f.replace(".mzML", ".fx") for f in files]}, 4))
    _step(progress, "FeatureLinkerUnlabeledKD",
          command_io({"in": [["/d/A.fx", "/d/B.fx"], ["/d/C.fx", "/d/D.fx"]],
                      "out": ["/r/ab.cx", "/r/cd.cx"]}, 2))
    text = methods_text(build_report(read_progress(tmp_path), app_name="App"), names=_no_names)
    assert "Then, FeatureLinkerUnlabeledKD was run on groups of up to 2 files together" in text


def test_a_methods_block_of_another_shape_is_ignored(tmp_path):
    report = _report(tmp_path)
    plain = methods_text(report, names=_no_names)
    for methods in (["CometAdapter"], "text", {"tools": ["x"]},
                    {"tools": {"FeatureLinkerUnlabeledKD": "Linked"}}, {"reference": 3}):
        assert methods_text(report, {"methods": methods}, names=_no_names) == plain
