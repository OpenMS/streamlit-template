"""The example workflow's own setting min-files drops features found in too few files."""
from types import SimpleNamespace

import pandas as pd

from src.Workflow import Workflow


def _table(path):
    pd.DataFrame({
        "metabolite": ["a", "b", "c"], "mz": [100.0, 200.0, 300.0], "rt": [10.0, 20.0, 30.0],
        "charge": [1, 1, 1], "quality": [0.5, 0.5, 0.5],
        "A.mzML": [1.0, 2.0, None], "B.mzML": [1.0, None, None], "C.mzML": [1.0, 3.0, 4.0],
    }).to_csv(path, sep="\t", index=False)


def test_keep_features_in_at_least_two_files(tmp_path):
    table = tmp_path / "feature_matrix.tsv"
    _table(table)
    logged = []
    wf = SimpleNamespace(logger=SimpleNamespace(log=logged.append))
    Workflow._keep_features_in(wf, table, 2)
    assert list(pd.read_csv(table, sep="\t")["metabolite"]) == ["a", "b"]
    assert "Kept 2 of 3" in logged[0]


def test_one_file_keeps_the_table_untouched(tmp_path):
    table = tmp_path / "feature_matrix.tsv"
    _table(table)
    before = table.read_text()
    Workflow._keep_features_in(SimpleNamespace(), table, 1)
    assert table.read_text() == before
