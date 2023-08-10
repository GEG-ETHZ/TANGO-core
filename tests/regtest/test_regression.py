"""

    Description: regression test cases for pytest

    Test cases:
    - testcase1: CPG (Doublet, green_field)
    - testcase2: CPG (x1 Inverted 5spot, green_field)
    - testcase3: CPG (x6 Inverted 5spot, brown_field)
    - testcase4: ORC (Doublet, green_field)
    - testcase5: ORC (x1 Inverted 5spot, green_field)
    - testcase6: AGS with CO2 (x1 horizontal well)
    - testcase7: AGS with Water (x1 horizontal well)

    Usage:
    - "pytest" to run all the cases
    - "pytest -k 'testcaseX'" to run a specific test

    Reference: https://docs.pytest.org/en/7.4.x/

"""

import sys, os
from pathlib import Path
sys.path.append(os.path.join(str(Path(__file__).parent.parent.parent),'src'))
from tango.tango_cli import TANGO
import pandas as pd
import pytest
import inspect


examples_dir = os.path.join(str(Path(__file__).parent.parent.parent),'examples')

def run(fname) -> None:
    tango = TANGO(['-f', fname])
    tango.run()


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
    assert get_val(fname) == pytest.approx(1.06321798)
    rmFiles(fname)


def testcase2():
    fname = os.path.join(examples_dir, 'testcase2.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(1.53049832)
    rmFiles(fname)


def testcase3():
    fname = os.path.join(examples_dir, 'testcase3.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(0.691471469)
    rmFiles(fname)


def testcase4():
    fname = os.path.join(examples_dir, 'testcase4.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(43.8631228)
    rmFiles(fname)


def testcase5():
    fname = os.path.join(examples_dir, 'testcase5.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(7.6254657502)
    rmFiles(fname)


def testcase6():
    fname = os.path.join(examples_dir, 'testcase6.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(124.7726806)
    rmFiles(fname)


def testcase7():
    fname = os.path.join(examples_dir, 'testcase7.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(138.636924494)
    rmFiles(fname)
