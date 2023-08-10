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
        self._model_dict = model_dict
        self._initialize_constants()
        self._initialize_models()
        self._results = dict()


    def _initialize_models(self) -> None:
        self._instantiate_well_model()
        self._instantiate_permitting_model()
        self._instantiate_exploration_model()
        self._instantiate_surface_pipe_model()
        self._instantiate_surface_power_plant_model()


    def _instantiate_well_model(self) -> None:
        inj_well_model = get_model_obj(d=self._model_dict, name='injection_well')
        prd_well_model = get_model_obj(d=self._model_dict, name='production_well')
        if 'production_well_pump' in self._model_dict.keys():
            L = self._model_dict['production_well_pump'].get_well_length()
            prd_well_model.update_well_length(pump_well_length=L)
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI': self._PPI['O&G'],
                                        'multipliers': self._cost_mult['wells']})
        self._well_model = EconModelWells(specs=specs,
                                          injection_well=inj_well_model,
                                          production_well=prd_well_model)


    def _instantiate_permitting_model(self) -> None:
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI_permitting': self._PPI['permitting'],
                                              'PPI_OnGs': self._PPI['O&G-s'],
                                              'multipliers': self._cost_mult['wellfield']})
        self._permitting_model = EconModelPermitting(specs=specs,
                                                     well_econ_model=self._well_model)


    def _instantiate_exploration_model(self) -> None:
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI': self._PPI['O&G-s'],
                                              'multipliers': self._cost_mult['exploration']})
        self._exploration_model = EconModelExploration(specs=specs,
                                                       well_econ_model=self._well_model)

    def _instantiate_surface_pipe_model(self) -> None:
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI': self._PPI['pipes'],
                                        'multipliers': self._cost_mult['pipes']})
        self._surface_pipe_model = EconModelSurfacePipes(specs=specs,
                                                         surface_model=get_model_obj(d=self._model_dict, name='surface'))


    def _instantiate_surface_power_plant_model(self) -> None:
        specs = utils.merge_object_dict(self.specs,
                                        dict={'PPI_PE': self._PPI['PE'],
                                              'PPI_pump': self._PPI['pump'],
                                              'PPI_TG': self._PPI['T-G'],
                                              'PPI_HX': self._PPI['HX'],
                                              'multipliers': self._cost_mult['plant']})
        self._surface_power_plant_model = EconModelSurfacePowerPlant(specs=specs,
                                                                     surface_model=get_model_obj(d=self._model_dict, name='surface'))


    def _initialize_constants(self) -> None:

        # multipliers
        self._cost_year = datetime.strptime(self.specs.start_date, DATETIME_FMT).year
        self._PPI_table = utils.get_table(self.specs.PPI_table, header=1)
        self._cost_mult_table = utils.get_table(self.specs.cost_multiplier_table)

        self._PPI = dict() # producer price index (PPI)
        self._PPI['O&G'] = self.get_PPI_value(col_name="PPI_O&G")
        self._PPI['O&G-s'] = self.get_PPI_value(col_name="PPI_O&G-s")
        self._PPI['permitting'] = self.get_PPI_value(col_name="PPI_Permit")
        self._PPI['pipes'] = self.get_PPI_value(col_name="PPI_Pipe")
        self._PPI['T-G'] = self.get_PPI_value(col_name="PPI_T-G")
        self._PPI['pump'] = self.get_PPI_value(col_name="PPI_Pump")
        self._PPI['PE'] = self.get_PPI_value(col_name="PPI_PE")
        self._PPI['HX'] = self.get_PPI_value(col_name="PPI_HX")

        self._cost_mult = dict() # [X_IC (indirect cost multiplier), X_PC (project contingency multiplier)]
        self._cost_mult['wells'] = self._get_multiplier_values(component="Wells")
        self._cost_mult['wellfield'] = self._get_multiplier_values(component="Well_field")
        self._cost_mult['pipes'] = self._get_multiplier_values(component="Surface_pipes")
        self._cost_mult['plant'] = self._get_multiplier_values(component="Surface_plant")
        self._cost_mult['exploration'] = self._get_multiplier_values(component="Exploration")

        self.specs.project_maturity = self.specs.project_maturity.upper()
        self.specs.active_monitoring_area = self.get_active_monitoring_area()
        self.specs.num_patterns = self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1]


    def set_inlet_state(self, state):
        self._state = state  # surface


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
        df = self._PPI_table
        year = self._cost_year
        val = float(interp1d(df.Year, df[col_name], bounds_error=False, kind='linear')(year))
        if np.isnan(val):
            logging.warning(f"A value {year} is outside the interpolation range in PPI_table. Extrapolating a value for {col_name}.")
            return float(interp1d(df.Year, df[col_name], bounds_error=False, fill_value='extrapolate', kind='linear')(year))
        return val


    def _get_multiplier_values(self, component: str) -> list:
        df = self._cost_mult_table
        idx = df.index[df['Component']==component]
        return df['X_IC'].iloc[idx].iloc[0], df['X_PC'].iloc[idx].iloc[0]


    def _get_annual_results(self, d) -> None:
        """
        Args:
            results: a dictionary containing time series summary of physic-based simulation results
            -> Get annual/averaged results for LCOE calculation
        """
        dt = self.specs.dt # dt in year
        var_names = [var for var in dir(self._state) if not var.startswith("__")]
        for name in var_names:
            key = f"surface_{name}"
            if key in d:
                try:
                    setattr(self._state, name, np.mean(d[key]) / dt)
                except:
                    continue


    def _compute_capex(self) -> None:
        self._results['CAPEX_well'] = self._well_model.execute()
        self._results['CAPEX_permitting'] = self._permitting_model.execute()
        self._results['CAPEX_exploration'] = self._exploration_model.execute()
        self._results['CAPEX_surface_gathering_system'] = self._surface_pipe_model.execute()
        self._results['CAPEX_surface_plant'] = self._surface_power_plant_model.execute(self._state)
        val = 0
        for key in self._results.keys():
             val += self._results[key]
        self._results['CAPEX_total'] = val


    def _get_LCOE(self, W: float) -> float:
        """

        Args:
            W: electricity produced [We]

        Returns: Simple Levelized Cost of Energy (sLCOE) [$/kWh]
                 source: https://www.nrel.gov/analysis/tech-lcoe-documentation.html


        """
        CAPEX = self._results['CAPEX_total'] # total capital expenditure [$]
        if CAPEX <= 0 or W <= 0:
            return np.nan
        d = self.specs.discount_rate
        t = self.specs.num_tsteps * self.specs.dt
        CF = self.specs.capacity_factor
        F_OM = self.specs.OPEX_cost_fraction
        CRF = d * (1. + d) ** t / ( (1. + d) ** t - 1.) # capital recovery factor
        return CAPEX * (CRF + F_OM) / (W * W_TO_KW * CF * YEAR_TO_HOUR)


    def _get_specific_capital_cost(self, W: float) -> float:
        """

        Args:
            W: electricity produced [We]

        Returns: Specific capital cost [$/kWe]

        """
        CAPEX = self._results['CAPEX_total'] # total capital expenditure [$]
        if CAPEX <= 0 or W <= 0:
            return np.nan
        return CAPEX / (W * W_TO_KW)


    def _compute_LCOE(self) -> None:
        W_net_total = self._surface_power_plant_model.get_net_W_total()
        self._results['Net_Electricity_Generated_kWe'] = W_TO_KW * W_net_total
        self._results['LCOE'] = self._get_LCOE(W_net_total)
        self._results['SpCC'] = self._get_specific_capital_cost(W_net_total)


    def get_results(self) -> dict:
        return self._results


    def execute(self, results: dict) -> None:

        self._get_annual_results(results)

        self._compute_capex()

        self._compute_LCOE()
