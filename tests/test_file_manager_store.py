"""The result store of FileManager: storing, reading, listing, renaming and
removing a dataset's results, and what it leaves alone when it is unused."""

import pickle
from io import BytesIO
from pathlib import Path

import pytest

from src.workflow.FileManager import FileManager, cache_path_for

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")


def _fm(tmp_path):
    return FileManager(Path(tmp_path, "wf"))


def test_paths_only_create_no_store(tmp_path):
    fm = _fm(tmp_path)
    fm.get_files(["a.mzML"], set_file_type="featureXML")
    assert not Path(tmp_path, "wf", "cache").exists()


def test_keyword_cache_path_and_results_dir(tmp_path):
    fm = FileManager(Path(tmp_path, "wf"), Path(tmp_path, "r"), cache_path=Path(tmp_path, "c"))
    assert fm.results_dir == Path(tmp_path, "r")
    assert fm.cache_path == Path(tmp_path, "c")
    assert cache_path_for(Path(tmp_path, "ws", "wf")) == Path(tmp_path, "ws", "wf", "cache")
    assert cache_path_for(Path(tmp_path, "ws", "wf"), True) == Path(tmp_path, "ws", "cache")


def test_store_and_read_pandas_and_objects(tmp_path):
    fm = _fm(tmp_path)
    df = pd.DataFrame({"a": [1, 2]})
    fm.store_data("run1", "table", df)
    fm.store_data("run1", "settings", {"x": 1})
    out = fm.get_results("run1", ["table", "settings"])
    assert out["table"].equals(df)
    assert out["settings"] == {"x": 1}
    assert fm.result_exists("run1", "table")
    assert not fm.result_exists("run1", "other")
    assert fm.get_result_path("run1", "table").suffix == ".pq"
    assert fm.get_result_path("run2", "table") is None


def test_store_polars(tmp_path):
    pl = pytest.importorskip("polars")
    fm = _fm(tmp_path)
    fm.store_data("run1", "frame", pl.DataFrame({"a": [1, 2]}))
    fm.store_data("run1", "lazy", pl.DataFrame({"b": [3]}).lazy())
    out = fm.get_results("run1", ["frame", "lazy"], use_polars=True)
    assert out["frame"].collect()["a"].to_list() == [1, 2]
    assert out["lazy"].collect()["b"].to_list() == [3]


def test_store_file_path_and_buffer(tmp_path):
    fm = _fm(tmp_path)
    src = Path(tmp_path, "out.tsv")
    src.write_text("x")
    fm.store_file("run1", "out_tsv", src)
    assert not src.exists()
    buf = BytesIO(b"abc")
    buf.name = "upload.fasta"
    fm.store_file("run1", "db", buf)
    files = fm.get_results("run1", ["out_tsv", "db"])
    assert files["out_tsv"].name == "out_tsv.tsv" and files["out_tsv"].read_text() == "x"
    assert files["db"].name == "db.fasta" and files["db"].read_bytes() == b"abc"
    assert set(fm.get_all_files_except("run1", ["db"])) == {"out_tsv"}


