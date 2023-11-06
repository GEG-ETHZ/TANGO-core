import numpy as np
from math import erfc
from math import e as exp

from tango.core.config import *
from tango.core import FluidState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from tango.core.abstracts.unit import *
from .common import CommonSpecs
from dataclasses import dataclass

@dataclass
class ReservoirSpecsNative(CommonSpecs):
    """Specifications for reservoir unit based on Adams et. al (2015)"""
    reservoir_depth: float = None
    thickness: float = None     # the reservoir thickness (in m)
    porosity: float = None    # the rock porosity in the reservoir (dimensionless)
    permeability: float = None # the rock permeability in the reservoir (in m2)
    area: float = None
    net_to_gross_ratio: float = 1.0
    brine_density: float = 1000.0  # the brine density used to calculate the reservoir pressure (kg/m3)
    initial_pressure: float = None
    initial_temperature: float = None
    well_eff_diameter: float = 0.41 # effective (average) wellbore diameter (inj and prod) (m)
    def __post_init__(self):
        required_fields = ['reservoir_depth', 'thickness', 'porosity', 'permeability']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")


class ReservoirStateNative(UnitState):
    """Resevoir state based on Adams et. al (2015)."""
    def __init__(self):
        UnitState.__init__(self)
        self._energy_extracted = 0.0
        self._energy_extracted_old = 0.0 # reservoir energy extracted at previous time step (J)
        self._pressure_old = 0.0 # reservoir pressure at previous time step (Pa)


    def set_pressure_old(self, val) -> None:
        self._pressure_old = val


    def get_energy_extracted(self) -> float:
        return self._energy_extracted


    def get_del_pressure(self) -> float:
        return self._pressure_old - self.outlet_fluid.P


    def update_pressure_old(self) -> None:
        self._pressure_old = self.outlet_fluid.P


    def update_energy_extracted(self, del_) -> None:
        self._energy_extracted = self._energy_extracted_old + del_


    def update_energy_extracted_old(self) -> None:
        self._energy_extracted_old = self._energy_extracted


