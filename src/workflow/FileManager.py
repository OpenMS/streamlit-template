import gzip
import shutil
import string
import random
import sqlite3

import pandas as pd
import pickle as pkl

from io import BytesIO
from pathlib import Path
from typing import Union, List

class FileManager:
    """
    Manages file paths for operations such as changing file extensions, organizing files
    into result directories, and handling file collections for processing tools. Designed
    to be flexible for handling both individual files and lists of files, with integration
    into a Streamlit workflow.

    Methods:
        get_files: Returns a list of file paths as strings for the specified files, optionally with new file type and results subdirectory.
        collect: Collects all files in a single list (e.g. to pass to tools which can handle multiple input files at once).
    """

    def __init__(
        self,
        workflow_dir: Path,
        cache_path: Path,
    ):
        """
        Initializes the FileManager object with a the current workflow results directory.
        """
        self.workflow_dir = workflow_dir

        # Setup Caching
        self.cache_path = cache_path
        Path(self.cache_path, 'files').mkdir(parents=True, exist_ok=True)
        self.cache_connection = sqlite3.connect(
            Path(self.cache_path, 'cache.db'), isolation_level=None
        )
        self.cache_cursor = self.cache_connection.cursor()
        self.cache_cursor.execute("""
                          CREATE TABLE IF NOT EXISTS stored_data (
                            id TEXT PRIMARY KEY
                          );
        """)
        self.cache_cursor.execute("""
                          CREATE TABLE IF NOT EXISTS stored_files (
                            id TEXT PRIMARY KEY
                          );
        """)

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
            while Path(self.workflow_dir, "results", name).exists():
                name = self._generate_random_code(4)
        path = Path(self.workflow_dir, "results", name)
        path.mkdir(exist_ok=True)
        return str(path)
    
    def _get_column_list(self, table_name: str) -> List[str]:
        """
        Get a list of columns in the table.

        Args:
            table_name (str): The name of the table.

        Returns:
            columns (List): The columns in the table.
        """
        self.cache_cursor.execute(f"PRAGMA table_info({table_name});")
        return [col[1] for col in self.cache_cursor.fetchall()]

    
    def _add_column(self, table_name: str, column_name: str) -> None:
        """
        Checks if a column is in the cache table and if it is not adds 
        it to the table.

        Args:
            table_name (str): The name of the table
            column_name (str): The name of the column
        """

        # Fetch list of columns
        columns = self._get_column_list(table_name)

        # Add column to table if it does not exist
        if column_name not in columns:
            self.cache_cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT;"
            )

    def _add_entry(self, table_name: str, dataset_id: str, 
                   column_name: str, path: str) -> None:
        """
        Adds an entry to the cache index.

        Args:
            table_name (str): The name of the table
            dataset_id (str): The name of the dataset the data is 
                attached to.
            column_name (str): The name of the column
            path (str): The path to be inserted
        """

        # Ensure column exists
        self._add_column(table_name, column_name)

        # Store reference
        self.cache_cursor.execute(f"""
            INSERT INTO {table_name} (id, {column_name})
            VALUES ("{dataset_id}", "{path}")
            ON CONFLICT(id) 
            DO UPDATE SET {column_name} = excluded.{column_name};
        """)

    def _store_data(self, dataset_id: str, name_tag: str, data) -> None:
        """
        Stores data as a cached file. Pandas DataFrames are stored as 
        parquet files, while all other data structures are stored as
        compressed pickle.
        Args:
            dataset_id (str): The name of the dataset the data is 
                attached to.
            name_tag (str): The name of the associated data structure.
            data: Any pickleable data structure.

        Returns:
            file_path (Path): The file path of the stored file.
        """
        
        path = Path(self.cache_path, 'files', dataset_id)
        path.mkdir(parents=True, exist_ok=True)
        
        # DataFrames are stored as apache parquet
        if isinstance(data, pd.DataFrame):
            path = Path(path, f"{name_tag}.pq")
            with open(path, 'wb') as f:
                data.to_parquet(f)
        # Other data structures are stored as compressed pickle
        else:
            path = Path(path, f"{name_tag}.pkl.gz")
            with gzip.open(path, 'wb') as f:
                pkl.dump(data, f)

        return path

    def store_data(self, dataset_id: str, name_tag: str, data) -> None:
        """
        Stores a given data structure.

        Args:
            dataset_id (str): The name of the dataset the data is 
                attached to.
            name_tag (str): The name of the associated data structure.
            data: Any pickleable data structure.
        """

        # Store datastructure as file
        data_path = self._store_data(dataset_id, name_tag, data)

        # Store reference in index
        self._add_entry('stored_data', dataset_id, name_tag, data_path)
        
    def store_file(self, dataset_id: str, name_tag: str, file: Path | BytesIO, 
                   remove: bool = True, file_name = None) -> None:
        """
        Stores a given file.

        Args:
            dataset_id (str): The name of the dataset the data is 
                attached to.
            name_tag (str): The name of the associated data structure.
            file (Path of File-Like): The file that should be stored.
            remove (bool): Wether or not the file should be removed
                after copying it.
            filetype (str): The file extension of the file. Only 
                neccessary if a file-like object is used as input.
        """

        # Define storage path
        if file_name is None:
            file_name = f"{name_tag}{file.suffix}"
        
        target_path = Path(
                self.cache_path, 'files', dataset_id, file_name
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Store file in path
        if isinstance(file, BytesIO):
            with open(target_path, 'wb') as f:
                f.write(file.getbuffer())
        else:
            file = Path(file)            
            shutil.copy(file, target_path)
            if remove:
                file.unlink()

        # Store reference in index
        self._add_entry('stored_files', dataset_id, name_tag, target_path)

    def get_results_list(self, name_tags: List[str], partial=False) -> List[str]:
        """
        Get all results that contain data for specified fields.

        Args:
            name_tags (List): the fields to be considered.
        """
        # Some columns might not have been created yet (or ever)..
        available_columns = (
            set(self._get_column_list('stored_data')) 
            | set(self._get_column_list('stored_files'))
        )
        name_tags = [n for n in name_tags if n in available_columns]
        if len(name_tags) == 0:
            return []
        
        # Fetch data
        selection_operator = 'OR' if partial else 'AND'
        selection_statement = (
            f" IS NOT NULL {selection_operator} ".join(name_tags)
            + " IS NOT NULL;"
        )
        self.cache_cursor.execute(f"""
            SELECT id
            FROM (
                SELECT sd.id AS id, sd.*, sf.*
                FROM stored_data sd
                LEFT JOIN stored_files sf ON sd.id = sf.id

                UNION

                SELECT sf.id AS id, sd.*, sf.*
                FROM stored_files sf
                LEFT JOIN stored_data sd ON sf.id = sd.id
            ) combined
            WHERE {selection_statement}
        """)

        return [row[0] for row in self.cache_cursor.fetchall()]
    
    def get_results(self, dataset_id, name_tags, partial=False):
        results = {}
        # Retrieve files as Path objects
        file_columns = self._get_column_list('stored_files')
        file_columns = [c for c in file_columns if c in name_tags]
        if len(file_columns) > 0:
            self.cache_cursor.execute(f"""
                SELECT {', '.join(file_columns)}
                FROM stored_files
                WHERE id = '{dataset_id}';
            """)
            result = self.cache_cursor.fetchone()
            for c, r in zip(file_columns, result):
                if r is None:
                    if partial:
                        continue
                    else:
                        raise KeyError(f"{c} does not exist for {dataset_id}")
                results[c] = Path(r)
        # Retrieve data as Python objects
        data_columns = self._get_column_list('stored_data')
        data_columns = [c for c in data_columns if c in name_tags]
        if len(data_columns) > 0:
            self.cache_cursor.execute(f"""
                SELECT {', '.join(data_columns)}
                FROM stored_data
                WHERE id = '{dataset_id}';
            """)
            result = self.cache_cursor.fetchone()
            for c, r in zip(data_columns, result):
                if r is None:
                    if partial:
                        continue
                    else:
                        raise KeyError(f"{c} does not exist for {dataset_id}")
                file_path = Path(r)
                if file_path.suffix == '.pq':
                    data = pd.read_parquet(file_path)
                else:
                    with gzip.open(file_path, 'rb') as f:
                        data = pkl.load(f)
                results[c] = data
        return results
    
    def result_exists(self, dataset_id, name_tag):
        
        # Check which table is correct
        if name_tag in self._get_column_list('stored_data'):
            table = 'stored_data'
        elif name_tag in self._get_column_list('stored_files'):
            table = 'stored_files'
        else:
            return False
        
        # Check if field value is set
        self.cache_cursor.execute(f"""
            SELECT {name_tag} 
            FROM {table} 
            WHERE id = '{dataset_id}' AND {name_tag} IS NOT NULL
        """)
        if self.cache_cursor.fetchone():
            return True
        return False

    def remove_results(self, dataset_id):
    
        # Remove references
        self.cache_cursor.execute(f"""
            DELETE FROM stored_data
            WHERE id = '{dataset_id}';
        """)
        self.cache_cursor.execute(f"""
            DELETE FROM stored_files
            WHERE id = '{dataset_id}';
        """)

        # Remove stored files
        shutil.rmtree(Path(self.cache_path, 'files', dataset_id))

    def clear_cache(self):
        shutil.rmtree(Path(self.cache_path, 'files'))
        Path(self.cache_path, 'files').mkdir()
        self.cache_cursor.execute(f"DROP TABLE IF EXISTS stored_data;")
        self.cache_cursor.execute(f"DROP TABLE IF EXISTS stored_files;")
        self.cache_cursor.execute("""
                          CREATE TABLE IF NOT EXISTS stored_data (
                            id TEXT PRIMARY KEY
                          );
        """)
        self.cache_cursor.execute("""
                          CREATE TABLE IF NOT EXISTS stored_files (
                            id TEXT PRIMARY KEY
                          );
        """)

