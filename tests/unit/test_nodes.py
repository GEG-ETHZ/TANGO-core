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
from tango.models.native import *
from tango.models.native.well import *
from tango.models.native.surface import *
from tango.utils import *


def get_specs(casename: str) -> None:
    examples_dir = os.path.join(str(Path(__file__).parent.parent.parent), 'examples')
    data = load_from_yaml(os.path.join(examples_dir, f'{casename}.yml'))
    specs = dict()
    specs['common'] = data['graph']['specs'] | data['schedule'] | data['economic']
    for key in data['graph']['nodes'].keys():
        specs[data['graph']['nodes'][key]['type']] = data['graph']['nodes'][key]['specs']
    return specs


specs_CO2 = get_specs('testcase1')  # CO2
specs_H2O = get_specs('testcase4')  # H2O


def test_injection_well():

    model = InjectionWellModelNative(specs_CO2)
    model.init_state(P=6.e6, T=295.15)
    model.update()
    assert model.state.outlet_fluid.P == pytest.approx(12320526.240)
    assert model.state.outlet_fluid.T == pytest.approx(347.14151104)

    model = InjectionWellModelNative(specs_H2O)
    model.init_state(P=1.e5, T=295.15)
    model.update()
    assert model.state.outlet_fluid.P == pytest.approx(24439888.119)
    assert model.state.outlet_fluid.T == pytest.approx(302.99120246)


def test_reservoir():

    model = ReservoirModelNative(specs_CO2)
    model.init_state(P=2.7579e+7, T=330.)
    model.update()
    assert model.state.outlet_fluid.P == pytest.approx(27578999.9)
    assert model.state.outlet_fluid.T == pytest.approx(375.6035)

    model = ReservoirModelNative(specs_H2O)
    model.init_state(P=2.7579e+7, T=330.)
    model.update()
    assert model.state.outlet_fluid.P == pytest.approx(27579000.0)
    assert model.state.outlet_fluid.T == pytest.approx(375.65)


def test_production_well():

    model = ProductionWellModelNative(specs_CO2)
    model.init_state(P=2.8e7, T=375.0)
    model.update()
    assert model.state.outlet_fluid.P == pytest.approx(13913705.3614)
    assert model.state.outlet_fluid.T == pytest.approx(337.876370365)

    model = ProductionWellModelNative(specs_H2O)
    model.init_state(P=2.8e7, T=375.0)
    model.update()
    assert model.state.outlet_fluid.P == pytest.approx(9180870.3324)
    assert model.state.outlet_fluid.T == pytest.approx(367.11120669)

def test_surface():

    model = SurfaceModelCPGNative(specs_CO2)
    model.init_state(P=1.0e7, T=330.)
    model.update()
    assert model.state.outlet_fluid.P == pytest.approx(6053084.8456)
    assert model.state.outlet_fluid.T == pytest.approx(295.150)

    model = SurfaceModelORCNative(specs_H2O)
    model.init_state(P=1.0e7, T=330.)
    model.update()
    assert model.state.outlet_fluid.P == pytest.approx(9999899.413)
    assert model.state.outlet_fluid.T == pytest.approx(317.141317)

