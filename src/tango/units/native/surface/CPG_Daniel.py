import logging
import random
import sys
import numpy as np

from tango.core.config import *
from tango.core import FluidState
from tango.units.native.common import CommonSpecs
from tango.units.native.surface.base import *
from dataclasses import dataclass

import CoolProp.CoolProp as CP
from CoolProp.HumidAirProp import HAPropsSI

T_CRIT_CO2_K = 304.128

@dataclass
class SurfaceSpecsCPGNative(CommonSpecs):
    pipe_diameter: float = None  # (m)
    approach_temperature: float = None  # The temperature difference between condensing and the surface temperature (K)
    condensation_pressure_offset: float = None  # (Pa)
    temperature_range: float = 0. # diff between inlet and exit fluid temperature.
    eta_pump: float = 0.90    # The pump efficiency (-)
    total_pipe_length: float = None # (m)
    epsilon: float = 55.e-6  # roughness of surface pipe (m)
    eta_turbine: float = 0.78 # The isentropic efficiency of the turbine (-)
    cooling_tower_design: str = 'CLOSED' # cooling tower design
    cooling_mode: str = 'WET' # WET or DRY
    dT_approach_CT: float = 5.
    dT_approach_HX: float = 4.
    dT_range_water: float = 2.
    density_constraint: float = 600.0 # kg/m3
    min_quality: float = 0.75
    def __post_init__(self):
        required_fields = ['pipe_diameter', 'approach_temperature', 'condensation_pressure_offset']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")


class SurfaceStateCPGNative(SurfaceState):
    def __init__(self):
        SurfaceState.__init__(self)
        self.inlet_fluid_turbine: FluidState
        self.inlet_fluid_condenser: FluidState
        self.inlet_fluid_pump: FluidState
        self.outlet_fluid_turbine: FluidState
        self.outlet_fluid_condenser: FluidState
        self.outlet_fluid_pump: FluidState
        self.q_condenser: float = 0.
        self.q_cooler: float = 0.
        self.q_preheater: float = 0.
        self.q_boiler: float = 0.
        self.q_desuperheater: float = 0.
        self.q_recuperator: float = 0.
        self.w_turbine: float = 0.
        self.w_pump: float = 0.
        self.w_cooler: float = 0.
        self.w_condenser: float = 0.
        self.w_net: float = 0.
        # self._dP_pump: float = 0.
        self._dP_pump: float = 1000000.


    def get_dP_pump(self) -> float:
        return self._dP_pump


    def update_dP_pump(self, val) -> None:
        self._dP_pump = val


