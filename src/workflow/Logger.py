from pathlib import Path

class Logger:
    """
    A simple logging class for writing messages to a log file. input_widgetThis class is designed
    to append messages to a log file in the current workflow directory, facilitating
    easy tracking of events, errors, or other significant occurrences in processes called
    during workflow execution.

    Attributes:
        log_file (Path): The file path of the log file where messages will be written.
    """
    def __init__(self, workflow_dir: Path) -> None:
        self.workflow_dir = workflow_dir

    def log(self, message: str, level: int = 0) -> None:
        """
        Appends a given message to the log file, followed by two newline characters
        for readability. This method ensures that each logged message is separated
        for clear distinction in the log file.

        Args:
            message (str): The message to be logged to the file.
            level (int, optional): The level of importance of the message. Defaults to 0.
        """
        log_dir = Path(self.workflow_dir, "logs")
        if not log_dir.exists():
            log_dir.mkdir()
        # Write the message to the log file.
        if level == 0:
            with open(Path(log_dir, "minimal.log"), "a", encoding="utf-8") as f:
                f.write(f"{message}\n\n")
        if level <= 1:
            with open(Path(log_dir, "commands-and-run-times.log"), "a", encoding="utf-8") as f:
                f.write(f"{message}\n\n")
        if level <= 2:
            with open(Path(log_dir, "all.log"), "a", encoding="utf-8") as f:
                f.write(f"{message}\n\n")
        # log_types = ["minimal", "commands and run times", "tool outputs", "all"]
        # for i, log_type in enumerate(log_types):
        #     with open(Path(log_dir, f"{log_type.replace(" ", "-")}.log"), "a", encoding="utf-8") as f:
        #         f.write(f"{message}\n\n")