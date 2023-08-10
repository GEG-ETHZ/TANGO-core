from tango.core.constants import *
from tango.core.config import *
from tango.core import FluidState
from tango.models.adams.surface.base import *
from tango import utils
from dataclasses import dataclass

import logging
import math
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d


@dataclass
class SurfaceSpecsORCAdams(CommonSpecs):
    approach_temperature: float = 7.0  # The temperature difference between condensing and the surface temperature (K)
    pinch_temperature: float = 5.0  # (K)
    temperature_range: float = 0.  # diff between inlet and exit fluid temperature.
    eta_pump: float = 0.90  # The pump efficiency (-)
    condensation_pressure_offset: float = 5e4  # (Pa)
    total_pipe_length: float = None  # (m)
    pipe_diameter: float = 0.41  # (m)
    epsilon: float = 55.e-6  # roughness of surface pipe (m)
    eta_turbine: float = 0.78  # The isentropic efficiency of the turbine (-)
    cooling_tower_design: str = 'CLOSED'  # cooling tower design
    cooling_mode: str = 'WET'  # WET or DRY
    initial_outlet_pressure: float = 1.2e6  # Initial guess of outlet (injector wellhead) pressure (Pa) for ORC
    initial_outlet_temperature: float = 333.15  # Initial guess of outlet (injector wellhead) temperature (K) for ORC
    refrigerant: str = 'R245fa'
    ORC_opt_mode: str = 'min_cost'  # min_cost or max_power


@dataclass
class SurfaceStateORCFluid():
    """"dataclass to store ORC states"""
    w_pump: float = 0.
    w_turbine: float = 0.
    w_cooler: float = 0.
    w_condenser: float = 0.
    q_cooler: float = 0.
    q_preheater: float = 0.
    q_boiler: float = 0.
    q_desuperheater: float = 0.
    q_recuperator: float = 0.
    q_condenser: float = 0.


class SurfaceStateORCAdams(SurfaceState):
    def __init__(self):
        SurfaceState.__init__(self)
        self.ORC_fluid: FluidState
        self.dP_pump: float = 0.
        self.dP_pipe: float = 0.
        self.dT_range: float = 0.
        self.dT_LMTD_preheater: float = 0.
        self.dT_LMTD_boiler: float = 0.
        self.dT_LMTD_recuperator: float = 0.
        self.w_pump: float = 0.
        self.w_turbine: float = 0.
        self.w_cooler: float = 0.
        self.w_condenser: float = 0.
        self.w_downhole_pump: float = 0.
        self.q_cooler: float = 0.
        self.q_preheater: float = 0.
        self.q_boiler: float = 0.
        self.q_desuperheater: float = 0.
        self.q_recuparator: float = 0.
        self.q_condenser: float = 0.
        self.w_net: float = 0.


    def get_del_pressure(self) -> float:
        return self.inlet_fluid.P - self.outlet_fluid.P - self.dP_pipe


    # def get_del_temperature(self) -> float:
    #     return self.inlet_fluid.T - self.outlet_fluid.T