class SurfaceUnitCPGNative(SurfaceUnitNative):

    """The power plant unit based on Adams et al. (2015)."""
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsCPGNative.from_dict(self._process_specs(specs))
        self._fluid_name = self.specs.fluid_name
        self._min_Temp_CO2 = self.specs.surface_temperature + self.specs.dT_approach_HX + self.specs.dT_range_water + self.specs.dT_approach_CT
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._condensation_temperature_range = 0
        self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0 #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow
        self._set_mult()
        self._set_constants()

        self.init_state()


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['surface']


    def _update_turbine_power(self) -> None:

        P_out_guess = self.state.inlet_fluid.P
        T_in =self.state.inlet_fluid.T
        # P_out_guess = 121e5
        # T_in =60.4 + 273.15

        # P_out_guess = 85e5
        # T_in =35.8 + 273.15
        # raise RuntimeError(f"some error")

        max_retry = 10
        try:
            self.state.inlet_fluid.updatePT(P_out_guess, T_in)
        except:
            print(f"Faield to update PS: {P_out_guess},{self.state.inlet_fluid.S}")
            retry_count = 0
            P_out_guess -= 1e5
            for i in range(max_retry):
                try:
                    print(f"Retrying {i + 1} of {max_retry}")
                    self.state.inlet_fluid.updatePT(P_out_guess, T_in)
                    break
                except:
                    P_out_guess -= 1e5
                    retry_count += 1

        # self.state.inlet_fluid.updatePT(P_out_guess, T_in)

        min_temp_CO2 = self._min_Temp_CO2
        density_constraint = self.specs.density_constraint
        min_quality = self.specs.min_quality
        # fluid_state_tmp = FluidState.withPT("CO2", P_out_guess)

        h_turb_in = CP.PropsSI("HMASS", "T", T_in, "P", P_out_guess, "CO2")
        s_turb_in = CP.PropsSI("SMASS", "T", T_in, "P", P_out_guess, "CO2")
        CP_f = CP.PropsSI("CPMASS", "T", T_in, "P", P_out_guess, "CO2")
        phase = None
        itr = 1

        while phase != "liquid":  # and phaselse != “twophase”:
        # while phase != "liquid" and phase != "twophase":


            # Calculate the enthalpy at the outlet of the turbine followed by an isentropic expansion
            # self.state.outlet_fluid_turbine.updatePS(P=P_out_guess, S=self.state.inlet_fluid.S)
            try:
                self.state.outlet_fluid_turbine.updatePS(P=P_out_guess, S=self.state.inlet_fluid.S)
            except:
                print(f"Faield to update PS: {P_out_guess},{self.state.inlet_fluid.S}")
                retry_count = 0
                P_out_guess -= 1e5
                for i in range(max_retry):
                    try:
                        print(f"Retrying {i+1} of {max_retry}")
                        self.state.outlet_fluid_turbine.updatePS(P=P_out_guess, S=self.state.inlet_fluid.S)
                        break
                    except:
                        P_out_guess -= 1e5
                        retry_count += 1
            #     self.state.outlet_fluid_turbine.updatePT(P=P_out_guess, T=T_in)

            h_turb_out_guess = self.state.outlet_fluid_turbine.H
            T_turb_out_guess = self.state.outlet_fluid_turbine.T




            min_cond_Press = CP.PropsSI("P", "T", min_temp_CO2, "D", density_constraint, "CO2")
            # min_cond_Press = CP.PropsSI(‘P’, ‘T’, min_cond_Temp+273.15, ‘Q’, 0.5, “CO2")
            # min_cond_Press = CP.PropsSI(‘P’, ‘T’, min_cond_Temp+273.15, ‘SMASS’,s_turb_in, “CO2”)
            phase = CP.PhaseSI("P", P_out_guess, "SMASS", s_turb_in, "CO2")

            # print(f"itr:{itr}. P={P_out_guess}, T={T_turb_out_guess}, phase: {phase}")


            steam_Quality = CP.PropsSI("Q", "P", P_out_guess, "HMASS", h_turb_out_guess, "CO2")
            if steam_Quality <= min_quality and steam_Quality != -1:
                print("Constraint for the minimum steam quality met")
                break
            elif T_turb_out_guess < min_temp_CO2:
                print("Constraint for the minimum temperature of the CO2 met")
                break
            elif P_out_guess < min_cond_Press:
                print("Constraint for the density / minimum pressure of the CO2 met")
                break

            else:
                P_out_guess = P_out_guess - 1e5
            itr += 1


        P_turb_out = P_out_guess

        h_turb_out = CP.PropsSI("HMASS", "P", P_turb_out, "SMASS", s_turb_in, "CO2")
        temp_turb_out = CP.PropsSI("T", "P", P_turb_out, "SMASS", s_turb_in, "CO2")
        eta_turbine = 0.78  # (-) Efficiency of the turbine  (Adams et al, 2015)
        X_CO2 = self._X_CO2
        self.state.w_turbine = X_CO2 * self.state.mass_rate * eta_turbine * (h_turb_in - h_turb_out)  # (W)

        print(f"w_turbine: {self.state.w_turbine/1e6}")
        # sys.exit(0)


    def _update_condenser_state(self) -> None:

        print("ENTERING CONDENSER CALCULATIONS:")

        """Step 1: Calculate the condensing heat required"""

        T = self.state.outlet_fluid_turbine.T
        P = self.state.outlet_fluid_turbine.P
        m_dot = self.state.mass_rate
        density_constraint = self.specs.density_constraint
        h_cond_in = self.state.outlet_fluid_turbine.H
        min_Temp_CO2 = self._min_Temp_CO2
        # T = np.array(turb_out_Temperatures)  # Celsius
        # P = np.array(turb_out_Pressures) * 1e5  # Pa
        # m_dot = np.array(m_dot_array)  # kg/s

        cond_in_entropy = CP.PropsSI("SMASS", "HMASS", h_cond_in, "P", P, "CO2")

        den_cond_in = CP.PropsSI('DMASS', 'P', P, 'T', min_Temp_CO2, "CO2")
        # print("Density condensor inlet:")
        # print(f"{den_cond_in} kg/m3")

        h_cond_in = CP.PropsSI('HMASS', 'P', P, 'SMASS', cond_in_entropy, "CO2")
        # print("Enthalpy condensor inlet:")
        # print(f"{h_cond_in} J/kg")

        T_cond_in = CP.PropsSI('T', 'P', P, 'T', T , "CO2")
        # print("Temperature condensor inlet:")
        # print(f"{T_cond_in-273.15} degC")

        Q_cond_in = CP.PropsSI('Q', 'HMASS', h_cond_in, 'P', P, "CO2")
        # print("Quality condensor inlet:")
        # print(f"{Q_cond_in} [-]")

        # print("-----------------")

        h_cond_out = CP.PropsSI('HMASS', 'P', P, 'D', density_constraint, "CO2")
        # print("Enthalpy condensor outlet:")
        # print(f"{h_cond_out} J/kg")

        T_cond_out = CP.PropsSI('T', 'HMASS', h_cond_out, 'D', density_constraint, "CO2")
        # print("Temperature condensor outlet:")
        # print(f"{T_cond_out-273.15} degC")

        condensing_heat_CO2 = (h_cond_in - h_cond_out) * m_dot

        condensing_req_MW = condensing_heat_CO2 / 1e6

        print("Condensing heat required:")
        print(f"{condensing_req_MW} MWth")

        """Step 2: Calculate the heat exchange area"""

        T_CO2_in = T_cond_in
        T_CO2_out = T_cond_out

        # T_water_in = T_cold_water
        # T_water_out = T_hot_water
        T_water_in = self.specs.surface_temperature + self.specs.dT_approach_HX
        T_water_out = T_water_in + self.specs.dT_range_water

        dT_inlet = abs(T_CO2_in - T_water_out)
        dT_outlet = abs(T_CO2_out - T_water_in)

        # Overall Heat Transfer (U) - genGEO (light organic - water)
        U = 500  # [W / m2 * K]

        # Log Mean Temperature Difference (LMTD)
        LMTD = (dT_inlet - dT_outlet) / np.log(dT_inlet / dT_outlet)

        # condensing_heat_CO2 = heat_transfer_coeff * heat_exchange_area * log_mean_temp_diff
        # Q_CO2 = U * A_HX * LMTD
        # A_HX =  Q_CO2 / (U * LMTD)

        A_HX = condensing_heat_CO2 / (U * LMTD)

        print("Heat exchange area for condenser:")
        print(f"{A_HX} m2")

        # self.state.q_cooler = 0. # (W)
        X_CO2 = self._X_CO2
        self.state.q_condenser = m_dot * (h_cond_out - h_cond_in) # (W)
        self.state.w_condenser = X_CO2 * self.state.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)

        #
        # return (condensing_heat_CO2, T_cond_in - 273.15, T_cond_out - 273.15, h_cond_out, A_HX)

        T_cond_in_CO2, T_cond_out_CO2, h_cond_out_CO2 = T_cond_in, T_cond_out, h_cond_out

        # hs_outlet = self.state.outlet_fluid_turbine.H  # Ideal (eta=1.0) enthalpy of outlet fluid (J/kg)
        # h_inlet = self.state.inlet_fluid.H  # (J/kg)
        # X_CO2 = self._X_CO2
        # eta = self.specs.eta_turbine  # (-)
        # h_saturated_vapor = self.condenser_saturated_vapor_h # (J/kg)
        # h_condensed = self.condenser_saturated_liquid_h # (J/kg)
        #
        # h_turbine_outlet = h_inlet - eta * (h_inlet - hs_outlet) # (J/kg)
        #
        # self.state.q_cooler = 0. # (W)
        # self.state.q_condenser = self.state.mass_rate * (h_condensed - h_turbine_outlet) # (W)
        # if h_turbine_outlet > h_saturated_vapor: # desuperheating needed
        #     self.state.q_cooler = self.state.mass_rate * (h_saturated_vapor - h_turbine_outlet)
        #     self.state.q_condenser = self.state.mass_rate * (h_condensed - h_saturated_vapor)
        #     T_turbine_outlet = FluidState.withHP(self._fluid_name, h_turbine_outlet, self.condensation_pressure).T
        #     self._condensation_temperature_range = T_turbine_outlet - self._condensation_temperature
        #
        # self.state.w_cooler = X_CO2 * self.state.q_cooler * self._get_parasitic_power_fraction_cooling() # (W)
        # self.state.w_condenser = X_CO2 * self.state.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)

        """
        
            Cooling tower
        
        """

        P_surface = 101325.0  # Pressure at the surface [Pa]

        print("ENTERING COOLING TOWER CALCULATIONS")

        # print("Surface temperature (in degC): ", T_surface)

        # Create AbstractState objects for water and the refrigerant
        water_state = CP.AbstractState("HEOS", "water")
        condensing_heat_CO2 = condensing_heat_CO2 / 4184  # kcal/s
        # condensing_heat_CO2 = m_dot_water * CP_water * deltaT_water
        # CP_water = 4.186 J/kg*K

        RelHumidity_1 = 0.8  # Relative humidity 1
        RelHumidity_2 = 1.0  # Relative humidity 2 (water-saturated air at the outlet of the cooler)

        T_hot_CO2 = T_cond_in_CO2
        T_cold_CO2 = T_cond_out_CO2

        T_cold_air = self.specs.surface_temperature

        # T_wetBulb = HAPropsSI('T_wb', 'T', T_cold_air + 273.15, 'P', P_surface * 1e5, 'R',
        #                       RelHumidity_1) - 273.15  # degC
        T_wetBulb = HAPropsSI('T_wb', 'T', T_cold_air, 'P', P_surface, 'R', RelHumidity_1)  # K

        T_cold_water = self.specs.surface_temperature + self.specs.dT_approach_HX  # degC
        T_hot_water = T_cold_water + self.specs.dT_range_water  # degC

        T_hot_air = (T_cold_water + T_hot_water) / 2  # degC

        """ Assumption that t2 (air outlet) is approximately (T1-T2)/2. 
        Approximation is from J. B. Dickey, "Managing Waste Heat with the Water
        Cooling Tower, 3rd Ed.", Marley Cooling Tower Co., Mission, Kansas 66202, 1978."""

        # Calculate water enthalpy at the ORC heat exchanger inlet
        # water_state.update(CP.PT_INPUTS, prod_Press, prod_Temp + 273.15)

        water_state.update(CP.QT_INPUTS, 0, T_hot_water)
        Psaturation_T_hot_water = water_state.p()  # Pa

        water_state.update(CP.QT_INPUTS, 0, T_cold_water)
        Psaturation_T_cold_water = water_state.p() # Pa

        water_state.update(CP.QT_INPUTS, 0, T_hot_air)
        Psaturation_T_hot_air = water_state.p()  # Pa

        water_state.update(CP.QT_INPUTS, 0, T_cold_air)
        P_1 = water_state.p() * RelHumidity_1  # Pa
        P_2 = Psaturation_T_cold_water  # Pa

        W_1 = 0.622 * (P_1) / (P_surface - P_1)  # dont know what W_1 is
        W_2 = 0.622 * (RelHumidity_2 * P_2) / (P_surface - RelHumidity_2 * P_2)
        W_sa_1 = 0.622 * (Psaturation_T_hot_water) / (P_surface - Psaturation_T_hot_water)
        W_sa_2 = 0.622 * (Psaturation_T_cold_water) / (P_surface - Psaturation_T_cold_water)

        """Step 2: Calculate air inlet and outlet enthalpies and air-to-water ratio"""

        # h1 = HAPropsSI('H', 'T', T_cold_air + 273.15, 'P', P_surface * 1e5, 'R',
        #                RelHumidity_1) / 4184  # kcal/kg   #SK: Rename h1 and h2
        # h2 = HAPropsSI('H', 'T', T_hot_air + 273.15, 'P', P_surface * 1e5, 'R', RelHumidity_2) / 4184  # kcal/kg
        h1 = HAPropsSI('H', 'T', T_cold_air, 'P', P_surface, 'R',
                       RelHumidity_1) / 4184  # kcal/kg   #SK: Rename h1 and h2
        h2 = HAPropsSI('H', 'T', T_hot_air, 'P', P_surface, 'R', RelHumidity_2) / 4184  # kcal/kg

        # Calculating the volume fill of the cooler from equation 5-9a on page 283. First calculate the
        # log mean enthalpy from equation 5-11 for counterflow.
        # water_state.update(CP.QT_INPUTS, 0, T_hot_water + 273.15)
        water_state.update(CP.QT_INPUTS, 0, T_hot_water)

        h_sa_T_hot_water = water_state.hmass() / 4184  # kcal/kg      #SK: Rename h_sa_...

        # water_state.update(CP.QT_INPUTS, 0, T_cold_water + 273.15)
        water_state.update(CP.QT_INPUTS, 0, T_cold_water)
        h_sa_T_cold_water = water_state.hmass() / 4184  # kcal/kg

        # water_state.update(CP.QT_INPUTS, 0, T_hot_air + 273.15)
        water_state.update(CP.QT_INPUTS, 0, T_hot_air)
        h_sa_T_hot_air = water_state.hmass() / 4184  # kcal/kg

        dh_1 = h_sa_T_hot_water - h2  # kcal/kg    #SK: Rename dh_1...
        dh_2 = h_sa_T_cold_water - h1  # kcal/kg
        del_h_sa = (h_sa_T_hot_water + h_sa_T_cold_water - 2 * h_sa_T_hot_air) / 4  # kcal/kg

        dh_mean = (dh_1 - dh_2) / (2.3 * np.log((dh_1 - del_h_sa) / (dh_2 - del_h_sa)))  # kcal/kg

        # From figure 5-10 on page 284 gives us the correction factor k in the simplified
        # heat balance equation --> k = -0.002 * T2 + 1.01

        k = -0.002 * T_cold_water + 1.01

        # calculate the theoretical air to water ratio

        lamda = (T_hot_water - T_cold_water) / (
                    k * (h2 - h1))  # kg air/ kg water --> (converted h1,2 from J/kg to kcal/kg)
        L_G = 1 / lamda

        """Step 3: Calculate water or air mass flow rate"""
        MassRate_water = condensing_heat_CO2 / (
                    T_hot_water - T_cold_water)  # kg/s   #SK: double check if 'condensing_heat_CO2' in our code is equivalent of 'Q_CO2_cond' in Daniel's code
        MassRate_air = lamda * MassRate_water  # kg/s

        """Step 4: Calculate the demensions of the fill --> need to determine the air velocity, 
        fill area, and water loading """
        # Based on the L. D. Berman book pages 229. the maxiumum valocity in a counter flow
        # mechanical draught cooler is between 1.6 - 1.8 m/s

        velocity_air = 1.8  # m/s
        # density_air = 1 / HAPropsSI('V', 'T', T_cold_air + 273.15, 'P', P_surface * 1e5, 'R', RelHumidity_1)  # kg/m^3
        density_air = 1 / HAPropsSI('V', 'T', T_cold_air, 'P', P_surface, 'R', RelHumidity_1)  # kg/m^3

        A_tf = lamda * MassRate_water / density_air / velocity_air  # m^2, fill area

        # The loading in mechanical draught coolers should be between 5-8 m^3/m^2.hr --> page 278.
        L = 3600 / 1000 * density_air * velocity_air / lamda  # m^3/m^2.hr

        """Step 5: Find beta_p/w or beta_pv/wv; the heat transfer coefficient (square or volumetric). Find volume
        fill based on heat transfer coefficient."""
        # Based on equation 1-81 on page 51, beta_wv can be estimated --> beta_wv = B * (v_a*rho*a)^m * (L/3.6)^n
        # m and n chosen based on the type of slat packing for a splash type cooler.

        beta_wv = 1050 * (velocity_air * density_air) ** 0.62 * (L / 3.6) ** 0.38  # kg/m^2.hr

        # Calculating the volume fill from equation 5-9a
        V_tf = MassRate_water * 3600 * (T_hot_water - T_cold_water) * (1 + 0.8 * (W_1 + W_2 + W_sa_1 + W_sa_2)) / (
                    k * beta_wv * (dh_mean))  # m^3

        # calculating the height of the fill. The correctiong factor , a_h is 1.1-1.3 for small coolers, and
        # 1.0 for large coolers.

        a_h = 1.3
        h_tf = a_h * V_tf / A_tf

        """Step 6: Calculate the Fan Power Requirements"""
        # the resistances in a splash counterflow mechanical draught cooling tower for A_tf <= 60m2 and
        # L between 4-7 is between 50-70.
        zeta = 70
        Z = zeta * velocity_air ** 2 / (2 * 9.81) * density_air
        H = Z

        n = (A_tf // 64) + 1  # number of fans installed. Largest fan is for A = 74 m^2
        eta_fan = 0.6
        eta_elec_drive = 0.8

        V_a = MassRate_air * 3600 / density_air / n
        W_fan_single = V_a * H / (102 * 3600 * eta_fan * eta_elec_drive)  # kW
        W_fan_total = n * W_fan_single
        print("Fan Power Requirement")
        print(f"{W_fan_total} kW")

        """Step 7: Calculate the power requirements for the water pump."""
        # Calculate the valocity of water in the pipe. Assume 16 in pipe (406mm) with a 6mm thickness: ~400mm ID
        epsilon_pipe = 55.e-6  # m
        r_pipe = 0.200  # m

        # water_state.update(CP.PT_INPUTS, P_surface * 1e5, T_hot_air + 273.15)
        water_state.update(CP.PT_INPUTS, P_surface, T_hot_air)
        density_water = water_state.rhomass()  # kg/m^2
        viscosity_water = water_state.viscosity()  # Pa.s

        velocity_water = MassRate_water / density_water / ((r_pipe) ** 2 * np.pi)

        # Hydrostatic Pressure - Rule of Thumb: 10ft or 3m for suction head
        H_suction = 3.0  # m # <---- Asumption needs to made for this value
        H_static = h_tf + H_suction  # m

        # Friction head. Equivilant length is the extra length to incorporate the losses due to fittings
        # and curves in the piping. Currently Assumed to be 10m.
        L_eqv = 10  # m ### <------------ Needs to be designed with some basica assuptions on dimensions.
        L_eqv_total = L_eqv + H_static  # m

        # friction factor
        Re = density_water * 2 * r_pipe * velocity_water / viscosity_water
        relative_roughness = epsilon_pipe / (2 * r_pipe)
        r = relative_roughness  # relative roughness
        f = (-1.8 * np.log10((r / 3.7) ** 1.11 + 6.9 / Re)) ** -2.0
        H_f = L_eqv_total * velocity_water ** 2 * f / 0.4 / 2 / 0.91

        # Kinetic Pressure
        H_v = 0

        # Power Pumping
        eta_pump = 0.85
        W_pump = 1000 * 9.81 * (H_static) / eta_pump / 1000
        print("Pump Power Requirement")
        print(f"{W_pump} kW")

        ######################################################################
        W_tower = W_fan_total + W_pump
        ######################################################################

        """Step 8: Estimate the cost of the cooling tower using Zanker's empirical formula"""
        ## Most cooling tower cost estimation utilises the Zanker empirical formula from
        # A Zanker, "Coolin Tawer Costs from Operating Data," Calculation and Shortcut Handbook
        # (07-X), McGraw-Hill Book Co., New York, pp.47-48. 1967
        #
        # CAPEX [$_1967] = Q /(C*A + 39.2*R - 586)

        # where Q is the heat load in BTU/hr, A is the approach in degF, R is the range in degF,
        # C = 279/(1+0.0335*(85-t_wb)^1.143), and t_wb is the wet bulb temperature in degF

        # t_wb = (HAPropsSI('T_wb', 'T', T_cold_air + 273.15, 'P', P_surface * 1e5, 'R', RelHumidity_1) - 273.15)  # C
        t_wb = HAPropsSI('T_wb', 'T', T_cold_air, 'P', P_surface, 'R', RelHumidity_1)  # C

        # A = (T_cold_water - T_wetBulb) * 9 / 5  # degF
        # R = (T_hot_water - T_cold_water) * 9 / 5  # degF
        A = (T_cold_water - T_wetBulb) * 9 / 5  + 32.# degF
        R = (T_hot_water - T_cold_water) * 9 / 5  + 32.# degF

        Q = condensing_heat_CO2 * 4.148 * 3412.142  # Btu/hr


        A_0 = 8.52  # degF
        Q_0 = 3_465_000_000  # MMBtu/hr

        # C = 279 / (1 + 0.0335 * (85 - (T_wetBulb * 9 / 5 + 32)) ** 1.143)
        C = 279 / (1 + 0.0335 * (85 - ( (T_wetBulb-273.15) * 9 / 5 + 32)) ** 1.143)
        C_1967 = Q_0 * (Q / Q_0) ** 0.8426 / (C * A_0 * (A / A_0) ** 0.4376 + 39.2 * R - 586)  # usd_1967

        CEPCI_2024 = 800.3
        CEPCI_1967 = 109.7

        Cost_CoolingTower = C_1967 * CEPCI_2024 / CEPCI_1967  # USD_2024

        print("Total Cost for Cooling Tower")
        print(f"{Cost_CoolingTower / 1e6} MM USD")

        SpC = Cost_CoolingTower / (condensing_heat_CO2 * 4.148)
        SpC_2002 = SpC * 395.6 / 800.3

        # Tower Effectiveness
        effectiveness = (T_hot_water - T_cold_water) / (T_hot_water - T_wetBulb)

        #     print("T hot water (C): ",T_hot_water)
        #     print("T cold water (C): ", T_cold_water)

        #     print("T hot air (C): ",T_hot_air)
        #     print("T cold air (C): ", T_cold_air)

        #     print("T hot CO2 (C): ",T_hot_CO2)
        #     print("T cold CO2 (C): ", T_cold_CO2)

        #     print("Lamda :", lamda)

        #     print("h hot air (C): ",h2)
        #     print("h cold air (C): ", h1)

        #     print( "Approach temperature CoolingTower(degC): ", T_cold_water-T_cold_air)
        #     print("Approach temperature HeatExchanger (degC): ", T_hot_CO2-T_hot_water)

        #     print("A_tf: ", A_tf)
        #     print("Number of fans: ",n)

        # W_turbine = elec_output
        W_turbine = self.state.w_turbine / 1e6

        print(f"The power needed by the Cooling Tower (fan + pump) is: {W_tower} kW")

        print("------------------------")

        self.state.w_cooler = - W_tower * 1000 # W
        # self.state.w_cooler = W_fan_total * 1000  # W (test)

        # print("Final numbers:")

        # print("Turbine electricity output:")
        # print(f"{round(W_turbine,2)} MWe")

        # print("Total Cooling Tower Power Requirement:")
        # print(f"{round(W_tower/1e3,2)} MWe")

        # print(f"Net Power output:")
        # print(f"{round(W_turbine - W_tower/1e3,2)} MWe")

        return W_turbine, W_fan_total, W_pump, Cost_CoolingTower



    def _update_pump_state(self) -> None:

        eta = self.specs.eta_pump
        X_CO2 = self._X_CO2

        dP_pump = self.state.get_dP_pump()
        if (dP_pump > 20000000):
            dP_pump = random.randint(5000000, 10000000)
        P_pump_outlet = self.condensation_pressure + dP_pump

        h_pump_inlet = self.state.inlet_fluid_pump.H
        h_pump_outlet = self.state.inlet_fluid_pump.H
        if dP_pump > 0:
            try:
                self.state.outlet_fluid_pump.updatePS(P=P_pump_outlet, S=self.state.inlet_fluid_pump.S)
            except:
                logging.warning(f"Failed to update fluid state with PS. Updating with PT instead.")
                self.state.outlet_fluid_pump.updatePT(P=P_pump_outlet, T=self.state.inlet_fluid_pump.T)
            h_pump_outlet = h_pump_inlet + (self.state.outlet_fluid_pump.H - h_pump_inlet) / eta

        self.state.w_pump = -1.0 * X_CO2 *  self.state.mass_rate * (h_pump_outlet - h_pump_inlet)

        # P_inj_inlet = P_pump_outlet + min(0., dP_pump) # if dP_pump <0, then choke.
        P_inj_inlet = P_pump_outlet + max(0., dP_pump)  # if dP_pump <0, then choke.

        try:
            if P_inj_inlet < 0:
                P_inj_inlet = 10000000
            self.state.outlet_fluid.updateHP(H=h_pump_outlet, P=P_inj_inlet)
        except:
            logging.warning(f"Failed to update fluid state with HP. Updating with PT instead.")
            self.state.outlet_fluid.updatePT(P=P_inj_inlet, T=self.state.outlet_fluid_pump.T)

    def _update_net_state(self) -> None:
        self.state.w_net = self.state.w_turbine + self.state.w_cooler + self.state.w_condenser + self.state.w_pump


    def init_state(self, P: float=None, T: float=None) -> None:
        """
        direct CO2 thermosiphon system:
            production_well - turbine - condenser - pump - injection_well
        """

        self.state = SurfaceStateCPGNative()
        if P != None and T != None:
            self.state.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)

        self.state.mass_rate = self.specs.mass_flow_rate

        # self.state.outlet_fluid_turbine = FluidState.withQT(self._fluid_name, Q=1.0, T=self._condensation_temperature)
        # self.state.outlet_fluid_condenser = FluidState.withQT(self._fluid_name, Q=0.0, T=self._condensation_temperature)
        initial_cond_T = min(self._condensation_temperature, T_CRIT_CO2_K)

        self.state.outlet_fluid_turbine = FluidState.withQT(self._fluid_name, Q=1.0, T=initial_cond_T)
        self.state.outlet_fluid_condenser = FluidState.withQT(self._fluid_name, Q=0.0, T=initial_cond_T)
        self.condensation_pressure = self.state.outlet_fluid_condenser.P + self.specs.condensation_pressure_offset
        # self.condenser_saturated_vapor_h = FluidState.withPQ(self._fluid_name, Q=1.0, P=self.condensation_pressure).H
        # self.condenser_saturated_liquid_h = FluidState.withPQ(self._fluid_name, Q=0.0, P=self.condensation_pressure).H
        P = self.state.outlet_fluid_condenser.P + self.specs.condensation_pressure_offset
        # self.state.inlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        # self.state.outlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.state.inlet_fluid_pump = FluidState.withPT(self._fluid_name, P, self.state.outlet_fluid_condenser.T)
        self.state.outlet_fluid_pump = FluidState.withPT(self._fluid_name, P, self.state.outlet_fluid_condenser.T)


        self.state.outlet_fluid = FluidState.copy(self.state.outlet_fluid_pump)


    def overwrite_pump_state(self) -> None:

        self._update_pump_state()

        self._update_net_state()

        self.update_outlet_streams()


    def update(self) -> None:

        # self.update_inlet_state()

        self._update_turbine_power()

        self._update_condenser_state()

        self._update_pump_state()

        self._update_net_state()

        self.update_outlet_streams()


