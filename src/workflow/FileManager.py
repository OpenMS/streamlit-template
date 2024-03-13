from pathlib import Path
import string
import random
import shutil
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
    ):
        """
        Initializes the FileManager object with a the current workflow results directory.
        """
        self.workflow_dir = workflow_dir

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
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir()
        return str(path)