class SurfaceModelORCAdams(SurfaceModelAdams):
    """The power plant model based on Adams et al. (2015)."""

    def __init__(self, specs: dict):
        SurfaceModelAdams.__init__(self)
        self.specs = SurfaceSpecsORCAdams(**specs)
        self._fluid_name = self.specs.fluid_name
        self._refrigerant_name = self.specs.refrigerant
        self._cross_sectional_area = 0.25 * np.pi * self.specs.pipe_diameter ** 2
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._ORC_state = SurfaceStateORCFluid()
        self._set_mdot()
        self._set_constants()
        self._set_max_boiling_temperature()
        self._set_lookup_tables()


    def _set_max_boiling_temperature(self) -> float:
        """
            get max boiling temperature that will be used as a constraint for the organic fluid at the temperature
            with max saturated vapor entropy
        """
        self._ORC_fluid_state = FluidState.withPT(self._refrigerant_name,
                                            P=self.specs.initial_outlet_pressure,
                                            T=self.specs.initial_outlet_temperature) # P and T are arbitrary here.
        ORC_fluid_Pcrit = self._ORC_fluid_state.Pcrit
        P_min = FluidState.withQT(self._refrigerant_name, Q=1.0, T=273.15).P  # assume min pressure is condensing at 0 deg.C
        P_arr = np.linspace(P_min, ORC_fluid_Pcrit, 1000)
        S_arr = np.zeros(len(P_arr))
        for i, P in enumerate(P_arr):
            S_arr[i] = FluidState.withPQ(self._refrigerant_name, P=P, Q=1.0).S
        S_max = np.max(S_arr)
        P_max = P_arr[np.argmax(S_arr)]
        self._max_boiling_temperature = FluidState.withPS(self._refrigerant_name, P=P_max, S=S_max).T


    def _set_lookup_tables(self) -> None:
        """set ORC_Tboil_optimum table. Note that the unit is in deg. C"""
        fname = f"ORC_Tboil_optimum_{MAP_ORC_OPTNAME_TO_TABLE_NAME[self.specs.ORC_opt_mode]}_{self._refrigerant_name}.csv"
        self._ORC_Tboil_optimum_table = utils.get_table(fname)


    def _get_value_from_table(self, x: float, col_name: str) -> float:
        """

        Args:
            x: temperature in K
            col_name: T_boil_C or dT_pinch_C

        Returns: interpolated (extrapolated, if x is outside the range) value (T_boil_C or dT_pinch_C)

        """
        x += K_TO_C
        df = self._ORC_Tboil_optimum_table
        val = float(interp1d(df.T_C, df[col_name], bounds_error=False, kind='linear')(x))
        if np.isnan(val):
            logging.warning(
                f"A value {x} is outside the interpolation range in ORC_Tboil_optimum_table. Extrapolating a value for {col_name}.")
            return float(
                interp1d(df.T_C, df[col_name], bounds_error=False, fill_value='extrapolate', kind='linear')(year))
        return val


    def _compute_friction_factor(self, rho: float, mu: float, u: float) -> float:
        """Returns the friction factor calculated using the Haaland equation (1983).

        Args:
            rho (float): the fluid density (kg/m3)
            mu (float): the dynamic viscosity (Pa s)
            u (float): the flow velocity (m/s)

        Returns:
            float: the friction factor (-)
        """
        d = self.specs.pipe_diameter
        epsilon = self.specs.epsilon
        Re = rho * u * d / mu  # Reynolds number
        r = epsilon / d
        return (-1.8 * np.log10((r / 3.7) ** 1.11 + 6.9 / Re)) ** -2.0


    def _get_pipe_pressure_drop(self, rho: float, u: float, ff: float) -> float:
        d = self.specs.pipe_diameter
        L = self.specs.well_spacing
        return 0.5 * ff * L * rho * u ** 2 / d


    def _update_state_pipe(self, state) -> None:
        """update state at surface pile (pressure drop between producer wellhead and surface plant inlet)"""

        rho = state.inlet_fluid.rho
        mu = state.inlet_fluid.mu
        u = self._m_dot / self._cross_sectional_area / rho

        ff = self._compute_friction_factor(rho, mu, u)
        state.dP_pipe = self._get_pipe_pressure_drop(rho, u, ff)

        state.inlet_fluid.updatePT(P=state.inlet_fluid.P - state.dP_pipe, T=state.inlet_fluid.T)


    def _get_values_from_table(self, T_inlet):
        T_boiling = self._get_value_from_table(x=T_inlet, col_name='T_boil_C') + C_TO_K
        dT_pinch = self._get_value_from_table(x=T_inlet, col_name='dT_pinch_C')
        if np.isnan(T_boiling):
            raise RuntimeError(f"Nan ORC T_boiling found.")
        if np.isnan(dT_pinch):
            raise RuntimeError(f"Nan ORC dT_pinch found.")
        if T_boiling > self._ORC_fluid_state.Tcrit:
            raise RuntimeError(f"ORC T_boiling is greater than critical point.")
        if dT_pinch < 0:
            raise RuntimeError(f"Negative ORC dT_pinch found.")
        return T_boiling, dT_pinch


    def _update_state_fluid(self, state) -> None: #TODO: clean up

        T_inlet = state.inlet_fluid.T
        T_boiling, dT_pinch = self._get_values_from_table(T_inlet)

        # State 1 (Condenser -> Pump)
        fluid_state_pump_inlet = FluidState.withQT(self._refrigerant_name,
                                                   Q=0.0,
                                                   T=self._condensation_temperature)  # saturated liquid

        # State 6 (Desuperheater/Cooler -> Condenser)
        fluid_state_condenser_inlet = FluidState.withQT(self._refrigerant_name,
                                                        Q=1.0,
                                                        T=fluid_state_pump_inlet.T)  # saturated vapor

        # State 3 (Preheater -> Boiler)
        fluid_state_boiler_inlet = FluidState.withQT(self._refrigerant_name,
                                                     Q=0.0,
                                                     T=T_boiling)  # saturated liquid

        # State 4 (Boiler -> Turbine)
        fluid_state_turbine_inlet = FluidState.withQT(self._refrigerant_name,
                                                      Q=1.0,
                                                      T=fluid_state_boiler_inlet.T)  # saturated vapor

        # State 5 (Turbine -> Desuperheater/Cooler)
        fluid_state_cooler_inlet = FluidState.withPS(self._refrigerant_name,
                                                     P=fluid_state_pump_inlet.P,
                                                     S=fluid_state_turbine_inlet.S)
        hs_cooler_inlet = fluid_state_cooler_inlet.H
        h_cooler_inlet = fluid_state_turbine_inlet.H - self.specs.eta_turbine * (fluid_state_turbine_inlet.H - hs_cooler_inlet)
        fluid_state_cooler = FluidState.withHP(self._refrigerant_name,
                                               H=h_cooler_inlet,
                                               P=fluid_state_pump_inlet.P)

        # State 2 (Pump -> Preheater)
        fluid_state_preheater_inlet = FluidState.withPS(self._refrigerant_name,
                                                        P=fluid_state_boiler_inlet.P,
                                                        S=fluid_state_pump_inlet.S)
        hs_preheater_inlet = fluid_state_preheater_inlet.H
        h_preheater = fluid_state_pump_inlet.H - ((fluid_state_pump_inlet.H - hs_preheater_inlet) / self.specs.eta_pump)
        fluid_state_preheater = FluidState.withHP(self._refrigerant_name,
                                                  H=h_preheater,
                                                  P=fluid_state_boiler_inlet.P)

        #
        # ... ORC fluid heat/work
        #

        self._ORC_state.w_pump = fluid_state_pump_inlet.H - fluid_state_preheater.H
        self._ORC_state.q_preheater = fluid_state_boiler_inlet.H - fluid_state_preheater.H
        self._ORC_state.q_boiler = fluid_state_turbine_inlet.H - fluid_state_boiler_inlet.H
        self._ORC_state.w_turbine = fluid_state_turbine_inlet.H - fluid_state_cooler.H
        self._ORC_state.q_cooler = fluid_state_condenser_inlet.H - fluid_state_cooler.H
        self._ORC_state.q_condenser = fluid_state_pump_inlet.H - fluid_state_condenser_inlet.H

        # cooling tower parastic load
        self._condensation_temperature_range = fluid_state_cooler.T - fluid_state_condenser_inlet.T
        self._ORC_state.w_cooler = self._ORC_state.q_cooler * self._get_parasitic_power_fraction_cooling() # (W)
        self._ORC_state.w_condenser = self._ORC_state.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)

        #
        # ... Water (assume pressure 100 kPa above saturation)
        #

        fluid_state_water = FluidState.withQT(self._fluid_name, Q=0., T=T_inlet)
        Psat_water = fluid_state_water.P
        cp_water = fluid_state_water.cp

        # Water state 11, inlet, 12, mid, 13 exit
        T_11 = T_inlet
        T_12 = T_boiling + dT_pinch
        mdot_ratio = cp_water * (T_11 - T_12) / self._ORC_state.q_boiler
        T_13 = T_12 - mdot_ratio * self._ORC_state.q_preheater / cp_water
        if T_13 < (fluid_state_preheater.T + dT_pinch): # check that T_C(13) isn't below pinch constraint
            T_13 = fluid_state_preheater.T + dT_pinch # pinch constraint is here, not at 12, outlet is pump temp plus pinch
            R = self._ORC_state.q_boiler / (self._ORC_state.q_boiler + self._ORC_state.q_preheater)
            T_12 = T_11 - (T_11 - T_13) * R
            mdot_ratio = cp_water * (T_11 - T_12) / self._ORC_state.q_boiler

        # Calculate water heat/work
        state.q_preheater = mdot_ratio * self._m_dot * self._ORC_state.q_preheater
        state.q_boiler = mdot_ratio * self._m_dot * self._ORC_state.q_boiler
        state.q_desuperheater = mdot_ratio * self._m_dot * self._ORC_state.q_cooler
        state.q_condenser = mdot_ratio * self._m_dot * self._ORC_state.q_condenser
        state.q_recuperator = mdot_ratio * self._m_dot * self._ORC_state.q_recuperator
        state.w_turbine = mdot_ratio * self._m_dot * self._ORC_state.w_turbine
        state.w_pump = mdot_ratio * self._m_dot * self._ORC_state.w_pump
        state.w_cooler = mdot_ratio * self._m_dot * self._ORC_state.w_cooler
        state.w_condenser = mdot_ratio * self._m_dot * self._ORC_state.w_condenser
        state.w_net = state.w_turbine + state.w_pump + state.w_cooler + state.w_condenser

        # Calculate temperatures
        state.dT_range_CT = fluid_state_cooler.T - fluid_state_condenser_inlet.T
        dT_A_p = T_13 - fluid_state_preheater.T
        dT_B_p = T_12 - fluid_state_boiler_inlet.T
        if dT_A_p == dT_B_p:
            state.dT_LMTD_preheater = dT_A_p
        else:
            div = dT_A_p/dT_B_p
            state.dT_LMTD_preheater = (dT_A_p - dT_B_p) / (math.log(abs(div)) * np.sign(div))

        dT_A_b = T_12 - fluid_state_boiler_inlet.T
        dT_B_b = T_11 - fluid_state_turbine_inlet.T
        if dT_A_b == dT_B_b:
            state.dT_LMTD_boiler = dT_A_b
        else:
            div = dT_A_b / dT_B_b
            state.dT_LMTD_boiler = (dT_A_b - dT_B_b) / (math.log(abs(div)) * np.sign(div))

        state.outlet_fluid.updatePT(P=state.inlet_fluid.P, T=T_13)


    def init_state(self, state) -> None:
        state.outlet_fluid = FluidState.withPT(self._fluid_name,
                                               P=self.specs.initial_outlet_pressure,
                                               T=self.specs.initial_outlet_temperature)


    def overwrite_state_pipe(self, state) -> None:
        self._update_state_pipe(state)


    def update(self, state) -> None:

        self._update_state_pipe(state)

        self._update_state_fluid(state)
