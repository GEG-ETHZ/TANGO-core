from tango.core import FluidState

from CoolProp.CoolProp import PropsSI
import pytest


class ComputePropsSI:
    def __init__(self, fluidname: str, P: float, T: float):
        self.P     = PropsSI("P"        , "P", P, "T", T, fluidname)
        self.T     = PropsSI("T"        , "P", P, "T", T, fluidname)
        self.H     = PropsSI("H"        , "P", P, "T", T, fluidname)
        self.S     = PropsSI("S"        , "P", P, "T", T, fluidname)
        self.Q     = PropsSI("Q"        , "P", P, "T", T, fluidname)
        self.rho   = PropsSI("D"        , "P", P, "T", T, fluidname)
        self.cp    = PropsSI("CPMASS"   , "P", P, "T", T, fluidname)
        self.mu    = PropsSI("VISCOSITY", "P", P, "T", T, fluidname)
        self.Tcrit = PropsSI("TCRIT"    , "P", P, "T", T, fluidname)
        self.Pcrit = PropsSI("PCRIT"    , "P", P, "T", T, fluidname)


def check(state):
    props = ComputePropsSI(state.fluidname, state.P, state.T)
    assert state.P == pytest.approx(props.P)
    assert state.T == pytest.approx(props.T)
    assert state.H == pytest.approx(props.H)
    assert state.S == pytest.approx(props.S)
    assert state.Q == pytest.approx(props.Q)
    assert state.rho == pytest.approx(props.rho)
    assert state.cp == pytest.approx(props.cp)
    assert state.mu == pytest.approx(props.mu)
    assert state.Tcrit == pytest.approx(props.Tcrit)
    assert state.Pcrit == pytest.approx(props.Pcrit)


def test_FluidState():

    state1 = FluidState.withPT("Water", 1.23e+5, 321.0)
    assert state1.P == pytest.approx(1.23e+5)
    assert state1.T == pytest.approx(321.0)
    check(state1)

    state2 = FluidState.withHP("Water", state1.H, state1.P)
    assert state2.H == pytest.approx(state1.H)
    assert state2.P == pytest.approx(state1.P)
    check(state2)

    state3 = FluidState.withPS("Water", state2.P, state2.S)
    assert state3.P == pytest.approx(state2.P)
    assert state3.S == pytest.approx(state2.S)
    check(state3)

    state4 = FluidState.withPQ("Water", P = state3.P, Q = 0)
    assert state4.Q == pytest.approx(0.0)
    assert state4.P == pytest.approx(state3.P)

    state5 = FluidState.withQT("Water", Q = 1, T = state4.T)
    assert state5.Q == pytest.approx(1.0)
    assert state5.T == pytest.approx(state4.T)
