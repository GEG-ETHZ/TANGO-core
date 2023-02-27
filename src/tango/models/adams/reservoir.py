from tango.models.base import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from dataclasses import dataclass
import numpy as np
from math import erfc

@dataclass
class ReservoirSpecsAdams(CommonSpecs):
    """Specifications for reservoir modeling based on Adams et. al (2015)"""
    depth: float = 1000     # the reservoir depth (in m)
    thickness: float = 305     # the reservoir thickness (in m)
    area: float = 2.5e5    # the reservoir area (m2)
    rock_density: float = 2300    # the rock density in the reservoir (in kg/m3)
    rock_cp: float = 1000    # the rock heat capacity (J/kg)
    porosity: float = 0.10    # the rock porosity in the reservoir (dimensionless)
    permeability: float = 5.0e-14 # the rock permeability in the reservoir (in m2)
    thermal_gradient: float = 0.035    # the vertical thermal gradient in the reservoir (in °C/km)
    surface_temperature: float = 288.15     # K
    surface_pressure: float = 1e5    # Pa
    inlet_temperature: float = 288.15    # K
    well_spacing: float = 707.0    # m
    well_diameter: float = 0.4    # m
    p1: float = -1.9376
    p2: float = 1.743
    p3: float = 0.182


class ReservoirStateAdams(ReservoirState):
    """Resevoir state based on Adams et. al (2015)."""
    def __init__(self, specs: dict):
        ReservoirState.__init__(self)


class ReservoirModelAdams(ReservoirModel):
    """The reservoir model based on Adams et al. (2015)."""
    def __init__(self, specs: dict, state: ReservoirState) -> None:
        self.specs = ReservoirSpecsAdams(**specs)
        self.state = state

        h, dTdz, T0 = self.specs.depth, self.specs.thermal_gradient, self.specs.surface_temperature

        self.initial_temperature: float = T0 + h * dTdz # deg C
        self.inlet_temperature = self.specs.inlet_temperature
        self.reference_temperature = self.initial_temperature - self.inlet_temperature
        self.temperature: float = self.initial_temperature
        self.fluid_name = self.specs.fluid_name

        self.m_dot = self.specs.mass_flow_rate
        self.surface_P, self.surface_T = self.specs.surface_pressure, self.specs.surface_temperature
        self.surface_fluid = FluidState.withPT(self.fluid_name, self.surface_P, self.surface_T)

        g = GRAVITY_ACCELERATION # m/s2
        self.reference_pressure: float = self.surface_fluid.rho * g * h

        # This is an interative process of getting the inlet state
        self.state.inlet_fluid = FluidState.withPT(self.fluid_name, self.reference_pressure, self.inlet_temperature)
        self.update_impedance(self.state.inlet_fluid.mu, self.state.inlet_fluid.rho)
        self.update_delta_P()

        self.state.inlet_fluid.updatePT(self.reference_pressure + self.delta_P, self.inlet_temperature)
        self.state.outlet_fluid = FluidState.withPT(self.fluid_name, self.reference_pressure, self.temperature)

        self.volume = self.specs.thickness * self.specs.area
        self.fluid_volume = self.specs.porosity * self.volume
        self.rock_volume = self.volume - self.fluid_volume

        T_ref = self.reference_temperature
        rock_C_v = self.specs.rock_density * self.specs.rock_cp # volumetric heat capacity of rocks (J/m3)
        self.reference_energy = self.rock_volume * rock_C_v * T_ref

        # These parameters are used to calculate thermal decay
        self.gamma = 1.0
        self.psi = 0.0
        self.energy_extracted = 0.0

        average_mu = 0.5*(self.state.inlet_fluid.mu + self.state.outlet_fluid.mu)
        average_rho = 0.5*(self.state.inlet_fluid.rho + self.state.outlet_fluid.rho)
        self.update_impedance(average_mu, average_rho)
        self.update_delta_P()

    def update_delta_P(self) -> None:
        self.delta_P = self.m_dot * self.impedance

    def update_impedance(self, mu, rho) -> None:
        """Update the reservoir impedance using the 5-spot solution of Adams et al. (2020)."""
        k, b = self.specs.permeability, self.specs.depth
        L, D = self.specs.well_spacing, self.specs.well_diameter

        self.impedance = mu * np.log(4.0*L/(np.pi*D)) / (rho*k*b)

    def update_temperature(self, dt: float) -> None:
        """Update reservoir temperature using the thermal decay characterization of
        Adams (2015).

        Keyword arguments:
        dt -- time increments in unit of years
        """
        p1, p2, p3 = self.specs.p1, self.specs.p2, self.specs.p3
        dt = dt * YEAR_TO_SECOND

        h_inj = self.state.inlet_fluid.H
        h_prod = self.state.outlet_fluid.H

        self.energy_extracted += self.m_dot * (h_prod-h_inj) * dt    # J
        self.psi = self.energy_extracted / self.reference_energy
        self.gamma = self.depletion_curve(self.psi, p1, p2, p3)

        # The outlet fluid temperature is equal to the reservoir temperature
        outlet_temperature = self.gamma * self.reference_temperature + self.inlet_temperature
        self.state.outlet_fluid.updatePT(P=self.reference_pressure, T=outlet_temperature)

    def update(self, dt) -> None:
        self.update_temperature(dt)

    def execute(self) -> None:
        # Should only update its state.reservoir, not others
        self.update(self.specs.dt)

    @staticmethod
    def depletion_curve(psi, p1, p2, p3) -> float:
        if psi <= (-p1/p2):
            return 1 - (1 - p3) * (1 - 0.5*erfc(p2*psi + p1))
        else:
            C = 1.13
            return 1 - (1 - p3) * (1 - 0.5*np.exp(-C*(p2*psi + p1)))