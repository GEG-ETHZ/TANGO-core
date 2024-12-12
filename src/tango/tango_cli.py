import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from tango.runner import Runner
from tango.utils import *

class Tango:
    """
    Main class for executing the TANGO workflow.

    This class initializes the TANGO workflow runner and manages the execution process.

    Attributes:
        runner (Runner): An instance of the `Runner` class initialized with input file specifications.

    Methods:
        execute():
            Starts the workflow execution.
    """

    def __init__(self, args: list):
        """
        Initializes the Tango object by parsing arguments, setting up logging, and initializing the runner.

        Args:
            args (list): Command-line arguments passed to the script.

        Steps:
        - Parses the command-line arguments using `parse_args`.
        - Sets up logging configuration using `set_logger`.
        - Initializes the `Runner` with the input file specified in the arguments.
        """
        args = parse_args(args)
        set_logger(args)
        self.runner = Runner(args.input_file)

    def execute(self) -> None:
        """
        Executes the workflow by invoking the `start` method of the `Runner` instance.

        Returns:
            None
        """
        self.runner.start()


if __name__ == '__main__':
    """
    Entry point for the TANGO application.

    Steps:
    - Creates an instance of the `Tango` class with command-line arguments.
    - Executes the workflow using the `execute` method.

    Example:
        To run the script:
        ```
        python tango_cli.py -f path/to/input_file.yaml
        ```
    """
    tango = Tango(sys.argv[1:])
    tango.execute()


