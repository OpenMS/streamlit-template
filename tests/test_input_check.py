"""
Input check of mzML and FASTA files (src/workflow/input_check.py).

The module is Streamlit-free, so it is imported directly.
"""
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.workflow.input_check import (  # noqa: E402
    check_inputs,
    clear_cache,
    inspect_file,
    param_files,
    summarize,
    unusable,
)

EXAMPLE = Path(PROJECT_ROOT, "example-data", "mzML")


def _mzml(spectra: str, count: int, closed: bool = True) -> str:
    text = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<indexedmzML xmlns="http://psi.hupo.org/ms/mzml">\n'
        '<mzML><run id="r">\n'
        f'<spectrumList count="{count}" defaultDataProcessingRef="dp">\n'
        f"{spectra}"
        "</spectrumList></run></mzML>\n"
    )
    return text + ("</indexedmzML>\n" if closed else "")


def _spectrum(level: int) -> str:
    return (
        '<spectrum index="0" id="scan=1" defaultArrayLength="0">'
        f'<cvParam cvRef="MS" accession="MS:1000511" name="ms level" value="{level}"/>'
        "</spectrum>\n"
    )


def test_example_mzml_counts_spectra_and_ms2():
    pool = inspect_file(EXAMPLE / "Pool.mzML")
    assert pool.status == "ok"
    assert pool.counts["spectra"] == 799
    assert pool.counts["ms2"] == 1
    assert pool.summary == "799 spectra, MS2 present"

    blank = inspect_file(EXAMPLE / "Blank.mzML")
    assert blank.status == "ok"
    assert blank.summary.endswith("MS1 only")
    # A workflow that needs MS2 refuses the MS1-only file
    strict = inspect_file(EXAMPLE / "Blank.mzML", require_ms2=True)
    assert strict.status == "unusable"
    assert strict.errors == ["no MS2 spectra"]


def test_truncated_mzml_is_unusable(tmp_path):
    src = EXAMPLE / "Pool.mzML"
    cut = tmp_path / "cut.mzML"
    data = src.read_bytes()
    cut.write_bytes(data[: len(data) // 2])
    report = inspect_file(cut)
    assert not report.usable
    assert report.errors[0].startswith("cut off")
    # The count from the header is still reported
    assert report.counts["spectra"] == 799


def test_not_an_mzml(tmp_path):
    fake = tmp_path / "notes.mzML"
    fake.write_text("hello, this is a text file\n")
    assert inspect_file(fake).errors == ["not an mzML file"]

    empty = tmp_path / "empty.mzML"
    empty.write_bytes(b"")
    assert inspect_file(empty).errors == ["empty file"]

    gz = tmp_path / "packed.mzML"
    gz.write_bytes(b"\x1f\x8b\x08\x00rest")
    assert "gzip" in inspect_file(gz).errors[0]

    folder = tmp_path / "dir.mzML"
    folder.mkdir()
    assert inspect_file(folder).errors == ["is a folder, not a file"]

    assert inspect_file(tmp_path / "missing.mzML").errors == ["file not found"]


def test_mzml_without_spectra(tmp_path):
    f = tmp_path / "none.mzML"
    f.write_text(_mzml("", 0))
    assert inspect_file(f).errors == ["no spectra"]


def test_mzml_msn_found_after_first_chunk(tmp_path):
    # MS2 spectra beyond the 4 MB read size are still found
    f = tmp_path / "late.mzML"
    filler = _spectrum(1) * 60000
    f.write_text(_mzml(filler + _spectrum(2), 60001))
    assert f.stat().st_size > 4 * 1024 * 1024
    report = inspect_file(f, require_ms2=True)
    assert report.usable
    assert report.counts == {"spectra": 60001, "chromatograms": 0, "ms2": 1}


def test_fasta_counts_and_decoys(tmp_path):
    f = tmp_path / "db.fasta"
    f.write_text(
        ">sp|P1|A_HUMAN first\nPEPTIDEK\nAAAR\n"
        ">sp|P2|B_HUMAN\nMKLV\n"
        ">DECOY_sp|P1|A_HUMAN\nKEDITPEP\n"
    )
    report = inspect_file(f)
    assert report.status == "ok"
    assert report.counts == {"entries": 3, "decoys": 1, "duplicates": 0}
    assert report.summary == "3 proteins (1 decoys)"


def test_fasta_unusable(tmp_path):
    dup = tmp_path / "dup.fasta"
    dup.write_text(">P1\nAAA\n>P2\nCCC\n>P1 again\nDDD\n")
    assert inspect_file(dup).errors == ["1 duplicate accession (P1)"]

    empty = tmp_path / "empty.fa"
    empty.write_text("")
    assert inspect_file(empty).errors == ["empty file"]

    blank_lines = tmp_path / "blank.fa"
    blank_lines.write_text("\n\n")
    assert inspect_file(blank_lines).errors == ["no entries"]

    text = tmp_path / "text.fasta"
    text.write_text("PEPTIDE\n>P1\nAAA\n")
    assert "does not start" in inspect_file(text).errors[0]

    binary = tmp_path / "bin.fasta"
    binary.write_bytes(b">P1\nAA\x00\x01\n")
    assert "binary" in inspect_file(binary).errors[0]

    no_acc = tmp_path / "noacc.fasta"
    no_acc.write_text(">\nAAA\n>P2\nCCC\n")
    assert inspect_file(no_acc).errors == ["1 entry without an accession"]


def test_fasta_warnings(tmp_path):
    f = tmp_path / "warn.fasta"
    f.write_bytes(
        b"\xef\xbb\xbf>P1\nPEPtidek\n>P2\n>P3\nAC1DE\n; comment\n>P4\nMKV\r\n"
    )
    report = inspect_file(f)
    assert report.usable
    assert report.status == "warning"
    assert report.counts["entries"] == 4
    assert report.warnings == [
        "starts with a byte-order mark",
        "1 entry without a sequence",
        "lowercase residues in 1 entry",
        "characters that are not residues (1) in 1 entry",
    ]


def test_unchecked_types_and_helpers(tmp_path):
    raw = tmp_path / "x.raw"
    raw.write_bytes(b"\x01")
    fasta = tmp_path / "db.fasta"
    fasta.write_text(">P1\nAAA\n")
    reports = check_inputs([raw, EXAMPLE / "Pool.mzML", fasta, tmp_path / "gone.mzML"])
    assert [r.status for r in reports] == ["unchecked", "ok", "ok", "unusable"]
    assert [r.name for r in unusable(reports)] == ["gone.mzML"]
    assert summarize(reports) == "2 mzML, 1 FASTA"
    assert summarize(reports[:1]) is None
    assert reports[3].describe() == "gone.mzML: file not found"

    params = {
        "mzML-files": [str(EXAMPLE / "Pool.mzML"), str(tmp_path / "gone.mzML")],
        "fasta": str(fasta),
        "threshold": 5,
        "label": "not a file.mzML",
    }
    assert param_files(params) == [str(EXAMPLE / "Pool.mzML"), str(fasta)]


def test_cache_follows_file_changes(tmp_path):
    clear_cache()
    f = tmp_path / "db.fasta"
    f.write_text(">P1\nAAA\n")
    assert inspect_file(f).counts["entries"] == 1
    f.write_text(">P1\nAAA\n>P2\nCCC\n")
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 10**9))
    assert inspect_file(f).counts["entries"] == 2
    shutil.rmtree(tmp_path)