def test_results_list_and_missing(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("b", "x", 1)
    fm.store_data("a", "x", 1)
    fm.store_data("a", "y", 2)
    assert fm.get_results_list(["x"]) == ["a", "b"]
    assert fm.get_results_list(["x", "y"]) == ["a"]
    assert fm.get_results_list(["x", "y"], partial=True) == ["a", "b"]
    assert fm.get_results_list(["never"]) == []
    with pytest.raises(KeyError):
        fm.get_results("b", ["y"])
    assert fm.get_results("b", ["y"], partial=True) == {}


def test_names_are_not_sql(tmp_path):
    fm = _fm(tmp_path)
    tricky = "it's \"quoted\"; DROP TABLE stored_data"
    fm.store_data(tricky.replace("/", ""), "x", 1)
    assert fm.get_results(tricky, ["x"]) == {"x": 1}
    with pytest.raises(ValueError):
        fm.store_data("run1", 'x"; DROP TABLE stored_data; --', 1)
    with pytest.raises(ValueError):
        fm.store_data("../escape", "x", 1)


def test_rename_and_display_name(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("run1", "x", 1)
    assert fm.get_display_name("run1") == "run1"
    assert fm.rename_dataset("run1", "  My run  ")
    assert fm.get_display_name("run1") == "My run"
    assert not fm.rename_dataset("run1", "   ")
    assert not fm.rename_dataset("run1", "x" * 101)


def test_remove_and_clear_with_hooks(tmp_path, monkeypatch):
    fm = _fm(tmp_path)

    def viewer_cache(cache_path, dataset_id):
        return Path(cache_path, "viewer", dataset_id or "")

    monkeypatch.setattr(FileManager, "cache_dir_hooks", [viewer_cache])
    fm.store_data("run1", "x", 1)
    fm.store_data("run2", "x", 1)
    Path(fm.cache_path, "viewer", "run1").mkdir(parents=True)
    Path(fm.cache_path, "viewer", "run2").mkdir(parents=True)
    fm.remove_results("run1")
    assert fm.get_results_list(["x"]) == ["run2"]
    assert not Path(fm.cache_path, "viewer", "run1").exists()
    assert Path(fm.cache_path, "viewer", "run2").exists()
    fm.clear_cache()
    assert fm.get_results_list(["x"]) == []
    assert not Path(fm.cache_path, "viewer").exists()
    fm.store_data("run3", "x", 1)
    assert fm.get_results_list(["x"]) == ["run3"]


def test_parquet_sink(tmp_path):
    fm = _fm(tmp_path)
    with fm.parquet_sink("run1", "t") as path:
        pd.DataFrame({"a": [1]}).to_parquet(path)
    assert fm.get_results("run1", ["t"])["t"]["a"].tolist() == [1]
    with pytest.raises(RuntimeError):
        with fm.parquet_sink("run1", "u") as path:
            path.write_bytes(b"half")
            raise RuntimeError
    assert not fm.result_exists("run1", "u")
    assert not path.exists()


def test_writing_replaces_a_link(tmp_path):
    shared = Path(tmp_path, "demo.pkl.gz")
    fm = _fm(tmp_path)
    fm.store_data("run1", "x", 1)
    stored = fm.get_result_path("run1", "x")
    stored.rename(shared)
    stored.symlink_to(shared)
    fm.store_data("run1", "x", 2)
    assert not stored.is_symlink()
    assert fm.get_results("run1", ["x"])["x"] == 2


def test_pickles_and_reconnects(tmp_path):
    # Other tests purge src.workflow.* from sys.modules; take the class that is
    # registered now, which pickle looks up by name.
    import importlib

    module = importlib.import_module("src.workflow.FileManager")
    fm = module.FileManager(Path(tmp_path, "wf"))
    fm.store_data("run1", "x", 1)
    copy = pickle.loads(pickle.dumps(fm))
    assert copy.get_results("run1", ["x"]) == {"x": 1}


def test_opens_a_store_written_before(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("run1", "x", {"a": 1})
    again = FileManager(Path(tmp_path, "wf"))
    assert again.get_results("run1", ["x"])["x"] == {"a": 1}
    assert again.get_results_list(["x"]) == ["run1"]


def test_one_name_as_a_string(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("run1", "layout", {"rows": 1})
    assert fm.get_results("run1", "layout") == {"layout": {"rows": 1}}
    assert fm.get_results_list("layout") == ["run1"]


def test_reserved_and_bad_names_rejected(tmp_path):
    fm = _fm(tmp_path)
    for name in ("id", "display_name"):
        with pytest.raises(ValueError):
            fm.store_data("run1", name, {"x": 1})
    src = Path(tmp_path, "a.tsv")
    src.write_text("x")
    for bad in ("../a.tsv", "sub/a.tsv", "..", "", "a\\b.tsv"):
        with pytest.raises(ValueError):
            fm.store_file("run1", "tsv", src, remove=False, file_name=bad)
    assert src.exists()


def test_file_and_data_cannot_share_a_path(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("run1", "table", pd.DataFrame({"a": [1]}))
    src = Path(tmp_path, "t.pq")
    src.write_text("not parquet")
    with pytest.raises(ValueError):
        fm.store_file("run1", "other", src, remove=False, file_name="table.pq")
    assert fm.get_results("run1", "table")["table"]["a"].tolist() == [1]


def test_same_name_as_data_and_file_in_two_datasets(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("run1", "out", {"x": 1})
    src = Path(tmp_path, "out.tsv")
    src.write_text("hello")
    fm.store_file("run2", "out", src)
    assert fm.get_results("run1", "out")["out"] == {"x": 1}
    assert Path(fm.get_results("run2", "out")["out"]).read_text() == "hello"
    with pytest.raises(KeyError):
        fm.get_results("run3", "out")


def test_failed_write_keeps_old_payload(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("run1", "obj", {"x": 1})

    class Bad:
        def __reduce__(self):
            raise RuntimeError("cannot pickle")

    with pytest.raises(RuntimeError):
        fm.store_data("run1", "obj", Bad())
    assert fm.get_results("run1", "obj")["obj"] == {"x": 1}
    folder = fm.get_result_path("run1", "obj").parent
    assert not [p for p in folder.iterdir() if p.name.endswith(".tmp")]


def test_all_files_except_leaves_data_out(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("run1", "obj", {"x": 1})
    src = Path(tmp_path, "a.tsv")
    src.write_text("a")
    fm.store_file("run1", "tsv", src)
    fm.store_data("run2", "tsv2", {"y": 2})
    files = fm.get_all_files_except("run1", [])
    assert set(files) == {"tsv"}


def _linked_demo(tmp_path):
    """A workspace whose dataset folder ``run1`` is a link to a demo's folder."""
    fm = _fm(tmp_path)
    fm.store_data("run1", "x", 1)
    stored = fm.get_result_path("run1", "x")
    demo = Path(tmp_path, "demo", "run1")
    demo.parent.mkdir()
    stored.parent.rename(demo)
    stored.parent.symlink_to(demo, target_is_directory=True)
    return fm, demo


def test_writing_into_a_linked_dataset_leaves_the_demo(tmp_path):
    fm, demo = _linked_demo(tmp_path)
    before = sorted(p.name for p in demo.iterdir())
    fm.store_data("run1", "x", 2)
    fm.store_data("run1", "y", 3)
    folder = fm.dataset_dir("run1")
    assert not folder.is_symlink()
    assert sorted(p.name for p in demo.iterdir()) == before
    assert fm.get_results("run1", ["x", "y"]) == {"x": 2, "y": 3}


def test_removing_a_linked_dataset_keeps_the_demo(tmp_path):
    fm, demo = _linked_demo(tmp_path)
    fm.remove_results("run1")
    assert demo.is_dir() and any(demo.iterdir())
    assert fm.get_results_list(["x"]) == []


def test_storing_a_file_onto_itself_keeps_it(tmp_path):
    fm = _fm(tmp_path)
    folder = fm.dataset_dir("run1")
    folder.mkdir(parents=True)
    target = Path(folder, "out.tsv")
    target.write_text("x")
    fm.store_file("run1", "out", target)
    assert Path(fm.get_results("run1", "out")["out"]).read_text() == "x"


def test_a_linked_index_is_copied_before_writing(tmp_path):
    demo = _fm(Path(tmp_path, "demo"))
    demo.store_data("run1", "x", 1)
    demo.cache_connection.close()
    demo_db = Path(demo.cache_path, "cache.db")
    before = demo_db.read_bytes()
    ws = Path(tmp_path, "ws", "wf", "cache")
    ws.mkdir(parents=True)
    Path(ws, "cache.db").symlink_to(demo_db)
    fm = FileManager(Path(tmp_path, "ws", "wf"))
    assert fm.get_results_list(["x"]) == ["run1"]
    fm.store_data("run2", "x", 2)
    assert not Path(ws, "cache.db").is_symlink()
    assert demo_db.read_bytes() == before


def test_a_file_replaces_an_object_of_the_same_name(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("r", "out", {"x": 1})
    old = fm.get_result_path("r", "out")
    src = Path(tmp_path, "out.tsv")
    src.write_text("t")
    fm.store_file("r", "out", src)
    assert Path(fm.get_results("r", "out")["out"]).read_text() == "t"
    assert not old.exists()
    fm.store_data("r", "out", {"y": 2})
    assert fm.get_results("r", "out")["out"] == {"y": 2}
    assert set(fm.get_all_files_except("r", [])) == set()


def test_storing_another_result_keeps_its_file(tmp_path):
    fm = _fm(tmp_path)
    src = Path(tmp_path, "a.tsv")
    src.write_text("a")
    fm.store_file("run1", "tsv", src)
    first = fm.get_result_path("run1", "tsv")
    fm.store_file("run2", "tsv", first)
    assert first.exists() and fm.get_result_path("run2", "tsv").read_text() == "a"


def test_repeated_reads_reuse_the_column_list(tmp_path, monkeypatch):
    fm = _fm(tmp_path)
    fm.store_data("run1", "table", pd.DataFrame({"a": [1]}))
    fm.get_results("run1", ["table"])
    calls = []
    real = FileManager._get_column_list

    def counting(self, table_name, fresh=False):
        cached = self._columns.get(table_name)
        before = cached
        out = real(self, table_name, fresh=fresh)
        if self._columns.get(table_name) is not before:
            calls.append(table_name)
        return out

    monkeypatch.setattr(FileManager, "_get_column_list", counting)
    for _ in range(5):
        fm.get_results("run1", ["table"])
        fm.get_results_list(["table"])
    assert calls == []


def test_own_new_result_is_seen_at_once(tmp_path):
    fm = _fm(tmp_path)
    fm.store_data("run1", "table", pd.DataFrame({"a": [1]}))
    assert fm.get_results_list(["table"]) == ["run1"]
    fm.store_data("run1", "other", {"x": 1})
    assert fm.get_results("run1", ["other"])["other"] == {"x": 1}
    assert fm.get_results_list(["other"]) == ["run1"]


def test_another_writer_is_seen_after_the_cache_expires(tmp_path, monkeypatch):
    # The module the class was defined in, also after other tests purged it.
    module_globals = FileManager._get_column_list.__globals__
    reader, writer = _fm(tmp_path), _fm(tmp_path)
    reader.store_data("run1", "table", pd.DataFrame({"a": [1]}))
    assert reader.get_results_list(["table"]) == ["run1"]
    writer.store_data("run2", "other", {"x": 2})
    monkeypatch.setitem(module_globals, "COLUMN_CACHE_SECONDS", 0.0)
    assert reader.get_results_list(["other"]) == ["run2"]
    assert reader.get_results("run2", ["other"])["other"] == {"x": 2}


def test_another_instance_clearing_the_cache_does_not_break_reads(tmp_path):
    reader, other = _fm(tmp_path), _fm(tmp_path)
    reader.store_data("run1", "table", pd.DataFrame({"a": [1]}))
    assert reader.get_results_list(["table"]) == ["run1"]
    assert reader.result_exists("run1", "table")
    other.clear_cache()
    assert reader.get_results_list(["table"]) == []
    assert not reader.result_exists("run1", "table")


def test_column_cache_is_not_pickled(tmp_path):
    import importlib

    module = importlib.import_module("src.workflow.FileManager")
    fm = module.FileManager(Path(tmp_path, "wf"))
    fm.store_data("run1", "table", pd.DataFrame({"a": [1]}))
    fm.get_results("run1", ["table"])
    assert fm._columns
    copy = pickle.loads(pickle.dumps(fm))
    assert copy._columns == {}
    assert copy.get_results("run1", ["table"])["table"]["a"].tolist() == [1]
