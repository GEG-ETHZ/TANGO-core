from tango.models.base import *
from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from dataclasses import dataclass
import numpy as np
from math import erfc
from math import e as exp

@dataclass
class ReservoirSpecsAdams(CommonSpecs):
    """Specifications for reservoir modeling based on Adams et. al (2015)"""
    thickness: float = 305     # the reservoir thickness (in m)
    area: float = 2.5e5    # the reservoir area (m2)
    porosity: float = 0.10    # the rock porosity in the reservoir (dimensionless)
    permeability: float = 5.0e-14 # the rock permeability in the reservoir (in m2)
    brine_density: float = 1000.0  # the brine density used to calculate the reservoir pressure (kg/m3)
    p1: float = -1.9376
    p2: float = 1.743
    p3: float = 0.182


class ReservoirStateAdams(ReservoirState):
    """Resevoir state based on Adams et. al (2015)."""
    def __init__(self):
        ReservoirState.__init__(self)

        # Parameters characterizing thermal decay
        self.gamma = 1.0
        self.psi = 0.0
        self.energy_extracted = 0.0


class ReservoirModelAdams(ReservoirModel):
    """The reservoir (1-D well-pair) model based on Adams et al. (2015)."""
    def __init__(self, specs: dict) -> None:
        self.specs = ReservoirSpecsAdams(**specs)

        h, dTdz, T0 = self.specs.reservoir_depth, self.specs.thermal_gradient, self.specs.surface_temperature

        self.initial_temperature: float = T0 + h * dTdz # deg C
        self.reference_temperature = self.initial_temperature - self.specs.surface_temperature
        self.temperature: float = self.initial_temperature
        self.fluid_name = self.specs.fluid_name
        self.well_pattern = self.specs.well_pattern.upper()

        g = GRAVITY_ACCELERATION # m/s2
        self.reference_pressure: float = self.specs.brine_density * g * h

        self.volume = self.specs.thickness * self.specs.area
        self.fluid_volume = self.specs.porosity * self.volume
        self.rock_volume = self.volume - self.fluid_volume

        T_ref = self.reference_temperature
        rock_C_v = self.specs.rock_density * self.specs.rock_cp # volumetric heat capacity of rocks (J/m3)
        self.reference_energy = self.rock_volume * rock_C_v * T_ref

        self.set_mdot()
        self.set_impedance_func()

    def set_boundaries(self, inj_well_specs, prd_well_specs) -> None:
        """get effective (average) wellbore diameter"""
        self.specs.well_diameter = (inj_well_specs.diameter + prd_well_specs.diameter) / 2.0

    def set_mdot(self) -> None:
        """
            - mass_flow_rate = flow rate at an injector (Kg/s)
            - m_dot = flow rate at each well pair (Kg/s)
        """
        if self.well_pattern not in WELL_PATTERN_OPTIONS:
            raise RuntimeError(f"well_pattern: {self.well_pattern} is not supported")
        self.m_dot = self.specs.mass_flow_rate
        if self.well_pattern == 'INVERTED_5SPOT':
            self.m_dot = self.specs.mass_flow_rate / 4.0


    def set_impedance_func(self) -> None:
        if self.well_pattern == 'DOUBLET':
            self.impedance_func = self.impedance_func_doublet
        else:
            self.impedance_func = self.impedance_func_5spot

    @staticmethod
    def impedance_func_5spot(mu, rho, k, b, L, D) -> float:
        return mu * np.log(4.0*L/(np.pi*D)) / (rho*k*b)

    @staticmethod
    def impedance_func_doublet(mu, rho, k, b, L, D) -> float:
        return mu * np.log(L/(exp*D)) / (rho*k*b*np.pi)

    def update_impedance(self, mu, rho) -> None:
        """Update the reservoir impedance using the doublet solution of Adams et al. (2020)."""
        k, b = self.specs.permeability, self.specs.thickness
        L, D = self.specs.well_spacing, self.specs.well_diameter
        self.impedance = self.impedance_func(mu, rho, k, b, L, D)

    def update_temperature(self, state) -> None:
        """Update reservoir temperature using the thermal decay characterization of
        Adams (2015).

        Keyword arguments:
        dt -- time increments in unit of years
        """
        p1, p2, p3 = self.specs.p1, self.specs.p2, self.specs.p3
        dt = self.specs.dt * YEAR_TO_SECOND

        h_inj = state.inlet_fluid.H
        h_prod = state.outlet_fluid.H

        state.energy_extracted += self.m_dot * (h_prod-h_inj) * dt    # J
        state.psi = state.energy_extracted / self.reference_energy
        state.gamma = self.depletion_curve(state.psi, p1, p2, p3)

        # The outlet fluid temperature is equal to the reservoir temperature
        outlet_temperature = state.gamma * self.reference_temperature + state.inlet_fluid.T
        state.outlet_fluid.updatePT(P=self.reference_pressure, T=outlet_temperature)

    def init_state(self, state):
        # This is an iterative process of getting the inlet state
        inlet_temperature = self.specs.surface_temperature
        state.inlet_fluid = FluidState.withPT(self.fluid_name, self.reference_pressure, inlet_temperature)
        self.update_impedance(state.inlet_fluid.mu, state.inlet_fluid.rho)
        self.delta_P = self.m_dot * self.impedance

        state.inlet_fluid.updatePT(self.reference_pressure + self.delta_P, inlet_temperature)
        state.outlet_fluid = FluidState.withPT(self.fluid_name, self.reference_pressure, self.temperature)

    def execute(self, state) -> None:
        average_mu = 0.5*(state.inlet_fluid.mu + state.outlet_fluid.mu)
        average_rho = 0.5*(state.inlet_fluid.rho + state.outlet_fluid.rho)

        self.update_impedance(average_mu, average_rho)
        self.delta_P = self.m_dot * self.impedance #delta P between inj-prd pair
        self.update_temperature(state)

    @staticmethod
    def depletion_curve(psi, p1, p2, p3) -> float:
        if psi <= (-p1/p2):
            return 1 - (1 - p3) * (1 - 0.5*erfc(p2*psi + p1))
        else:
            C = 1.13
            return 1 - (1 - p3) * (1 - 0.5*np.exp(-C*(p2*psi + p1)))