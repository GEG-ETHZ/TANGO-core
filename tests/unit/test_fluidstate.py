import pytest
from CoolProp.CoolProp import PropsSI

from tango.core import FluidState


class ComputePropsSI:
    def __init__(self, fluidname: str, P: float, T: float):
        self.P = PropsSI("P", "P", P, "T", T, fluidname)
        self.T = PropsSI("T", "P", P, "T", T, fluidname)
        self.H = PropsSI("H", "P", P, "T", T, fluidname)
        self.S = PropsSI("S", "P", P, "T", T, fluidname)
        self.Q = PropsSI("Q", "P", P, "T", T, fluidname)
        self.rho = PropsSI("D", "P", P, "T", T, fluidname)
        self.cp = PropsSI("CPMASS", "P", P, "T", T, fluidname)
        self.mu = PropsSI("VISCOSITY", "P", P, "T", T, fluidname)
        self.Tcrit = PropsSI("TCRIT", "P", P, "T", T, fluidname)
        self.Pcrit = PropsSI("PCRIT", "P", P, "T", T, fluidname)


def check(state):
    props = ComputePropsSI(state.fluidname, state.P, state.T)
    assert pytest.approx(props.P) == state.P
    assert pytest.approx(props.T) == state.T
    assert pytest.approx(props.H) == state.H
    assert pytest.approx(props.S) == state.S
    assert pytest.approx(props.Q) == state.Q
    assert state.rho == pytest.approx(props.rho)
    assert state.cp == pytest.approx(props.cp)
    assert state.mu == pytest.approx(props.mu)
    assert state.Tcrit == pytest.approx(props.Tcrit)
    assert state.Pcrit == pytest.approx(props.Pcrit)


def test_FluidState():
    state1 = FluidState.withPT("Water", 1.23e5, 321.0)
    assert pytest.approx(1.23e5) == state1.P
    assert pytest.approx(321.0) == state1.T
    check(state1)

    state2 = FluidState.withHP("Water", state1.H, state1.P)
    assert pytest.approx(state1.H) == state2.H
    assert pytest.approx(state1.P) == state2.P
    check(state2)

    state3 = FluidState.withPS("Water", state2.P, state2.S)
    assert pytest.approx(state2.P) == state3.P
    assert pytest.approx(state2.S) == state3.S
    check(state3)

    state4 = FluidState.withPQ("Water", P=state3.P, Q=0)
    assert pytest.approx(0.0) == state4.Q
    assert pytest.approx(state3.P) == state4.P

    state5 = FluidState.withQT("Water", Q=1, T=state4.T)
    assert pytest.approx(1.0) == state5.Q
    assert pytest.approx(state4.T) == state5.T