class ReservoirUnitNative(Unit):
    """The reservoir (1-D well-pair) unit based on Adams et al. (2015)."""
    def __init__(self, id: str, specs: dict) -> None:
        super().__init__(id, specs)
        self.specs = ReservoirSpecsNative.from_dict(self._process_specs(specs))
        self.fluid_name = self.specs.fluid_name
        self.well_pattern = self.specs.well_pattern.upper()

        self.area = self._compute_area()
        self.volume = self.specs.thickness * self.area
        self.fluid_volume = self.specs.porosity * self.volume
        self.rock_volume = self.volume - self.fluid_volume
        self.rock_C_v = self.specs.rock_density * self.specs.rock_cp # volumetric heat capacity of rocks (J/m3)

        self.initial_temperature = self._compute_initial_temperature()
        self.initial_pressure = self._compute_initial_pressure()

        self.specs.well_diameter = self.specs.well_eff_diameter

        # self._set_mdot()
        self._initialize_mdot_mult()
        self._set_impedance_func()

        self.init_state()


    def _process_specs(self, specs) -> dict:
        if 'well_eff_diameter' not in specs['reservoir']:
            val = 0.41
            if 'injection_well' in specs:
                if 'diameter' in specs['injection_well']:
                    val = specs['injection_well']['diameter']
            if 'production_well' in specs:
                if 'diameter' in specs['production_well']:
                    val = 0.5 * (val + specs['production_well']['diameter'])
            specs['reservoir']['well_eff_diameter'] = val
        return specs['common'] | specs['reservoir']


    def _compute_area(self) -> float:
        return 0.5 * (self.specs.well_spacing ** 2) if self.specs.area is None else self.specs.area


    def _compute_initial_temperature(self) -> float:
        if self.specs.initial_temperature is not None:
            return self.specs.initial_temperature
        h, dTdz, T0 = self.specs.reservoir_depth, self.specs.thermal_gradient, self.specs.surface_temperature
        return T0 + h * dTdz # deg C


    def _compute_initial_pressure(self) -> float:
        if self.specs.initial_pressure is not None:
            return self.specs.initial_pressure
        return self.specs.brine_density * GRAVITY_ACCELERATION * self.specs.reservoir_depth


    # def _set_mdot(self) -> None:
    #     """
    #         - mass_flow_rate = flow rate at an injector (Kg/s)
    #         - m_dot = flow rate at each well pair (Kg/s)
    #     """
    #     self.m_dot = self.specs.mass_flow_rate / 4.0 if self.well_pattern == 'INVERTED_5SPOT' else self.specs.mass_flow_rate

    def _initialize_mdot_mult(self) -> None:
        """multiplier to convert injection flow rate to m_dot (well-pair level flow rate)"""
        self.m_dot_mult = 0.25 if self.well_pattern == 'INVERTED_5SPOT' else 1.0


    def _set_impedance_func(self) -> None:
        self.impedance_func = getattr(self, f"_impedance_func_{self.well_pattern.lower().split('_')[-1]}", None)
        if self.impedance_func == None:
            raise ValueError(f"well_pattern: {self.well_pattern} is not supported in native reservoir unit.")


    @staticmethod
    def _impedance_func_5spot(mu, rho, k, b, L, D) -> float:
        return mu * np.log(4.0 * L / (np.pi * D)) / (rho * k * b)

    @staticmethod
    def _impedance_func_doublet(mu, rho, k, b, L, D) -> float:
        return mu * (np.log(L / (exp * D)) + D / L) / (rho * k * b * np.pi)  # ref
        # return mu * np.log(L /D) / (rho * k * b * np.pi) # genGEO


    def _compute_depletion_curve_coeffs(self) -> list:

        m_dot = self.specs.mass_flow_rate / 4.0 if self.well_pattern == 'INVERTED_5SPOT' else self.specs.mass_flow_rate # kg/s
        b = self.specs.thickness # m
        k_rock = self.specs.rock_k # thermal comductivity (W/m-K)
        rho_rock = self.specs.rock_density  # kg/m3
        rho_fluid = 0.5 * (self.state.inlet_fluid.rho + self.state.outlet_fluid.rho) # kg/m3
        cp_rock = self.specs.rock_cp # specific heat capacity (J/(kg*K))
        cp_fluid = 0.5 * (self.state.inlet_fluid.cp + self.state.outlet_fluid.cp) # specific heat capacity (J/(kg*K))
        R = self.specs.well_spacing # m

        coeff1 = b * k_rock * rho_fluid / m_dot / rho_rock / cp_rock
        coeff2 = k_rock * R * rho_fluid / rho_rock / cp_fluid / m_dot

        p1 = np.minimum(-890.97 * coeff1 - 1.30, -1.3)
        p2 = 0.4095 * np.exp(-0.7815 * p1)
        p3 = np.clip(1 - (1.4646 * np.exp(-377.3 * coeff2)), 0., 1.)

        return p1, p2, p3


    def _update_impedance(self, mu, rho) -> None:
        """Update the reservoir impedance using the doublet solution of Adams et al. (2020)."""
        k, b, NTG = float(self.specs.permeability), self.specs.thickness, self.specs.net_to_gross_ratio
        L, D = self.specs.well_spacing, self.specs.well_diameter
        b_eff = b * NTG  # = effective thickness
        self.impedance = self.impedance_func(mu, rho, k, b_eff, L, D)


    def _depletion_curve(self, psi) -> float:
        p1, p2, p3 = self.p1, self.p2, self.p3
        if psi <= (-p1/p2):
            return 1 - (1 - p3) * (1 - 0.5*erfc(p2*psi + p1))
        else:
            C = 1.13
            return 1 - (1 - p3) * (1 - 0.5*np.exp(-C*(p2*psi + p1)))


    def init_state(self, P: float=None, T:float=None) -> None:
        P = self.initial_pressure if P==None else P
        T = self.initial_temperature if T == None else T
        self.state = ReservoirStateNative()
        self.state.inlet_fluid = FluidState.withPT(self.fluid_name, P, T)
        self.state.outlet_fluid = FluidState.withPT(self.fluid_name, P, T)
        self.state.set_pressure_old(self.initial_pressure)
        self.p1, self.p2, self.p3 = self._compute_depletion_curve_coeffs()


    def update(self) -> None:
        """Update reservoir state given inlet state (outlet fluid state of injection well)"""

        state = self.state
        self.m_dot = self.m_dot_mult * state.mass_rate

        #
        # ... update reservoir pressure (outlet_pressure)
        #

        average_mu = 0.5*(state.inlet_fluid.mu + state.outlet_fluid.mu)
        average_rho = 0.5*(state.inlet_fluid.rho + state.outlet_fluid.rho)
        self._update_impedance(average_mu, average_rho)

        outlet_pressure = state.inlet_fluid.P - self.m_dot * self.impedance

        #
        # ... update reservoir temperature (outlet_temperature)
        #

        dt = self.specs.dt * YEAR_TO_SECOND

        T_inj = state.inlet_fluid.T
        dT = self.initial_temperature - T_inj
        h_inj = state.inlet_fluid.H
        h_prod = state.outlet_fluid.H

        reservoir_energy = self.rock_volume * self.rock_C_v * dT # J
        state.update_energy_extracted(del_=self.m_dot * (h_prod - h_inj) * dt) # J
        psi = state.get_energy_extracted() / reservoir_energy  # (-)
        gamma = self._depletion_curve(psi)
        outlet_temperature = gamma * dT + state.inlet_fluid.T

        state.outlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)
        state.mass_rate = self.m_dot
        self.update_outlet_streams()


    def execute(self) -> None:
        self.update_inlet_state()
        self.update()
        print("reservoir_in ", self.state.inlet_fluid.P, self.state.inlet_fluid.T)
        print("reservoir_out ", self.state.outlet_fluid.P, self.state.outlet_fluid.T)
