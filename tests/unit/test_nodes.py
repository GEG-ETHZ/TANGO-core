"""

    Description: unit test cases for pytest (https://docs.pytest.org/en/7.4.x/)

    Test cases:
    - testcase1: xxx

    Reference:
    - https://www.sciencedirect.com/science/article/pii/S0960148120318978?via%3Dihub

"""

import sys, os
import pytest
import yaml
from pathlib import Path
sys.path.append(os.path.join(str(Path(__file__).parent.parent.parent),'src'))

from tango.core.config import *
from tango.units.native import *
from tango.units.native.well import *
from tango.units.native.surface import *
from tango.utils import *


def get_specs(casename: str) -> None:
    examples_dir = os.path.join(str(Path(__file__).parent.parent.parent), 'examples')
    specs = load_from_yaml(os.path.join(examples_dir, f'{casename}.yml'))
    specs['common'] = specs['props'] | specs['surface'] | specs['schedule'] | specs['economic']
    return specs


id = 'test'
specs_CO2 = get_specs('testcase1')  # CO2
specs_H2O = get_specs('testcase4')  # H2O


def test_injection_well():

    unit = InjectionWellUnitNative(id, specs_CO2)
    unit.init_stream_interface(P=6.e6, T=295.15)
    unit.process_stream()
    assert unit.ppp == pytest.approx(12320526.240)
    assert unit.ttt == pytest.approx(347.14151104)

    unit = InjectionWellUnitNative(id, specs_H2O)
    unit.init_stream_interface(P=1.e5, T=295.15)
    unit.process_stream()
    assert unit.ppp == pytest.approx(24439888.119)
    assert unit.ttt == pytest.approx(302.99120246)


def test_reservoir():

    unit = ReservoirUnitNative(id, specs_CO2)
    unit.init_stream_interface(P=2.7579e+7, T=330.)
    unit._thermal_depletion()
    unit.process_stream()
    assert unit.ppp == pytest.approx(27578999.9)
    assert unit.ttt == pytest.approx(375.6035)

    unit = ReservoirUnitNative(id, specs_H2O)
    unit.init_stream_interface(P=2.7579e+7, T=330.)
    unit._thermal_depletion()
    unit.process_stream()
    assert unit.ppp == pytest.approx(27579000.0)
    assert unit.ttt == pytest.approx(375.65)


def test_production_well():

    unit = ProductionWellUnitNative(id, specs_CO2)
    unit.init_stream_interface(P=2.8e7, T=375.0)
    unit.process_stream()
    assert unit.ppp == pytest.approx(13913705.3614)
    assert unit.ttt == pytest.approx(337.876370365)

    unit = ProductionWellUnitNative(id, specs_H2O)
    unit.init_stream_interface(P=2.8e7, T=375.0)
    unit.process_stream()
    assert unit.ppp == pytest.approx(9180870.3324)
    assert unit.ttt == pytest.approx(367.11120669)

def test_surface():

    unit = SurfaceUnitCPGNative(id, specs_CO2)
    unit.init_state(P=1.0e7, T=330.)
    unit.process_stream()
    assert unit.outlet_fluid.P == pytest.approx(6053084.8456)
    assert unit.outlet_fluid.T == pytest.approx(295.150)

    unit = SurfaceUnitORCNative(id, specs_H2O)
    unit.init_state(P=1.0e7, T=330.)
    unit.process_stream()
    assert unit.ttt == pytest.approx(317.141317)
    assert unit.ppp == pytest.approx(9999899.413)


