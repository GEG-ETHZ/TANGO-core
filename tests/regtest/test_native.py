"""

    Description: regression test cases for pytest (https://docs.pytest.org/en/7.4.x/)

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

    Reference:
    - https://www.sciencedirect.com/science/article/pii/S0960148120318978?via%3Dihub

"""

import sys, os
import pandas as pd
import pytest
from pathlib import Path
sys.path.append(os.path.join(str(Path(__file__).parent.parent.parent),'src'))

from tango.tango_cli import Tango


examples_dir = os.path.join(str(Path(__file__).parent.parent.parent),'examples')

def run(fname) -> None:
    tango = Tango(['-f', fname])
    tango.execute()


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
    assert get_val(fname) == pytest.approx(1.044581)
    rmFiles(fname)


def testcase2():
    fname = os.path.join(examples_dir, 'testcase2.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(1.522312)
    rmFiles(fname)


def testcase3():
    fname = os.path.join(examples_dir, 'testcase3.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(0.690270)
    rmFiles(fname)


def testcase4():
    fname = os.path.join(examples_dir, 'testcase4.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(38.007733714)
    rmFiles(fname)


def testcase5():
    fname = os.path.join(examples_dir, 'testcase5.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(6.271013322477)
    rmFiles(fname)


def testcase6():
    fname = os.path.join(examples_dir, 'testcase6.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(80.53108017884247)
    rmFiles(fname)


def testcase7():
    fname = os.path.join(examples_dir, 'testcase7.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(149.38633520088)
    rmFiles(fname)


def testcase8():
    fname = os.path.join(examples_dir, 'testcase8.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(116.29298550936)
    rmFiles(fname)

def testcase9():
    fname = os.path.join(examples_dir, 'timestep_irregular.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(1.044581)
    rmFiles(fname)

def testcase10():
    fname = os.path.join(examples_dir, 'timestep_linear.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(1.522312)
    rmFiles(fname)

def testcase11():
    fname = os.path.join(examples_dir, 'timestep_linear_csv.yml')
    run(fname)
    assert get_val(fname) == pytest.approx(0.690270)
    rmFiles(fname)
