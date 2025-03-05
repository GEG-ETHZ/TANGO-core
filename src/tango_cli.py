import sys
import logging
from datetime import datetime
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

from tango.runner import Runner
from tango.utils import *

EXPIRATION_DATE = datetime(2025, 12,31)

class Tango:

    def __init__(self,
                 args: list):
        args = parse_args(args)
        set_logger(args)
        self.runner = Runner(args.input_file)


    def execute(self) -> None:
        self.runner.start()


if __name__ == '__main__':

    current_date = datetime.now()

    if current_date > EXPIRATION_DATE:
        logging.info("This executable has expired. Please contact the developer for an updated version.")
        sys.exit()

    tango = Tango(sys.argv[1:])

    tango.execute()

