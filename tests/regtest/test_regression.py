import sys, os
from pathlib import Path
sys.path.append(os.path.join(str(Path(__file__).parent.parent.parent),'src'))
from tango.runner import Runner
import pandas as pd
import pytest
import shutil

examples_dir = os.path.join(str(Path(__file__).parent.parent.parent),'examples')


def run(fname) -> None:
    runner = Runner(['-f', fname, '--test'])
    runner.start()


def get_val(fname) -> float:
    df = pd.read_csv(fname.replace('.yml', '.econ.csv'))
    return df['LCOE'].iloc[0]


def rmFiles(fname):
    files = [fname.replace('.yml', '.log'),
             fname.replace('.yml', '.econ.csv'),
             fname.replace('.yml', '.smry.csv')]
    for file in files:
        if os.path.exists(file):
            os.remove(file)


def testcase1():
    fname = os.path.join(examples_dir, 'testcase1.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(1.061605)
    rmFiles(fname)


def testcase2():
    fname = os.path.join(examples_dir, 'testcase2.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(0.249816)
    rmFiles(fname)


def testcase3():
    fname = os.path.join(examples_dir, 'testcase3.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(0.6980055)
    rmFiles(fname)
