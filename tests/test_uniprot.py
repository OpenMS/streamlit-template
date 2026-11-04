"""
UniProt proteome search and FASTA download (src/workflow/uniprot.py) and its
widget (src/workflow/uniprot_ui.py), against a local stand-in for the UniProt
REST API that answers in UniProt's response format.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.workflow import uniprot  # noqa: E402

PROTEOMES = [
    {"id": "UP000000625", "proteomeType": "Reference and representative proteome",
     "taxonomy": {"scientificName": "Escherichia coli (strain K12)", "taxonId": 83333},
     "proteinCount": 4402},
    {"id": "UP000001410", "proteomeType": "Other proteome",
     "taxonomy": {"scientificName": "Escherichia coli O6:H1", "taxonId": 199310},
     "proteinCount": 5336},
]
FASTA = {
    False: "".join(f">tr|A{i:05d}|A{i}_ECOLI Protein {i}\nMKTAYIAKQR\n" for i in range(7)),
    True: ">sp|P0A7V8|RS4_ECOLI 30S ribosomal protein S4\nMARYLGPKLK\n"
          ">sp|P0A7W1|RS5_ECOLI 30S ribosomal protein S5\nMAHIEKQAGE\n",
}


@pytest.fixture
def server(monkeypatch):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body, content_type, headers=None):
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            seen.append((url.path, q))
            query = q.get("query", "")
            reviewed = "reviewed:true" in query
            if url.path == "/proteomes/search":
                found = [p for p in PROTEOMES if "proteome_type:1" not in query
                         or p["proteomeType"].startswith("Reference")]
                if "nothing" in query:
                    found = []
                self._send(json.dumps({"results": found}), "application/json")
            elif url.path == "/uniprotkb/search":
                n = FASTA[reviewed].count(">")
                self._send(json.dumps({"results": []}), "application/json",
                           {"x-total-results": str(n)})
            elif url.path == "/uniprotkb/stream":
                self._send(FASTA[reviewed], "text/plain")
            else:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"messages": ["bad request"]}).encode())

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(uniprot, "BASE_URL", f"http://127.0.0.1:{httpd.server_port}")
    yield SimpleNamespace(seen=seen, url=uniprot.BASE_URL)
    httpd.shutdown()


def test_queries():
    assert uniprot.proteome_query("9606") == \
        "(organism_id:9606 OR taxonomy_id:9606) AND (proteome_type:1)"
    assert uniprot.proteome_query(' Homo "sapiens" ', reference_only=False) == \
        '(organism_name:"Homo  sapiens")'
    with pytest.raises(ValueError):
        uniprot.proteome_query("  ")
    assert uniprot.fasta_query("UP000005640", True) == "(proteome:UP000005640) AND (reviewed:true)"
    assert uniprot.fasta_query("UP000005640", False) == "(proteome:UP000005640)"
    with pytest.raises(ValueError):
        uniprot.fasta_query("UP1) OR (reviewed:false", True)


def test_search_puts_reference_proteomes_first(server):
    found = uniprot.search_proteomes("Escherichia coli", reference_only=False)
    assert [p.upid for p in found] == ["UP000000625", "UP000001410"]
    assert found[0].is_reference and not found[1].is_reference
    assert found[0].label() == ("Escherichia coli (strain K12) · UP000000625 · taxon 83333 · "
                                "4,402 proteins · Reference and representative proteome")
    assert [p.upid for p in uniprot.search_proteomes("Escherichia coli")] == ["UP000000625"]


def test_download(server, tmp_path):
    query = uniprot.fasta_query("UP000000625", True)
    assert uniprot.count_proteins(query) == 2
    dest = tmp_path / "db.fasta"
    calls = []
    assert uniprot.download_fasta(query, dest, isoforms=True,
                                  progress=lambda b, n: calls.append(n)) == 2
    assert dest.read_text() == FASTA[True]
    assert calls[-1] == 2
    assert not list(tmp_path.glob(".*.part"))
    assert server.seen[-1][1]["includeIsoform"] == "true"


def test_errors_leave_no_file(server, tmp_path, monkeypatch):
    with pytest.raises(uniprot.UniProtError, match="400: bad request"):
        uniprot._get("/elsewhere", {})
    monkeypatch.setitem(FASTA, True, "")
    with pytest.raises(uniprot.UniProtError, match="no proteins"):
        uniprot.download_fasta(uniprot.fasta_query("UP000000625", True), tmp_path / "db.fasta")
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(uniprot, "BASE_URL", "http://127.0.0.1:9")
    with pytest.raises(uniprot.UniProtError, match="could not be reached"):
        uniprot.search_proteomes("9606")


def _widget_app(workflow_dir, base_url, fallback):
    def app(workflow_dir, base_url, fallback):
        import shutil
        from pathlib import Path
        from types import SimpleNamespace

        from src.workflow import uniprot
        from src.workflow.uniprot_ui import proteome_download

        uniprot.BASE_URL = base_url
        files_dir = Path(workflow_dir, "input-files", "fasta-file")
        files_dir.mkdir(parents=True, exist_ok=True)
        if not any(files_dir.iterdir()):
            shutil.copy(fallback, files_dir)
        params_file = Path(workflow_dir, "params.json")
        ui = SimpleNamespace(
            workflow_dir=Path(workflow_dir), params={},
            upload_targets={"fasta-file": {"name": "Database", "fallback": [fallback]}},
            parameter_manager=SimpleNamespace(params_file=params_file, param_prefix="wf-param-"),
        )
        proteome_download(ui, "fasta-file")

    return AppTest.from_function(app, args=(str(workflow_dir), base_url, str(fallback)))


def test_widget_downloads_and_selects(server, tmp_path):
    fallback = tmp_path / "example.fasta"
    fallback.write_text(">x\nM\n")
    wf = tmp_path / "wf"
    at = _widget_app(wf, server.url, fallback).run()
    assert not at.exception

    at.text_input(key="uniprot-fasta-file-text").input("nothing here")
    at.button[0].click().run()
    assert "No reference proteome found" in at.warning[0].value

    at.text_input(key="uniprot-fasta-file-text").input("Escherichia coli")
    at.checkbox(key="uniprot-fasta-file-reference").uncheck()
    at.button[0].click().run()
    assert at.selectbox(key="uniprot-fasta-file-pick").value == "UP000000625"
    assert "2 proteins" in at.caption[-1].value

    at.radio(key="uniprot-fasta-file-scope").set_value(at.radio[0].options[1]).run()
    assert "7 proteins" in at.caption[-1].value
    at.button(key="uniprot-fasta-file-download").click().run()
    assert not at.exception
    name = "UP000000625_Escherichia_coli_strain_K12_all.fasta"
    assert sorted(p.name for p in (wf / "input-files" / "fasta-file").iterdir()) == [name]
    assert "with 7 proteins" in at.success[0].value
    params = json.loads((wf / "params.json").read_text())
    assert params["fasta-file"] == str(wf / "input-files" / "fasta-file" / name)


def _choice_app(workflow_dir, base_url, selected):
    def app(workflow_dir, base_url, selected):
        from pathlib import Path
        from types import SimpleNamespace

        import streamlit as st

        from src.workflow import uniprot
        from src.workflow.uniprot_ui import database_choice

        uniprot.BASE_URL = base_url
        ui = SimpleNamespace(
            workflow_dir=Path(workflow_dir), params={"fasta-file": selected} if selected else {},
            upload_targets={},
            parameter_manager=SimpleNamespace(params_file=Path(workflow_dir, "params.json"),
                                              param_prefix="wf-param-"),
            select_input_file=lambda key, **kw: st.write(f"file picker for {key}"),
        )
        database_choice(ui, "fasta-file")

    return AppTest.from_function(app, args=(str(workflow_dir), base_url, selected))


def test_database_choice(server, tmp_path):
    at = _choice_app(tmp_path, server.url, None).run()
    assert at.radio[0].value == "Your file"
    assert at.markdown[0].value == "file picker for fasta-file"

    at.radio[0].set_value("UniProt proteome").run()
    assert not at.markdown
    at.text_input(key="uniprot-fasta-file-text").input("Escherichia coli")
    at.button[0].click().run()
    at.button(key="uniprot-fasta-file-download").click().run()
    assert not at.exception
    downloaded = tmp_path / "input-files" / "fasta-file" / "UP000000625_Escherichia_coli_strain_K12_swissprot.fasta"
    assert downloaded.is_file()

    # A workspace whose database came from UniProt opens on that source
    at = _choice_app(tmp_path, server.url, str(downloaded)).run()
    assert at.radio[0].value == "UniProt proteome"
    assert "Using `UP000000625_Escherichia_coli_strain_K12_swissprot.fasta`" in at.caption[0].value
