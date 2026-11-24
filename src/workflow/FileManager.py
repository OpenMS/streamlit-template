import gzip
import pickle as pkl
import random
import re
import shutil
import sqlite3
import string
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import List, Union

# Tables of the result index: one row per dataset, one column per result.
_TABLES = ("stored_data", "stored_files")
# Columns of an index table that are not results.
_INTERNAL_COLUMNS = ("id", "display_name")
# A result name becomes a column name. Kept to these characters so it can be
# quoted safely; FLASHApp's names ("deconv_dfs", "anno_annotated", ...) fit.
_NAME_TAG = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def _unlink_if_link(path: Path) -> None:
    """
    Remove ``path`` when it is a link, before a result is written there.

    A workspace started from a demo links the demo's large result files
    (``copy_demo_workspace``). Writing through such a link would change the
    demo every new workspace shares, so a result written again replaces the
    link with a file of the workspace's own.
    """
    if path.is_symlink():
        path.unlink()


def _quote(name: str) -> str:
    """A result name as an SQL identifier; refuses names it cannot quote."""
    if not isinstance(name, str) or not _NAME_TAG.match(name):
        raise ValueError(
            f"Result name {name!r}: use letters, digits, '_', '-' or '.'."
        )
    return f'"{name}"'


def _result_name(name: str) -> str:
    """A name a result may be stored under: quotable and not an index column."""
    _quote(name)
    if name in _INTERNAL_COLUMNS:
        raise ValueError(f"Result name {name!r} is reserved.")
    return name


def _staged(path: Path) -> Path:
    """A private file beside ``path`` to write before it replaces ``path``."""
    return path.with_name(f".{path.name}.{random.getrandbits(32):08x}.tmp")


def _is_polars(data) -> bool:
    module = type(data).__module__ or ""
    return module.startswith("polars")


def _is_pandas(data) -> bool:
    module = type(data).__module__ or ""
    return module.startswith("pandas") and type(data).__name__ == "DataFrame"


def cache_path_for(workflow_dir, share_cache: bool = False) -> Path:
    """The result store's folder: ``<workflow_dir>/cache``, or
    ``<workspace>/cache`` for a workflow that shares it."""
    workflow_dir = Path(workflow_dir)
    return Path(workflow_dir.parent if share_cache else workflow_dir, "cache")


