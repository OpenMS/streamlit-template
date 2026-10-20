"""
Tests of the Svelte app's local server (server/), against the API the
frontend calls. The TOPP tools are the pyOpenMS stand-ins in fake_topp/, so
no OpenMS installation is needed.
"""

import json
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

FAKE_TOPP = Path(__file__).parent / "fake_topp"
WF = "/api/ws/test/wf/topp-workflow"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SVELTE_WORKSPACES_DIR", str(tmp_path / "workspaces"))
    monkeypatch.setenv("PATH", f"{FAKE_TOPP}{os.pathsep}{os.environ['PATH']}")
    from server.app import app

    return TestClient(app)


def params_file(tmp_path) -> dict:
    return json.loads((tmp_path / "workspaces" / "test" / "topp-workflow" / "params.json").read_text())


def test_workspaces_create_list_delete(client):
    assert client.post("/api/workspaces", json={"name": "a"}).status_code == 200
    assert "a" in client.get("/api/workspaces").json()["workspaces"]
    assert client.post("/api/workspaces", json={"name": "../evil"}).status_code == 400
    assert client.delete("/api/workspaces/a").status_code == 200
    assert "a" not in client.get("/api/workspaces").json()["workspaces"]


def test_demo_workspace_loads(client, tmp_path):
    demos = client.get("/api/workspaces").json()["demos"]
    assert demos, "example-data/workspaces should provide a demo"
    r = client.post("/api/workspaces/test/load-demo", json={"demo": demos[0]})
    assert r.status_code == 200
    assert any((tmp_path / "workspaces" / "test").iterdir())


def test_example_files_offered_then_replaced_by_upload(client):
    r = client.get(f"{WF}/files/mzML-files").json()
    assert r["only_example"] and len(r["files"]) == 4
    r = client.post(f"{WF}/files/mzML-files", files=[("files", ("mine.mzML", b"<mzML/>"))]).json()
    assert [f["name"] for f in r["files"]] == ["mine.mzML"]
    r = client.post(f"{WF}/files/mzML-files", files=[("files", ("notes.txt", b"x"))]).json()
    assert r["skipped"] == ["notes.txt"]


def test_local_files_referenced_without_copy(client, tmp_path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "a.mzML").write_text("<mzML/>")
    r = client.post(f"{WF}/files/mzML-files/local", json={"paths": [str(src)], "copy_files": False}).json()
    refs = [f for f in r["files"] if f["reference"]]
    assert [f["path"] for f in refs] == [str(src / "a.mzML")]
    r = client.delete(f"{WF}/files/mzML-files", params={"path": str(src / "a.mzML")}).json()
    assert not [f for f in r["files"] if f["reference"]]


def test_topp_parameters_store_only_non_defaults(client, tmp_path):
    cfg = client.get(f"{WF}/configure").json()
    ffm = cfg["items"][1]["items"][0]["schema"]
    assert ffm["available"]
    noise = next(p for p in ffm["params"] if p["key"] == "algorithm:common:noise_threshold_int")
    # custom_defaults from the spec is the effective default
    assert noise["value"] == noise["default"] == 1000.0
    # input/output files and the standard TOPP options are not offered
    keys = {p["key"] for p in ffm["params"]}
    assert not keys & {"in", "out", "threads", "log", "debug"}

    client.put(f"{WF}/topp/FeatureFinderMetabo", json={"values": {"algorithm:mtd:mass_error_ppm": 12}})
    stored = params_file(tmp_path)
    assert stored["FeatureFinderMetabo"] == {"algorithm:mtd:mass_error_ppm": 12.0}
    assert stored["_defaults"]["FeatureFinderMetabo"] == {"algorithm:common:noise_threshold_int": 1000.0}
    # setting it back to the default removes it again
    client.put(f"{WF}/topp/FeatureFinderMetabo", json={"values": {"algorithm:mtd:mass_error_ppm": 20.0}})
    assert "FeatureFinderMetabo" not in params_file(tmp_path)


def test_bool_parameters_stay_topp_strings(client, tmp_path):
    client.get(f"{WF}/configure")
    client.put(f"{WF}/topp/FeatureFinderMetabo", json={"values": {"algorithm:mtd:reestimate_mt_sd": False}})
    assert params_file(tmp_path)["FeatureFinderMetabo"]["algorithm:mtd:reestimate_mt_sd"] == "false"


def test_untouched_widgets_are_stored_with_their_defaults(client, tmp_path):
    client.get(f"{WF}/configure")
    stored = params_file(tmp_path)
    # execution() reads these keys unconditionally
    assert stored["mzML-files"] == [] and stored["run-python-script"] is False


