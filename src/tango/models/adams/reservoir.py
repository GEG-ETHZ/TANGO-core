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
    area: float = None
    porosity: float = 0.10    # the rock porosity in the reservoir (dimensionless)
    permeability: float = 5.0e-14 # the rock permeability in the reservoir (in m2)
    net_to_gross_ratio: float = 1.0
    brine_density: float = 1000.0  # the brine density used to calculate the reservoir pressure (kg/m3)
    initial_pressure: float = None
    initial_temperature: float = None


class ReservoirStateAdams(ReservoirState):
    """Resevoir state based on Adams et. al (2015)."""
    def __init__(self):
        ReservoirState.__init__(self)
        self.energy_extracted = 0.0
        self.energy_extracted_old = 0.0 # reservoir energy extracted at previous time step (J)
        self.pressure_old = 0.0 # reservoir pressure at previous time step (Pa)


class ReservoirModelAdams(ReservoirModel):
    """The reservoir (1-D well-pair) model based on Adams et al. (2015)."""
    def __init__(self, specs: dict) -> None:
        self.specs = ReservoirSpecsAdams(**specs)

        self.initial_temperature = self.get_initial_temperature()
        self.reference_temperature = self.initial_temperature - self.specs.surface_temperature
        self.fluid_name = self.specs.fluid_name
        self.well_pattern = self.specs.well_pattern.upper()

        self.initial_pressure = self.get_initial_pressure()

        self.area = self.get_area()
        self.volume = self.specs.thickness * self.area
        self.fluid_volume = self.specs.porosity * self.volume
        self.rock_volume = self.volume - self.fluid_volume

        T_ref = self.initial_temperature - self.specs.surface_temperature # reference temperature
        self.rock_C_v = self.specs.rock_density * self.specs.rock_cp # volumetric heat capacity of rocks (J/m3)

        self.set_mdot()
        self.set_impedance_func()

    def get_area(self) -> float:
        if self.specs.area is None:
            return 0.5 * (self.specs.well_spacing ** 2) # genGEO method. likely over estimated
        return self.specs.area


    def get_initial_temperature(self) -> float:
        if self.specs.initial_temperature is not None:
            return self.specs.initial_temperature
        h, dTdz, T0 = self.specs.reservoir_depth, self.specs.thermal_gradient, self.specs.surface_temperature
        return T0 + h * dTdz # deg C

    def get_initial_pressure(self) -> float:
        if self.specs.initial_pressure is not None:
            return self.specs.initial_pressure
        g = GRAVITY_ACCELERATION # m/s2
        h = self.specs.reservoir_depth
        return self.specs.brine_density * g * h

    def set_boundaries(self, inj_well_specs, prd_well_specs) -> None:
        """get effective (average) wellbore diameter"""
        self.specs.well_diameter = 0.5 * (inj_well_specs.diameter + prd_well_specs.diameter)

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
        return mu * np.log(4.0 * L / (np.pi * D)) / (rho * k * b)

    @staticmethod
    def impedance_func_doublet(mu, rho, k, b, L, D) -> float:
        return mu * (np.log(L/(exp*D)) + D/L) / (rho*k*b*np.pi)

    def set_depletion_curve_coeffs(self, state) -> list:

        m_dot = self.m_dot # kg/s
        b = self.specs.thickness # m
        k_rock = self.specs.rock_k # thermal comductivity (W/m-K)
        rho_rock = self.specs.rock_density  # kg/m3
        rho_fluid = 0.5 * (state.inlet_fluid.rho + state.outlet_fluid.rho) # kg/m3
        cp_rock = self.specs.rock_cp # specific heat capacity (J/(kg*K))
        cp_fluid = 0.5 * (state.inlet_fluid.cp + state.outlet_fluid.cp) # specific heat capacity (J/(kg*K))
        R = self.specs.well_spacing # m

        coeff1 = b * k_rock * rho_fluid / m_dot / rho_rock / cp_rock
        coeff2 = k_rock * R * rho_fluid / rho_rock / cp_fluid / m_dot

        p1 = np.minimum(-890.97 * coeff1 - 1.30, -1.3)
        p2 = 0.4095 * np.exp(-0.7815 * p1)
        p3 = np.clip(1 - (1.4646 * np.exp(-377.3 * coeff2)), 0., 1.)

        return p1, p2, p3


    def init_state(self, state) -> None:
        state.inlet_fluid = FluidState.withPT(self.fluid_name, self.initial_pressure, self.initial_temperature)
        state.outlet_fluid = FluidState.withPT(self.fluid_name, self.initial_pressure, self.initial_temperature)
        state.pressure_old = self.initial_pressure
        self.p1, self.p2, self.p3 = self.set_depletion_curve_coeffs(state)


    def set_inlet_state(self, state, state_from) -> None:
        state.inlet_fluid = state_from.outlet_fluid

    def update_impedance(self, mu, rho) -> None:
        """Update the reservoir impedance using the doublet solution of Adams et al. (2020)."""
        k, b, NTG = float(self.specs.permeability), self.specs.thickness, self.specs.net_to_gross_ratio
        L, D = self.specs.well_spacing, self.specs.well_diameter
        b_eff = b * NTG  # = effective thickness
        self.impedance = self.impedance_func(mu, rho, k, b_eff, L, D)

    def update(self, state) -> None:
        """

        Args:
            state: outlet state of injection_well

        """

        #
        # ... update reservoir pressure (outlet_pressure)
        #

        average_mu = 0.5*(state.inlet_fluid.mu + state.outlet_fluid.mu)
        average_rho = 0.5*(state.inlet_fluid.rho + state.outlet_fluid.rho)
        self.update_impedance(average_mu, average_rho)

        outlet_pressure = state.inlet_fluid.P - self.m_dot * self.impedance

        #
        # ... update reservoir temperature (outlet_temperature)
        #

        p1, p2, p3 = self.p1, self.p2, self.p3
        dt = self.specs.dt * YEAR_TO_SECOND

        T_inj = state.inlet_fluid.T
        dT = self.initial_temperature - T_inj
        h_inj = state.inlet_fluid.H
        h_prod = state.outlet_fluid.H

        reservoir_energy = self.rock_volume * self.rock_C_v * dT # J
        # state.energy_extracted += self.m_dot * (h_prod-h_inj) * dt # J
        state.energy_extracted = state.energy_extracted_old + self.m_dot * (h_prod - h_inj) * dt  # J
        psi = state.energy_extracted / reservoir_energy # (-)
        # energy_extracted = self.m_dot * (h_prod-h_inj) * dt # J
        # psi = energy_extracted / reservoir_energy # (-)
        gamma = self.depletion_curve(psi, p1, p2, p3)

        outlet_temperature = gamma * dT + state.inlet_fluid.T

        state.outlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)


    def execute(self, state) -> None:
        self.update(state)

    @staticmethod
    def depletion_curve(psi, p1, p2, p3) -> float:
        if psi <= (-p1/p2):
            return 1 - (1 - p3) * (1 - 0.5*erfc(p2*psi + p1))
        else:
            C = 1.13
            return 1 - (1 - p3) * (1 - 0.5*np.exp(-C*(p2*psi + p1)))