class FileManager:
    """
    Paths of a workflow's files, and the store of its results.

    **Paths.** ``get_files`` changes the type of input paths, puts them in a
    subdirectory of the results directory and collects them for tools that
    take many inputs at once.

    **Result store** (optional; nothing is created until it is used). A
    workflow keeps what it parsed from its tools' output under a dataset id
    (one run or one input file) and a result name: ``store_data`` writes a
    polars or pandas DataFrame (or a polars LazyFrame) as parquet and any other
    object as a compressed pickle, ``store_file`` copies a file; both land in
    ``<cache_path>/files/<dataset_id>/`` and are listed in the SQLite index
    ``<cache_path>/cache.db``. ``get_results`` reads them back (pandas by
    default, a polars LazyFrame with ``use_polars``, a pyarrow dataset with
    ``use_pyarrow``), ``get_results_list`` lists the datasets that hold given
    results, ``result_exists`` / ``get_result_path`` look one up,
    ``rename_dataset`` / ``get_display_name`` keep a name a user gave it, and
    ``remove_results`` / ``clear_cache`` delete them, together with the
    folders ``extra_cache_dirs`` names (caches an app builds from them).

    The object pickles (a queued run gets it): the SQLite connection is
    dropped and opened again on first use.
    """

    def __init__(
        self,
        workflow_dir: Path,
        results_dir: Path = None,
        *,
        cache_path: Path = None,
    ):
        """
        Args:
            workflow_dir (Path): The workflow directory.
            results_dir (Path, optional): Where ``set_results_dir`` creates its
                subdirectories. Defaults to ``<workflow_dir>/results``; a
                multi-run workflow points it at the current run.
            cache_path (Path, optional): Where the result store keeps its
                files and index. Defaults to ``<workflow_dir>/cache``; a
                workflow with ``share_cache = True`` gets ``<workspace>/cache``.
        """
        self.workflow_dir = workflow_dir
        self.results_dir = Path(results_dir or Path(workflow_dir, "results"))
        self.cache_path = Path(
            cache_path if cache_path is not None else Path(workflow_dir, "cache")
        )
        self._connection = None
        self._cursor = None

    # ------------------------------------------------------------------
    # SQLite index, opened on first use
    # ------------------------------------------------------------------

    def _connect_to_sql(self) -> None:
        Path(self.cache_path, "files").mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            Path(self.cache_path, "cache.db"), isolation_level=None
        )
        self._cursor = self._connection.cursor()
        self._create_tables()

    def _create_tables(self) -> None:
        for table in _TABLES:
            self._cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY);"
            )
            self._add_column(table, "display_name")

    @property
    def cache_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connect_to_sql()
        return self._connection

    @property
    def cache_cursor(self) -> sqlite3.Cursor:
        if self._cursor is None:
            self._connect_to_sql()
        return self._cursor

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_connection"] = None
        state["_cursor"] = None
        return state

    def __setstate__(self, state):
        state.setdefault("_connection", None)
        state.setdefault("_cursor", None)
        self.__dict__.update(state)

    # Callables ``(cache_path, dataset_id) -> Path | None`` naming folders an
    # app builds from stored results (viewer caches, for example), deleted
    # with them: ``remove_results`` passes the dataset, ``clear_cache`` None
    # (the folder of every dataset). An app appends to it where it defines
    # those caches: ``FileManager.cache_dir_hooks.append(my_dirs)``.
    cache_dir_hooks: list = []

    def extra_cache_dirs(self, dataset_id: str = None) -> List[Path]:
        """
        Folders deleted with a dataset's results (``dataset_id``) or with the
        whole store (None): those ``cache_dir_hooks`` name. A subclass may
        override it instead.
        """
        dirs = []
        for hook in self.cache_dir_hooks:
            path = hook(self.cache_path, dataset_id)
            if path is not None:
                dirs.append(Path(path))
        return dirs

    def get_files(
        self,
        files: Union[List[Union[str, Path]], Path, str, List[List[str]]],
        set_file_type: str = None,
        set_results_dir: str = None,
        collect: bool = False,
    ) -> Union[List[str], List[List[str]]]:
        """
        Returns a list of file paths as strings for the specified files.
        Otionally sets or changes the file extension for all files to the
        specified file type and changes the directory to a new subdirectory
        in the workflow results directory.

        Args:
            files (Union[List[Union[str, Path]], Path, str, List[List[str]]]): The list of file
            paths to change the type for.
            set_file_type (str): The file extension to set for all files.
            set_results_dir (str): The name of a subdirectory in the workflow
            results directory to change to. If "auto" or "" a random name will be generated.
            collect (bool): Whether to collect all files into a single list. Will return a list
            with a single entry, which is a list of all files. Useful to pass to tools which
            can handle multiple input files at once.

        Returns:
            Union[List[str], List[List[str]]]: The (modified) files list.
        """
        # Handle input single string
        if isinstance(files, str):
            files = [files]
        # Handle input single Path object, can be directory or file
        elif isinstance(files, Path):
            if files.is_dir():
                files = [str(f) for f in files.iterdir()]
            else:
                files = [str(files)]
        # Handle input list
        elif isinstance(files, list) and files:
            # Can have one entry of strings (e.g. if has been collected before by FileManager)
            if isinstance(files[0], list):
                files = files[0]
            # Make sure ever file path is a string
            files = [str(f) for f in files if isinstance(f, Path) or isinstance(f, str)]
        # Raise error if no files have been detected
        if not files:
            raise ValueError(
                f"No files found, can not set file type **{set_file_type}**, results_dir **{set_results_dir}** and collect **{collect}**."
            )
        # Set new file type if required
        if set_file_type is not None:
            files = self._set_type(files, set_file_type)
        # Set new results subdirectory if required
        if set_results_dir is not None:
            if set_results_dir == "auto":
                set_results_dir = ""
            files = self._set_dir(files, set_results_dir)
        # Collect files into a single list if required
        if collect:
            files = [files]
        return files

    def _set_type(self, files: List[str], set_file_type: str) -> List[str]:
        """
        Sets or changes the file extension for all files in the collection to the
        specified file type.

        Args:
            files (List[str]): The list of file paths to change the type for.
            set_file_type (str): The file extension to set for all files.

        Returns:
            List[str]: The files list with new type.
        """

        def change_extension(file_path, new_ext):
            return Path(file_path).with_suffix("." + new_ext)

        for i in range(len(files)):
            if isinstance(files[i], list):  # If the item is a list
                files[i] = [
                    str(change_extension(file, set_file_type)) for file in files[i]
                ]
            elif isinstance(files[i], str):  # If the item is a string
                files[i] = str(change_extension(files[i], set_file_type))
        return files

    def _set_dir(self, files: List[str], subdir_name: str) -> List[str]:
        """
        Sets the subdirectory within the results directory to store files. If the
        subdirectory name is 'auto' or empty, generates a random subdirectory name.
        Warns and overwrites if the subdirectory already exists.

        Args:
            files (List[str]): The list of file paths to change the type for.
            subdir_name (str): The name of the subdirectory within the results directory.

        Returns:
            List[str]: The files list with new directory.
        """
        if not subdir_name:
            subdir_name = self._create_results_sub_dir(subdir_name)
        else:
            subdir_name = self._create_results_sub_dir(subdir_name)

        def change_subdir(file_path, subdir):
            return Path(subdir, Path(file_path).name)

        for i in range(len(files)):
            if isinstance(files[i], list):  # If the item is a list
                files[i] = [str(change_subdir(file, subdir_name)) for file in files[i]]
            elif isinstance(files[i], str):  # If the item is a string
                files[i] = str(change_subdir(files[i], subdir_name))
        return files

    def _generate_random_code(self, length: int) -> str:
        """Generate a random code of the specified length.

        Args:
            length (int): Length of the random code.

        Returns:
            str: Random code of the specified length.
        """
        # Define the characters that can be used in the code
        # Includes both letters and numbers
        characters = string.ascii_letters + string.digits

        # Generate a random code of the specified length
        random_code = "".join(random.choice(characters) for _ in range(length))

        return random_code

    def _create_results_sub_dir(self, name: str = "") -> str:
        """
        Creates a subdirectory within the results directory for storing files. If the
        name is not specified or empty, generates a random name for the subdirectory.

        Args:
            name (str, optional): The desired name for the subdirectory.

        Returns:
            str: The path to the created subdirectory as a string.
        """
        # create a directory (e.g. for results of a TOPP tool) within the results directory
        # if name is empty string, auto generate a name
        if not name:
            name = self._generate_random_code(4)
            # make sure the subdirectory does not exist in results yet
            while Path(self.results_dir, name).exists():
                name = self._generate_random_code(4)
        path = Path(self.results_dir, name)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    # ------------------------------------------------------------------
    # Result store
    # ------------------------------------------------------------------

    def _get_column_list(self, table_name: str) -> List[str]:
        """The columns of an index table (``id``, ``display_name``, results)."""
        if table_name not in _TABLES:
            raise ValueError(f"Unknown table {table_name!r}")
        self.cache_cursor.execute(f"PRAGMA table_info({table_name});")
        return [col[1] for col in self.cache_cursor.fetchall()]

    def _add_column(self, table_name: str, column_name: str) -> None:
        """Adds a result column to an index table unless it is there."""
        if column_name in self._get_column_list(table_name):
            return
        try:
            self._cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {_quote(column_name)} TEXT;"
            )
        except sqlite3.OperationalError:
            # Another store sharing this cache may have added it meanwhile
            if column_name not in self._get_column_list(table_name):
                raise

    def _add_entry(
        self, table_name: str, dataset_id: str, column_name: str, path
    ) -> None:
        """Records where a dataset's result is stored (relative to the cache)."""
        self._add_column(table_name, column_name)
        column = _quote(column_name)
        self.cache_cursor.execute(
            f"INSERT INTO {table_name} (id, {column}) VALUES (?, ?) "
            f"ON CONFLICT(id) DO UPDATE SET {column} = excluded.{column};",
            (str(dataset_id), str(path)),
        )

    def _check_owner(self, dataset_id: str, path: Path, table: str, name_tag: str) -> None:
        """Refuses to write ``path`` when another result of the dataset is stored there."""
        rel = str(self._relative(path))
        for other in _TABLES:
            columns = [c for c in self._get_column_list(other) if c not in _INTERNAL_COLUMNS]
            if not columns:
                continue
            row = self._row(other, dataset_id, columns)
            for column, value in zip(columns, row or ()):
                if value == rel and (other, column) != (table, name_tag):
                    raise ValueError(
                        f"{path.name} already holds the result {column!r} of {dataset_id}."
                    )

    def _dataset_dir(self, dataset_id: str) -> Path:
        dataset_id = str(dataset_id)
        if not dataset_id or Path(dataset_id).name != dataset_id or dataset_id in (".", ".."):
            raise ValueError(f"Dataset id {dataset_id!r} is not a folder name.")
        return Path(self.cache_path, "files", dataset_id)

    def _relative(self, path: Path) -> Path:
        # The folder is resolved, not the file: a payload may be a link into
        # a demo workspace, and it is named by where it sits in this cache.
        path = Path(path)
        return Path(path.parent.resolve(), path.name).relative_to(self.cache_path.resolve())

    def _store_data(self, dataset_id: str, name_tag: str, data, row_group_size=None) -> Path:
        """
        Writes ``data`` below the dataset's folder: polars and pandas
        DataFrames and polars LazyFrames as parquet, anything else as a
        compressed pickle. Returns the path written.
        """
        _result_name(name_tag)
        folder = self._dataset_dir(dataset_id)
        folder.mkdir(parents=True, exist_ok=True)
        is_table = (
            _is_polars(data) and type(data).__name__ in ("DataFrame", "LazyFrame")
        ) or _is_pandas(data)
        path = Path(folder, f"{name_tag}.pq" if is_table else f"{name_tag}.pkl.gz")
        self._check_owner(dataset_id, path, "stored_data", name_tag)
        # Write a private file first and replace the result only once it is
        # complete, so a failed write keeps the earlier result readable (and
        # never writes through a link into a demo workspace).
        tmp = _staged(path)
        try:
            if _is_polars(data) and type(data).__name__ == "LazyFrame":
                # Stream to disk unless bounded row groups are asked for:
                # sink_parquet does not take row_group_size on every polars.
                if row_group_size is None:
                    data.sink_parquet(tmp)
                else:
                    data.collect().write_parquet(tmp, row_group_size=row_group_size)
            elif _is_polars(data) and is_table:
                data.write_parquet(tmp, row_group_size=row_group_size)
            elif is_table:
                with open(tmp, "wb") as f:
                    data.to_parquet(f, row_group_size=row_group_size)
            else:
                with gzip.open(tmp, "wb") as f:
                    pkl.dump(data, f)
            tmp.replace(path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return path

    def store_data(self, dataset_id: str, name_tag: str, data, row_group_size=None) -> None:
        """
        Stores a result of a dataset.

        Args:
            dataset_id (str): The dataset (a run, an input file) it belongs to.
            name_tag (str): The name of the result.
            data: A polars or pandas DataFrame, a polars LazyFrame (stored as
                parquet) or any other picklable object.
            row_group_size (int, optional): Row group size of a parquet file.
        """
        data_path = self._store_data(dataset_id, name_tag, data, row_group_size=row_group_size)
        self._add_entry("stored_data", dataset_id, name_tag, self._relative(data_path))

    @contextmanager
    def parquet_sink(self, dataset_id: str, name_tag: str):
        """
        Yields a path to write a parquet result to. On a clean exit the file
        is moved into place and recorded; on an exception it is removed and
        nothing is recorded.
        """
        _result_name(name_tag)
        final_path = Path(self._dataset_dir(dataset_id), f"{name_tag}.pq")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        self._check_owner(dataset_id, final_path, "stored_data", name_tag)
        tmp_path = _staged(final_path)
        try:
            yield tmp_path
            _unlink_if_link(final_path)
            tmp_path.replace(final_path)
            self._add_entry("stored_data", dataset_id, name_tag, self._relative(final_path))
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def store_file(
        self,
        dataset_id: str,
        name_tag: str,
        file: Union[Path, str, BytesIO],
        remove: bool = True,
        file_name: str = None,
    ) -> None:
        """
        Stores a file as a result of a dataset.

        Args:
            dataset_id (str): The dataset it belongs to.
            name_tag (str): The name of the result.
            file (Path | str | file-like): The file, or its content (an
                uploaded file, a ``BytesIO``).
            remove (bool): Remove the file after copying it.
            file_name (str, optional): The name to store it under; by default
                the result name with the file's extension.
        """
        _result_name(name_tag)
        if file_name is None:
            # File-like objects have no `suffix`; Streamlit's UploadedFile
            # carries the original file name in `name`.
            if isinstance(file, (str, Path)):
                suffix = Path(file).suffix
            else:
                suffix = Path(getattr(file, "name", "") or "").suffix
            file_name = f"{name_tag}{suffix}"

        file_name = str(file_name)
        if (
            not file_name
            or file_name in (".", "..")
            or Path(file_name).name != file_name
            or "\\" in file_name
        ):
            raise ValueError(f"File name {file_name!r} is not a plain file name.")
        target_path = Path(self._dataset_dir(dataset_id), file_name)
        self._check_owner(dataset_id, target_path, "stored_files", name_tag)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        tmp = _staged(target_path)
        try:
            if hasattr(file, "getbuffer"):
                with open(tmp, "wb") as f:
                    f.write(file.getbuffer())
            else:
                shutil.copy(Path(file), tmp)
            tmp.replace(target_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        if remove and not hasattr(file, "getbuffer"):
            Path(file).unlink()
        self._add_entry("stored_files", dataset_id, name_tag, self._relative(target_path))

    def get_results_list(self, name_tags: List[str], partial: bool = False) -> List[str]:
        """
        The datasets that hold all (``partial`` False) or any of the results
        named, sorted by id. Names no dataset holds are left out.
        """
        if isinstance(name_tags, str):
            name_tags = [name_tags]
        available = set(self._get_column_list("stored_data")) | set(
            self._get_column_list("stored_files")
        )
        name_tags = [n for n in name_tags if n in available and n not in _INTERNAL_COLUMNS]
        if not name_tags:
            return []
        data_columns = set(self._get_column_list("stored_data"))
        file_columns = set(self._get_column_list("stored_files"))

        def has(name):
            parts = []
            if name in data_columns:
                parts.append(f"sd.{_quote(name)} IS NOT NULL")
            if name in file_columns:
                parts.append(f"sf.{_quote(name)} IS NOT NULL")
            return "(" + " OR ".join(parts) + ")"

        where = (" OR " if partial else " AND ").join(has(n) for n in name_tags)
        self.cache_cursor.execute(
            f"""
            SELECT ids.id FROM (
                SELECT id FROM stored_data UNION SELECT id FROM stored_files
            ) ids
            LEFT JOIN stored_data sd ON sd.id = ids.id
            LEFT JOIN stored_files sf ON sf.id = ids.id
            WHERE {where}
            ORDER BY ids.id
            """
        )
        return [row[0] for row in self.cache_cursor.fetchall()]

    def _row(self, table: str, dataset_id: str, columns: List[str]):
        self.cache_cursor.execute(
            f"SELECT {', '.join(_quote(c) for c in columns)} FROM {table} WHERE id = ?",
            (str(dataset_id),),
        )
        return self.cache_cursor.fetchone()

    def get_results(
        self,
        dataset_id: str,
        name_tags: List[str],
        partial: bool = False,
        use_pyarrow: bool = False,
        use_polars: bool = False,
    ) -> dict:
        """
        Reads results of a dataset: ``{name: value}``. A stored file comes back
        as its ``Path``; a parquet result as a pandas DataFrame, a polars
        LazyFrame (``use_polars``) or a pyarrow dataset (``use_pyarrow``);
        anything else as the object stored. A result stored for other
        datasets but not this one raises ``KeyError`` unless ``partial``; a
        name no dataset holds is left out.
        """
        name_tags = [name_tags] if isinstance(name_tags, str) else list(name_tags)
        return self._results(
            dataset_id, name_tags, _TABLES, partial, use_pyarrow, use_polars
        )

    def _results(
        self, dataset_id, name_tags, tables, partial, use_pyarrow=False, use_polars=False
    ) -> dict:
        # A name may be a stored file of one dataset and data of another:
        # look in every table before calling a result missing.
        found, known = {}, set()
        for table in tables:
            columns = [
                c for c in self._get_column_list(table)
                if c in name_tags and c not in _INTERNAL_COLUMNS
            ]
            if not columns:
                continue
            known.update(columns)
            row = self._row(table, dataset_id, columns) or (None,) * len(columns)
            for column, value in zip(columns, row):
                if value is not None and column not in found:
                    found[column] = (table, Path(self.cache_path, value))
        if not partial:
            missing = sorted(known - set(found))
            if missing:
                raise KeyError(f"{missing[0]} does not exist for {dataset_id}")
        return {
            column: path if table == "stored_files" else self._read(
                path, use_pyarrow=use_pyarrow, use_polars=use_polars
            )
            for column, (table, path) in found.items()
        }

    @staticmethod
    def _read(path: Path, use_pyarrow: bool = False, use_polars: bool = False):
        if path.suffix == ".pq":
            if use_pyarrow:
                import pyarrow.dataset as ds

                return ds.dataset(path, format="parquet")
            if use_polars:
                import polars as pl

                return pl.scan_parquet(path)
            import pandas as pd

            return pd.read_parquet(path)
        with gzip.open(path, "rb") as f:
            return pkl.load(f)

    def get_all_files_except(self, dataset_id: str, exclude_tags: List[str]) -> dict:
        """Every stored file of a dataset (``{name: Path}``) but those named."""
        names = [
            c for c in self._get_column_list("stored_files")
            if c not in _INTERNAL_COLUMNS and c not in exclude_tags
        ]
        return self._results(dataset_id, names, ("stored_files",), partial=True)

    def result_exists(self, dataset_id: str, name_tag: str) -> bool:
        """Whether a dataset holds the result named."""
        return self.get_result_path(dataset_id, name_tag) is not None

    def get_result_path(self, dataset_id: str, name_tag: str):
        """Where a result (parquet, pickle or file) is stored, or None."""
        if name_tag in _INTERNAL_COLUMNS:
            return None
        for table in _TABLES:
            if name_tag not in self._get_column_list(table):
                continue
            row = self._row(table, dataset_id, [name_tag])
            if row is not None and row[0] is not None:
                return Path(self.cache_path, row[0])
        return None

    def remove_results(self, dataset_id: str) -> None:
        """Deletes a dataset's results, its index rows and its extra caches."""
        for table in _TABLES:
            self.cache_cursor.execute(f"DELETE FROM {table} WHERE id = ?", (str(dataset_id),))
        shutil.rmtree(self._dataset_dir(dataset_id), ignore_errors=True)
        for path in self.extra_cache_dirs(dataset_id):
            shutil.rmtree(path, ignore_errors=True)

    def clear_cache(self) -> None:
        """Deletes every stored result, the index and the extra caches."""
        shutil.rmtree(Path(self.cache_path, "files"), ignore_errors=True)
        Path(self.cache_path, "files").mkdir(parents=True, exist_ok=True)
        for path in self.extra_cache_dirs(None):
            shutil.rmtree(path, ignore_errors=True)
        for table in _TABLES:
            self.cache_cursor.execute(f"DROP TABLE IF EXISTS {table};")
        self._create_tables()

    def get_display_name(self, dataset_id: str) -> str:
        """The name a user gave the dataset, else its id."""
        for table in _TABLES:
            self.cache_cursor.execute(
                f"SELECT display_name FROM {table} WHERE id = ? AND display_name IS NOT NULL",
                (str(dataset_id),),
            )
            row = self.cache_cursor.fetchone()
            if row and row[0]:
                return row[0]
        return dataset_id

    def rename_dataset(self, dataset_id: str, new_display_name: str) -> bool:
        """
        Gives a dataset a display name (1 to 100 characters, trimmed).
        False when the name is empty or too long.
        """
        if not new_display_name or not new_display_name.strip():
            return False
        if len(new_display_name) > 100:
            return False
        new_display_name = new_display_name.strip()
        for table in _TABLES:
            self.cache_cursor.execute(
                f"UPDATE {table} SET display_name = ? WHERE id = ?",
                (new_display_name, str(dataset_id)),
            )
        return True
