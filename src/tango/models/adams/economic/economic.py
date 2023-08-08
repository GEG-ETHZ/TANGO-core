from tango.core.config import *
from tango.core.constants import *
from tango.models.base import *
from tango.models.adams.economic import *
from tango import utils

from dataclasses import dataclass, asdict
from scipy.interpolate import interp1d
from datetime import datetime

import logging
import os
import pandas as pd
import numpy as np


def get_model_obj(d, name) -> object:
    return None if name not in d else d[name]


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
        self.specs = EconomicSpecsAdams(**specs)
        self.model_dict = model_dict
        self.set_constants()
        self._set_models()
        self.results = dict()


    def _set_models(self) -> None:
        self.set_well_model()
        self.set_permitting_model()
        self.set_exploration_model()
        self.set_surface_pipe_model()
        self.set_surface_power_plant_model()


    def set_well_model(self) -> None:
        inj_well_model = get_model_obj(d=self.model_dict, name='injection_well')
        prd_well_model = get_model_obj(d=self.model_dict, name='production_well')
        if 'production_well_pump' in self.model_dict.keys():
            prd_well_model.well_length += self.model_dict['production_well_pump'].well_length
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI': self.PPI['O&G'],
                                              'multipliers': self.cost_mult['wells']})
        self.well_model = EconModelWells(specs=specs,
                                         injection_well=inj_well_model,
                                         production_well=prd_well_model)


    def set_permitting_model(self) -> None:
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI_permitting': self.PPI['permitting'],
                                              'PPI_OnGs': self.PPI['O&G-s'],
                                              'multipliers': self.cost_mult['wellfield']})
        self.permitting_model = EconModelPermitting(specs=specs,
                                                    well_econ_model=self.well_model)


    def set_exploration_model(self) -> None:
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI': self.PPI['O&G-s'],
                                              'multipliers': self.cost_mult['exploration']})
        self.exploration_model = EconModelExploration(specs=specs,
                                                      well_econ_model=self.well_model)

    def set_surface_pipe_model(self) -> None:
        self.surface_model = get_model_obj(d=self.model_dict, name='surface')
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI': self.PPI['pipes'],
                                              'multipliers': self.cost_mult['pipes']})
        self.surface_pipe_model = EconModelSurfacePipes(specs=specs,
                                                        surface_model=self.surface_model)


    def set_surface_power_plant_model(self) -> None:
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI_PE': self.PPI['PE'],
                                              'PPI_pump': self.PPI['pump'],
                                              'PPI_TG': self.PPI['T-G'],
                                              'PPI_HX': self.PPI['HX'],
                                              'multipliers': self.cost_mult['plant']})
        self.surface_power_plant_model = EconModelSurfacePowerPlant(specs=specs,
                                                                    surface_model=self.surface_model)


    def set_constants(self) -> None:

        # multipliers
        self.cost_year = datetime.strptime(self.specs.start_date, DATETIME_FMT).year
        self.PPI_table = utils.get_table(self.specs.PPI_table, header=1)
        self.cost_mult_table = utils.get_table(self.specs.cost_multiplier_table)

        self.PPI = dict() # producer price index (PPI)
        self.PPI['O&G'] = self.get_PPI_value(col_name="PPI_O&G")
        self.PPI['O&G-s'] = self.get_PPI_value(col_name="PPI_O&G-s")
        self.PPI['permitting'] = self.get_PPI_value(col_name="PPI_Permit")
        self.PPI['pipes'] = self.get_PPI_value(col_name="PPI_Pipe")
        self.PPI['T-G'] = self.get_PPI_value(col_name="PPI_T-G")
        self.PPI['pump'] = self.get_PPI_value(col_name="PPI_Pump")
        self.PPI['PE'] = self.get_PPI_value(col_name="PPI_PE")
        self.PPI['HX'] = self.get_PPI_value(col_name="PPI_HX")

        self.cost_mult = dict() # [X_IC (indirect cost multiplier), X_PC (project contingency multiplier)]
        self.cost_mult['wells'] = self.get_multiplier_values(component="Wells")
        self.cost_mult['wellfield'] = self.get_multiplier_values(component="Well_field")
        self.cost_mult['pipes'] = self.get_multiplier_values(component="Surface_pipes")
        self.cost_mult['plant'] = self.get_multiplier_values(component="Surface_plant")
        self.cost_mult['exploration'] = self.get_multiplier_values(component="Exploration")

        self.specs.project_maturity = self.specs.project_maturity.upper()
        self.specs.active_monitoring_area = self.get_active_monitoring_area()
        self.specs.num_patterns = self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1]


    def set_inlet_state(self, state):
        self.state = state  # surface


    def get_active_monitoring_area(self) -> float:
        if self.specs.fluid_name != 'CO2':
            return 0.
        NX, NY = self.specs.well_pattern_dimens
        if self.specs.well_pattern == 'DOUBLET':
            L_pattern = self.specs.well_spacing # L_pattern = pattern level length
        elif '5SPOT' in self.specs.well_pattern:
            L_pattern = self.specs.well_spacing * np.sqrt(2.0)  # *sqrt(2) to get a side length. self.well_spacing= L of inj-prd pair
        return   (1600. + NX * L_pattern) * (1600. + NY * L_pattern)# Active monitoring area = Area of Review (AoR) + 0.5 mile (800m)


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


    def get_annual_results(self, d) -> None:
        """
        Args:
            results: a dictionary containing time series summary of physic-based simulation results
            -> Get annual/averaged results for LCOE calculation
        """
        dt = self.specs.dt # dt in year
        var_names = [var for var in dir(self.state) if not var.startswith("__")]
        for name in var_names:
            key = f"surface_{name}"
            if key in d:
                try:
                    setattr(self.state, name, np.mean(d[key]) / dt)
                except:
                    continue


    def compute_capex(self) -> None:
        self.results['CAPEX_well'] = self.well_model.execute()
        self.results['CAPEX_permitting'] = self.permitting_model.execute()
        self.results['CAPEX_exploration'] = self.exploration_model.execute()
        self.results['CAPEX_surface_gathering_system'] = self.surface_pipe_model.execute()
        self.results['CAPEX_surface_plant'] = self.surface_power_plant_model.execute(self.state)
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
        d = self.specs.discount_rate
        t = self.specs.num_tsteps * self.specs.dt
        CF = self.specs.capacity_factor
        F_OM = self.specs.OPEX_cost_fraction
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
        W_net_total = self.surface_power_plant_model.W_net_total
        self.results['Net_Electricity_Generated_kWe'] = W_net_total * W_TO_KW
        self.results['LCOE'] = self.get_LCOE(self.results['CAPEX_total'], W_net_total)
        self.results['SpCC'] = self.get_specific_capital_cost(self.results['CAPEX_total'], W_net_total)
        self.results['RF'] = self.results['LCOE'] / self.results['SpCC']


    def execute(self, results: dict) -> None:

        self.get_annual_results(results)

        self.compute_capex()

        self.compute_LCOE()
