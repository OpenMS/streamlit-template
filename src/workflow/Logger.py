from pathlib import Path

class Logger:
    """
    A simple logging class for writing messages to a log file. This class is designed
    to append messages to a log file in the current workflow directory, facilitating
    easy tracking of events, errors, or other significant occurrences in processes called
    during workflow execution.

    Attributes:
        log_file (Path): The file path of the log file where messages will be written.
    """
    def __init__(self, workflow_dir: Path) -> None:
        self.workflow_dir = workflow_dir
        self.log_file = Path(self.workflow_dir, "log.txt")

    def log(self, message: str) -> None:
        """
        Appends a given message to the log file, followed by two newline characters
        for readability. This method ensures that each logged message is separated
        for clear distinction in the log file.

        Args:
            message (str): The message to be logged to the file.
        """
        # Write the message to the log file.
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"{message}\n\n")
