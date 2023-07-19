from tango.models.base import *
from tango.models.base.model import *
from dataclasses import dataclass
from tango.core.config import *
from tango.core.constants import *

import logging
import os
import pandas as pd
import numpy as np
from pathlib import Path
from scipy.interpolate import interp1d
from datetime import datetime


@dataclass
class EconomicSpecsAdams(CommonSpecs):
    PPI_table: str = 'PPI_table.xlsx'
    cost_multiplier_table: str = 'cost_multiplier_table.xlsx'
    OPEX_cost_fraction: float = 0.045 # Operation and maintainance (O&M) (or OPEX) fraction (=C_O&M / C_geothermal_plant)
    discount_rate: float = 0.096
    capacity_factor: float = 0.9
    monitoring_well_diameter: float = 0.216 # m
    monitoring_well_probability_of_success: float = 1.0
    num_characterization_wells: int = 2
    project_maturity: str =  ''


class EconomicStateAdams(EconomicState):
    """Economics state based on Adams et. al (2015)."""
    def __init__(self):
        EconomicState.__init__(self)


class EconomicModelAdams(EconomicModel):

    def __init__(self, specs: dict, model_dict: dict) -> None:
        self.specs = dict()
        self.results = dict()
        self.specs['economic'] = EconomicSpecsAdams(**specs)
        for key in model_dict.keys():
            self.specs[key] = model_dict[key].specs

        self.fluid_name = self.specs['reservoir'].fluid_name
        self.reservoir_depth = self.specs['reservoir'].reservoir_depth
        self.well_pattern = self.specs['reservoir'].well_pattern.upper()
        self.well_spacing = self.specs['reservoir'].well_spacing # inj-prod pair spacing
        # self.num_patterns_sqrt = self.specs['reservoir'].num_patterns_sqrt
        # self.num_patterns = self.num_patterns_sqrt ** 2
        self.well_pattern_dimens = self.specs['reservoir'].well_pattern_dimens
        self.num_patterns = self.well_pattern_dimens[0] * self.well_pattern_dimens[1]

        self.characterization_well_pos =  self.specs['production_well'].probability_of_success
        self.characterization_well_diameter = self.specs['production_well'].diameter

        self.set_surface()

        self.lifetime = self.specs['economic'].num_tsteps * self.specs['economic'].dt
        self.cost_year = datetime.strptime(self.specs['economic'].start_date, '%Y-%m-%d').year
        self.injector_mass_flow_rate = self.specs['economic'].mass_flow_rate
        self.project_maturity = self.specs['economic'].project_maturity.upper()
        self.monitoring_well_diameter = self.specs['economic'].monitoring_well_diameter
        self.monitoring_well_probability_of_success = self.specs['economic'].monitoring_well_probability_of_success
        self.num_characterization_wells = self.specs['economic'].num_characterization_wells
        self.OPEX_cost_fraction = self.specs['economic'].OPEX_cost_fraction
        self.discount_rate = self.specs['economic'].discount_rate
        self.capacity_factor = self.specs['economic'].capacity_factor

        self.check_inputs()

        self.set_constants()


    def set_surface(self) -> None: #TODO: improve
        self.surface_pipe_diameter = self.specs['surface'].pipe_diameter
        if self.fluid_name == 'CO2':
            self.surface_ambient_temperature = self.specs['surface'].surface_temperature
            self.surface_approach_temperature = self.specs['surface'].approach_temperature
            self.surface_temperature_range = self.specs['surface'].temperature_range
            self.surface_cooling_tower_mode = self.specs['surface'].cooling_mode
        else:
            pass



    def check_inputs(self) -> None:
        if self.well_pattern not in WELL_PATTERN_OPTIONS:
            raise ValueError(f"Well pattern: {self.well_pattern} is not supported.")
        if len(self.well_pattern_dimens) != 2:
            raise ValueError(f"Something wrong with well_pattern_dimens: {self.well_pattern}. Input a list with two integer elements.")
        if bool(list(filter(lambda x: not isinstance(x, int), self.well_pattern_dimens))):
            raise ValueError(f"Something wrong with well_pattern_dimens: {self.well_pattern}. Input a list with two integer elements.")
        if self.well_pattern == 'DOUBLET':
            if bool(list(filter(lambda x: x > 1, self.well_pattern_dimens))):
                raise ValueError(f"Multiple well_patterns is not supported for: {self.well_pattern}.")
        if not self.project_maturity:
            raise ValueError(f"project_maturity in 'economic' section is not defined.")
        if self.project_maturity not in PROJECT_MATURITY_OPTIONS:
            raise ValueError(f"project_maturity: {self.project_maturity} is not supported.")
        if self.fluid_name not in FLUID_NAME_OPTIONS:
            raise ValueError(f"fluid_name: {self.fluid_name} is not supported.")
        if self.fluid_name == 'CO2':
            if self.surface_cooling_tower_mode not in COOLING_MODE_OPTIONS:
                raise ValueError(f"surface_cooling_tower_mode: {self.surface_cooling_tower_mode} is not supported.")


    def set_constants(self) -> None:

        # multipliers
        self.PPI_table = self.get_table(self.specs['economic'].PPI_table, header=1)
        self.cost_mult_table = self.get_table(self.specs['economic'].cost_multiplier_table)

        self.PPI = dict() # producer price index (PPI)
        self.PPI['O&G'] = self.get_PPI_value(col_name="PPI_O&G")
        self.PPI['O&G-s'] = self.get_PPI_value(col_name="PPI_O&G-s")
        self.PPI['permitting'] = self.get_PPI_value(col_name="PPI_Permit")
        self.PPI['pipes'] = self.get_PPI_value(col_name="PPI_Pipe")
        self.PPI['T-G'] = self.get_PPI_value(col_name="PPI_T-G")
        self.PPI['pump'] = self.get_PPI_value(col_name="PPI_Pump")
        self.PPI['PE'] = self.get_PPI_value(col_name="PPI_PE")

        self.cost_mult = dict() # [X_IC (indirect cost multiplier), X_PC (project contingency multiplier)]
        self.cost_mult['wells'] = self.get_multiplier_values(component="Wells")
        self.cost_mult['wellfield'] = self.get_multiplier_values(component="Well_field")
        self.cost_mult['pipes'] = self.get_multiplier_values(component="Surface_pipes")
        self.cost_mult['plant'] = self.get_multiplier_values(component="Surface_plant")
        self.cost_mult['exploration'] = self.get_multiplier_values(component="Exploration")

        self.set_coeffs()

        # fluid type dependent parameters
        self.active_monitoring_area = self.get_active_monitoring_area()
        self.turbine_cost_multiplier = self.get_turbine_cost_multiplier()
        self.pump_material_cost_multiplier = self.get_pump_material_cost_multiplier()
        self.tower_design_coefficient = self.get_tower_design_coefficient()


    def set_coeffs(self) -> None:
        if self.fluid_name == 'H2O':
            return
        # coefficients for BAC regression models
        if self.surface_cooling_tower_mode == 'WET':
            self.coeffs_cooling = [5.58e3, 0., -1.77e1, 1.96e2]
            self.coeffs_condensing = [4.08e3, -1.54e-2, -1.24e1, 0.]
        else: # 'DRY':
            self.coeffs_cooling = [7.31e3, 0., 0., 1.23e3]
            self.coeffs_condensing = [1.91e3, 0., 0., 0.]


    def set_inlet_state(self, state: ModelState):
        self.state = state  # surface


    def get_active_monitoring_area(self) -> float:
        if self.fluid_name != 'CO2':
            return 0.
        NX, NY = self.well_pattern_dimens
        if self.well_pattern == 'DOUBLET':
            L_pattern = self.well_spacing # L_pattern = pattern level length
        elif '5SPOT' in self.well_pattern:
            L_pattern = self.well_spacing * np.sqrt(2.0)  # *sqrt(2) to get a side length. self.well_spacing= L of inj-prd pair
        return   (1600. + NX * L_pattern) * (1600. + NY * L_pattern)# Active monitoring area = Area of Review (AoR) + 0.5 mile (800m)


    def get_turbine_cost_multiplier(self) -> float:
        if self.fluid_name != 'CO2':
            return 1.0
        return 1.2


    def get_pump_material_cost_multiplier(self) -> float:
        if self.fluid_name != 'H2O':
            return 2.09 # stailes steel (suitable for non-water fluids, such as CO2)
        return 1.0 # Iron (suitable for non-corrosive liquids, such as water or glycol)


    def get_tower_design_coefficient(self) -> float:
        if self.fluid_name == 'H2O':
            return 1.0
        design = self.specs['surface'].cooling_tower_design.upper()
        if design == 'CLOSED':
            if self.fluid_name == 'CO2':
                return 1.2
            else:
                return 1.0
        elif design == 'OPEN':
            if self.fluid_name == 'H2O':
                return 0.252
            else:
                raise ValueError(f"Surface cooling tower design: {design} with fluid: {self.fluid_name} is not supported")
        else:
            raise ValueError(f"Surface cooling tower design: {design} is not supported")


    @staticmethod
    def get_table(fname: str, header:int = 0) -> pd.DataFrame:
        path = fname
        if not os.path.isabs(fname):
            path = os.path.join(Path(__file__).parent.parent.parent.parent.parent, 'data', fname)
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} not found.")
        try:
            table = pd.read_excel(path, header=header)
        except:
            raise RuntimeError(f"Failed to read {path}.")
        return table


    def get_PPI_value(self, col_name: str) -> float:
        df = self.PPI_table
        year = self.cost_year
        val = float(interp1d(df.Year, df[col_name], bounds_error=False, kind='linear')(year))
        if np.isnan(val):
            logging.warning(f"A value {year} is outside the interpolation range in PPI_table. Extrapolating a value for {col_name}.")
            return float(interp1d(df.Year, df[col_name], bounds_error=False, fill_value='extrapolate', kind='linear')(year))
        return val


    def get_multiplier_values(self, component: str) -> list:
        df = self.cost_mult_table
        idx = df.index[df['Component']==component]
        return df['X_IC'].iloc[idx].iloc[0], df['X_PC'].iloc[idx].iloc[0]

    """
    +==================================================================================================================-
        section: wells
    +==================================================================================================================-
    """

    def get_well_length(self, well_specs: dict) -> float:
        if well_specs.well_length is not None:
            return well_specs.well_length #TODO: add treatment for pump length
        return self.reservoir_depth / np.cos(np.deg2rad(well_specs.vertical_deviation))


    def get_num_wells(self) -> list: # per pattern
        NX, NY = self.well_pattern_dimens
        if self.well_pattern == 'DOUBLET':
            num_total_inj = 1
            num_total_prd = 1
        elif self.well_pattern == '5SPOT':
            num_total_inj = (NX+1) * (NY+1)
            num_total_prd = NX * NY
        elif self.well_pattern == 'INVERTED_5SPOT':
            num_total_inj = NX * NY
            num_total_prd = (NX+1) * (NY+1)
        else:
            raise NotImplementedError(f"well_pattern: {self.well_pattern} is not supported")
        return num_total_inj, num_total_prd


    def get_dC_CO2_well(self, PPI: float, X_IC: float, X_PC: float, d: float, L: float, fluid_name: str) -> float:
        if fluid_name != "CO2":
            return 0
        return X_IC * X_PC * PPI * (265. * d * L + 133. * L)


    def get_individual_well_cost(self, L: float, d: float, pos: float, fluid_name: str = "H2O") -> float:
        PPI = self.PPI['O&G']
        X_IC, X_PC = self.cost_mult['wells']
        C_well = X_IC * X_PC * PPI * (0.105 * L ** 2 + 1776. * d * L + 275300.) # well cost (base line)
        dC_CO2_well = self.get_dC_CO2_well(PPI, X_IC, X_PC, d, L, fluid_name) # adjustment for CO2
        return (C_well + dC_CO2_well) / pos


    def get_wells_cost_by_type(self, well_type: str, num_wells: int) -> float:
        if well_type not in self.specs:
            return 0
        if well_type == 'injection_well' and self.project_maturity == 'BROWN_FIELD':
            return 0
        well_specs = self.specs[well_type]
        well_length = self.get_well_length(well_specs)
        return num_wells * self.get_individual_well_cost(L=well_length,
                                                         d=well_specs.diameter,
                                                         pos=well_specs.probability_of_success,
                                                         fluid_name=self.fluid_name)


    def get_wells_cost(self) -> float:
        num_total_inj, num_total_prod = self.get_num_wells()
        C_inj = self.get_wells_cost_by_type(well_type='injection_well', num_wells=num_total_inj)
        C_prd = self.get_wells_cost_by_type(well_type='production_well', num_wells=num_total_prod)
        return C_inj + C_prd

    """
    +==================================================================================================================-
        section: field development / permitting
    +==================================================================================================================-
    """

    def get_dCO2_permitting(self, PPI: float, X_IC:float, X_PC: float, AMA: float) -> float:
        if self.fluid_name != 'CO2':
            return 0
        return X_IC * X_PC * PPI * 45000. * (1. / 1.e6) * AMA


    def get_dCO2_monitoring(self, PPI: float, X_IC:float, X_PC: float, AMA: float) -> float:
        if self.fluid_name != 'CO2':
            return 0
        C_surface_monitoring = X_IC * X_PC * PPI * 138000. * (1. / 1.e6) * AMA
        C_monitoring_well = self.num_patterns * self.get_individual_well_cost(L=self.reservoir_depth,
                                                                              d=self.monitoring_well_diameter,
                                                                              pos=self.monitoring_well_probability_of_success)
        return C_surface_monitoring + C_monitoring_well

    def get_permitting_cost(self) -> float:

        if self.project_maturity == 'BROWN_FIELD':
            return 0

        PPI = self.PPI['permitting']
        X_IC, X_PC = self.cost_mult['wellfield']
        AMA = self.active_monitoring_area

        C_permitting = X_IC * X_PC * PPI * 665700.

        dC_CO2_permitting = self.get_dCO2_permitting(self.PPI['permitting'], X_IC, X_PC, AMA)
        dC_CO2_monitoring = self.get_dCO2_monitoring(self.PPI['O&G-s'], X_IC, X_PC, AMA)

        return C_permitting + dC_CO2_permitting + dC_CO2_monitoring

    """
    +==================================================================================================================-
        section: exploration
    +==================================================================================================================-
    """

    def get_dCO2_modeling(self, PPI: float, X_IC: float, X_PC: float) -> float:
        if self.fluid_name != 'CO2':
            return 0
        return X_IC * X_PC * PPI * 44800 * (1/1e6) * self.active_monitoring_area


    def get_dCO2_characterization(self) -> float:
        if self.fluid_name != 'CO2':
            return 0
        num_wells = self.num_characterization_wells
        pos = self.characterization_well_pos
        C_characterization_well = self.get_individual_well_cost(L=self.reservoir_depth,
                                                               d=self.characterization_well_diameter,
                                                               pos=1.0)
        return 0.2 * num_wells * C_characterization_well / pos


    def get_exploration_cost(self) -> float:

        if self.project_maturity == 'BROWN_FIELD':
            return 0

        PPI = self.PPI['O&G-s']
        X_IC, X_PC = self.cost_mult['exploration']

        C_modeling = X_IC * X_PC * PPI * 508000

        dC_CO2_modeling = self.get_dCO2_modeling(PPI, X_IC, X_PC)
        dC_CO2_characterization = self.get_dCO2_characterization()

        return C_modeling + dC_CO2_modeling + dC_CO2_characterization

    """
    +==================================================================================================================-
        section: surface pipes
    +==================================================================================================================-
    """

    def get_surface_pipe_total_length(self) -> float:
        # L_single_pair = min(self.well_spacing, self.surface_pipe_length_per_well_pair) # single inj-prod pair
        L_single_pair = self.well_spacing  # single inj-prod pair
        if self.well_pattern == 'DOUBLET':
            return L_single_pair
        elif '5SPOT' in self.well_pattern:
            return self.num_patterns * 4 * L_single_pair
        else:
            raise NotImplementedError(f"well_pattern: {self.well_pattern} is not supported")


    def get_pipe_cost(self) -> float:
        if 'surface' not in self.specs:
            return 0
        PPI = self.PPI['pipes']
        X_IC, X_PC = self.cost_mult['pipes']
        L = self.get_surface_pipe_total_length()
        D = self.surface_pipe_diameter
        return X_PC * X_IC * PPI * (2205. * D**2 + 134.) * L

    """
    +==================================================================================================================-
        section: surface power plant
    +==================================================================================================================-
    """

    def get_num_well_pairs_per_pattern(self) -> int:
        if self.well_pattern == 'DOUBLET':
            return 1
        elif '5SPOT' in self.well_pattern:
            return 4
        else:
            raise NotImplementedError(f"well_pattern: {self.well_pattern} is not supported")


    def process_surface_state(self) -> None:

        mult = self.get_num_well_pairs_per_pattern() * self.num_patterns

        self.Q_condenser_total = mult * self.state.q_condenser  # used
        self.Q_cooler_total = mult * self.state.q_cooler
        self.Q_preheater_total = mult * self.state.q_preheater
        self.Q_boiler_total = mult * self.state.q_boiler
        self.Q_desuperheater_total = mult * self.state.q_desuperheater  # used

        self.W_pump_total = mult * self.state.w_pump # used
        self.W_turbine_total = mult * self.state.w_turbine  # used
        self.W_cooler_total = mult * self.state.w_cooler # used
        self.W_condenser_total = mult * self.state.w_condenser # used
        self.W_net_total = self.W_pump_total + self.W_turbine_total + self.W_cooler_total + self.W_condenser_total


    def get_turbine_generator_cost(self) -> float:
        PPI = self.PPI['T-G']
        S_T_fluid = self.turbine_cost_multiplier
        W_turbine = self.W_turbine_total
        return 0.67 * PPI * (S_T_fluid * 2830 * (W_turbine / 1.e3) ** 0.745 + 3680 * (W_turbine / 1.e3) ** 0.617)


    def get_pump_inj_cost(self) -> float:
        PPI = self.PPI['pump']
        W_pump = self.W_pump_total
        S_pump = self.pump_material_cost_multiplier
        return PPI * S_pump * 1750 * (1.34*-1*(W_pump/1e3))**0.7


    def BAC_regression_model(self, coeffs: list) -> float:
        """
        Baltimore Aircoil Specific (BAC) regression model for cooling and condensing costs
        """
        a, b, c, d = coeffs
        T_ambient = self.surface_ambient_temperature
        dT_approach = self.surface_approach_temperature
        dT_range = self.surface_temperature_range
        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach+dT_range)


    def get_C_cooling(self):
        return self.BAC_regression_model(coeffs=self.coeffs_cooling)


    def get_C_condensing(self):
        return self.BAC_regression_model(coeffs=self.coeffs_condensing)


    def get_cooling_condensing_tower_cost(self) -> float:

        TDC = self.tower_design_coefficient
        PPI = self.PPI['PE']

        Q_cooler = self.Q_desuperheater_total
        Q_condenser = self.Q_condenser_total
        W_pump = self.W_pump_total
        W_turbine = self.W_turbine_total
        
        C_cooling = self.get_C_cooling() # specific cooling tower cost ($/kW)
        C_condensing = self.get_C_condensing() # specific condensing tower cost ($/kW)

        Q_Ref_BAC = 1.0e6 # nominal heat load (=1.0 MWth)
        F_cooling = abs(Q_cooler) / (abs(Q_cooler) + abs(Q_condenser) + 1e-10)
        C_Ref_BAC = PPI * Q_Ref_BAC * TDC * (F_cooling * (C_cooling / 1e3) + (1 - F_cooling) * (C_condensing / 1e3))
        return C_Ref_BAC * (abs(Q_cooler+Q_condenser)/Q_Ref_BAC)**0.8



    def get_power_plant_cost(self) -> float:

        if 'surface' not in self.specs:
            return 0

        X_IC, X_PC = self.cost_mult['plant']
        X_SE = 1.39 # secondary equipment cost (control system, pumps, valuves, buildings, etc.)
        X_CL = 0.58 # construction labor cost
        X_CM = 0.11 # construction material cost
        X_ST = 0.00 # sales tax
        X_F = 0.04  # equipment freight

        self.process_surface_state()

        C_turbine_generator = self.get_turbine_generator_cost()

        C_pump_inj = self.get_pump_inj_cost()

        C_cooling_condensing_tower = self.get_cooling_condensing_tower_cost()

        C_plant_PEC = C_turbine_generator + C_pump_inj + C_cooling_condensing_tower # primary equipment cost (PEC)

        C_plant_TEC = X_SE * C_plant_PEC # total equipment cost (TEC)

        C_plant_BEC = C_plant_TEC * (1 + X_CL + X_CM + X_ST + X_F) # bare erected cost (BEC)

        return X_PC * X_IC * C_plant_BEC # total surface plant cost (TPC)

    """
    +==================================================================================================================+
        section: executives
    +==================================================================================================================+
    """

    def get_annual_results(self, d) -> None:
        """

        Args:
            results: a dictionary containing time series summary of physic-based simulation results

            -> Get annual/averaged results for LCOE calculation

        """
        dt = self.specs['economic'].dt # dt in year
        var_names = [var for var in dir(self.state) if not var.startswith("__")]
        for name in var_names:
            key = f"surface_{name}"
            if key in d:
                try:
                    # getattr(self.state, name)
                    setattr(self.state, name, np.mean(d[key]) / dt)
                except:
                    continue

                # attr = np.mean(d[key]) / dt # 1: to skip initial condition. Overwrite some attributes


    def compute_capex(self) -> None:
        self.results['CAPEX_well'] = self.get_wells_cost()
        self.results['CAPEX_permitting'] = self.get_permitting_cost()
        self.results['CAPEX_exploration'] = self.get_exploration_cost()
        self.results['CAPEX_surface_gathering_system'] = self.get_pipe_cost()
        self.results['CAPEX_surface_plant'] = self.get_power_plant_cost()
        val = 0
        for key in self.results.keys():
             val += self.results[key]
        self.results['CAPEX_total'] = val


    def get_LCOE(self, CAPEX: float, W: float) -> float:
        """

        Args:
            CAPEX: total capital expenditure [$]
            W: net electricity generated (annual) [We]

        Returns: Simple Levelized Cost of Energy (sLCOE) [$/kWh]
                 source: https://www.nrel.gov/analysis/tech-lcoe-documentation.html

        """
        if CAPEX <= 0 or W <= 0:
            return np.nan
        d = self.discount_rate
        t = self.lifetime
        CF = self.capacity_factor
        F_OM = self.OPEX_cost_fraction
        CRF = d * (1. + d) ** t / ( (1. + d) ** t - 1.) # capital recovery factor
        return CAPEX * (CRF + F_OM) / (W * W_TO_KW * CF * YEAR_TO_HOUR)


    def get_specific_capital_cost(self, CAPEX: float, W: float) -> float:
        """

        Args:
            CAPEX: total capital expenditure [$]
            W: electricity produced [We]

        Returns: Specific capital cost [$/kWe]

        """
        if CAPEX <= 0 or W <= 0:
            return np.nan
        return CAPEX / (W * W_TO_KW)


    def compute_LCOE(self) -> None:
        self.results['Net_Electricity_Generated_kWe'] = self.W_net_total * W_TO_KW
        self.results['LCOE'] = self.get_LCOE(self.results['CAPEX_total'], self.W_net_total)
        self.results['SpCC'] = self.get_specific_capital_cost(self.results['CAPEX_total'], self.W_net_total)
        self.results['RF'] = self.results['LCOE'] / self.results['SpCC']


    def execute(self, results: dict) -> None:

        self.get_annual_results(results)

        self.compute_capex()

        self.compute_LCOE()
