import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from runner import Runner


if __name__ == '__main__':

    runner = Runner(sys.argv[1:])

    runner.start()