def test_presets_and_reset(client, tmp_path):
    spec = client.get(WF).json()
    assert spec["presets"]
    name = spec["presets"][0]["name"]
    assert client.post(f"{WF}/presets/{name}").status_code == 200
    assert params_file(tmp_path)
    r = client.post(f"{WF}/params/reset").json()
    assert r["backup"].startswith("params.json.")


def test_unreadable_params_refuse_writes(client, tmp_path):
    client.get(f"{WF}/configure")
    path = tmp_path / "workspaces" / "test" / "topp-workflow" / "params.json"
    path.write_text("{not json")
    r = client.put(f"{WF}/params", json={"values": {"run-python-script": True}})
    assert r.status_code == 409
    assert path.read_text() == "{not json"


def test_workflow_runs_end_to_end(client, tmp_path):
    cfg = client.get(f"{WF}/files/mzML-files") and client.get(f"{WF}/configure").json()
    files = [o["value"] for o in cfg["items"][0]["state"]["options"]][:2]
    client.put(f"{WF}/params", json={"values": {"mzML-files": files}})
    assert client.post(f"{WF}/run").status_code == 200
    assert client.post(f"{WF}/run").status_code == 409  # already running
    for _ in range(240):
        st = client.get(f"{WF}/status", params={"level": "all", "lines": 0}).json()
        if not st["running"]:
            break
        time.sleep(0.5)
    assert st["outcome"] == "finished", st["log"]
    # TOPP command built from params.json, as run_topp does it
    assert "-algorithm:common:noise_threshold_int 1000.0" in st["log"]

    files = {f["path"] for f in client.get(f"{WF}/results/files").json()["files"]}
    assert "feature-linking/feature_matrix.tsv" in files
    page = client.get(f"{WF}/table", params={"path": "results/feature-linking/feature_matrix.tsv", "limit": 5, "sort": "mz"}).json()
    assert len(page["rows"]) == 5 and page["total"] > 5
    mzs = [r[3] for r in page["rows"]]
    assert mzs == sorted(mzs)
    z = client.post(f"{WF}/results/zip", json={"folders": ["feature-linking"]})
    assert z.status_code == 200 and z.content[:2] == b"PK"


def test_failed_workflow_is_reported(client):
    client.get(f"{WF}/configure")  # stores mzML-files = []
    client.post(f"{WF}/run")
    for _ in range(120):
        st = client.get(f"{WF}/status").json()
        if not st["running"]:
            break
        time.sleep(0.5)
    assert st["outcome"] == "error"
    assert "No mzML files selected" in st["log"]


def test_table_path_cannot_escape_workflow_dir(client):
    r = client.get(f"{WF}/table", params={"path": "../../../../etc/passwd"})
    assert r.status_code == 400


def test_toolbox(client):
    r = client.post("/api/tools/mz", json={"sequence": "PEPTIDE", "min_charge": 1, "max_charge": 2}).json()
    assert abs(r["charge_results"]["1"]["mz_ratio"] - 800.367) < 1e-3
    assert client.post("/api/tools/mz", json={"sequence": "PEPTIDEJ!"}).status_code == 400
    r = client.post("/api/tools/digest", json={"fasta": ">sp|P1|X d\nMKWVTFISLLLLFSSAYSRGVFRRDTHK"}).json()
    assert r["stats"]["total_peptides"] > 0
    r = client.post("/api/tools/isotope", json={"method": "formula", "value": "C6H12O6"}).json()
    assert abs(r["monoisotopic_mass"] - 180.0634) < 1e-3
    r = client.post("/api/tools/fragment", json={"sequence": "PEPTIDE", "ion_types": ["b", "y"], "charges": [1]}).json()
    assert len(r["fragments"]["rows"]) == 12


def test_mzml_viewer(client):
    client.post("/api/ws/test/mzml/example")
    files = client.get("/api/ws/test/mzml").json()["files"]
    name = files[0]["name"]
    ov = client.get(f"/api/ws/test/mzml/{name}/overview").json()
    assert ov["spectra"] and "1" in ov["chromatograms"]
    sp = client.get(f"/api/ws/test/mzml/{name}/spectrum/{ov['spectra'][0]['index']}").json()
    assert len(sp["mz"]) == len(sp["intensity"]) > 0
    pm = client.get(f"/api/ws/test/mzml/{name}/peakmap", params={"rt_bins": 50, "mz_bins": 50}).json()
    assert 0 < len(pm["rt"]) <= 2500 <= pm["total_peaks"]


def test_workspace_params_follow_default_parameters(client):
    p = client.get("/api/ws/test/params").json()
    assert p["example-x-dimension"] == 10
    p = client.put("/api/ws/test/params", json={"values": {"example-x-dimension": 3, "not-a-param": 1}}).json()
    assert p["example-x-dimension"] == 3 and "not-a-param" not in p
