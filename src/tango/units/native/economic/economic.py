from dataclasses import dataclass, asdict
from scipy.interpolate import interp1d
from datetime import datetime
from enum import Enum
import logging
import os
import pandas as pd
import numpy as np

from tango.core.config import *
from tango.core.constants import *
from tango.units.native.base import *
from tango.units.native.common import CommonSpecs
from tango.units.native.economic import *
from tango import utils


def get_unit_obj(d, name) -> object:
    return None if name not in d else d[name]


class Struct:
    def __init__(self, **entries):
        self.__dict__.update(entries)

def merge_object_dict(obj, dict) -> object:
    d = vars(obj) | dict
    return Struct(**d)


@dataclass
class EconomicSpecsNative(CommonSpecs):
    project_maturity: str = None
    type: str = ''
    PPI_table: str = 'PPI_Table.xlsx'
    cost_multiplier_table: str = 'cost_multiplier_table.xlsx'
    OPEX_cost_fraction: float = 0.045 # Operation and maintainance (O&M) (or OPEX) fraction (=C_O&M / C_geothermal_plant)
    discount_rate: float = 0.096
    capacity_factor: float = 0.9
    monitoring_well_diameter: float = 0.216 # m
    monitoring_well_probability_of_success: float = 1.0
    num_characterization_wells: int = 2
    horizontal_well_cost_multiplier: float = 1.15
    num_reusable_injectors: int = 0
    num_reusable_producers: int = 0
    def __post_init__(self):
        required_fields = ['project_maturity', 'type']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")
        if not isinstance(self.well_pattern_dimens, list):
            raise ValueError(f"Invalid data type found for 'well_pattern_dimens'. Please input a list with two integer elements instead.")
        if len(self.well_pattern_dimens) != 2:
            raise ValueError(f"Invalid 'well_pattern_dimens' found. Please input a list with two integer elements instead.")
        if self.well_pattern in ['DOUBLET', 'AGS']:
            if self.well_pattern_dimens[0] > 1 and self.well_pattern_dimens[1] > 1:
                raise ValueError(f"Multiple well_pattern: {self.well_pattern} is not supported")


class EconomicStateNative(UnitStateNative):
    """Economics state based on Adams et. al (2015)."""
    def __init__(self):
        UnitStateNative.__init__(self)


class EconomicUnitNative(UnitNative):

    def __init__(self, specs: dict, nodes) -> None:
        super().__init__('econ', specs)
        self._compatibility_check()
        self._process_specs(nodes)
        self._set_unit_dict(nodes)
        self._initialize_constants()
        self._initialize_units()
        self._results = dict()

    def _compatibility_check(self) -> dict:
        for key in self.specs['graph']['nodes'].keys():
            unit_name = self.specs['graph']['nodes'][key]['unit']
            unit_type = self.specs['graph']['nodes'][key]['type']
            if unit_name.lower() not in UNIT_OPTIONS_FOR_ECONUNIT['native'][unit_type]:
                raise ValueError(f"Unit type: {_type} (node_id='{key}') is not supported.")


    def _process_specs(self, nodes) -> dict:
        self.specs = EconomicSpecsNative.from_dict(self.specs['common'] | self.specs['economic'])


    def _set_unit_dict(self, nodes) -> None:
        self.unit_dict = dict()
        self.state_dict = dict()
        for id in nodes:
            self.unit_dict[nodes[id]['type']] = []
            self.state_dict[nodes[id]['type']] = []
        for id in nodes:
            self.unit_dict[nodes[id]['type']].append(nodes[id]['unit'])
            self.state_dict[nodes[id]['type']].append(nodes[id]['unit'].state)


    def _initialize_units(self) -> None:
        self._instantiate_well_unit()
        self._instantiate_permitting_unit()
        self._instantiate_exploration_unit()
        self._instantiate_surface_pipe_unit()
        self._instantiate_surface_power_plant_unit()


    def _instantiate_well_unit(self) -> None:
        specs = merge_object_dict(self.specs,
                                  dict={'PPI': self._PPI['O&G'],
                                  'multipliers': self._cost_mult['wells']})
        self._well_unit = EconUnitWells(specs=specs,
                                        unit_dict=self.unit_dict)


    def _instantiate_permitting_unit(self) -> None:
        specs = merge_object_dict(self.specs,
                                  dict={'PPI_permitting': self._PPI['permitting'],
                                        'PPI_OnGs': self._PPI['O&G-s'],
                                        'multipliers': self._cost_mult['wellfield']})
        self._permitting_unit = EconUnitPermitting(specs=specs,
                                                   well_econ_unit=self._well_unit)


    def _instantiate_exploration_unit(self) -> None:
        specs = merge_object_dict(self.specs,
                                  dict={'PPI': self._PPI['O&G-s'],
                                        'multipliers': self._cost_mult['exploration']})
        self._exploration_unit = EconUnitExploration(specs=specs,
                                                     well_econ_unit=self._well_unit)

    def _instantiate_surface_pipe_unit(self) -> None:
        self.surface_unit, self.surface_state = None, None
        if 'surface' in self.unit_dict.keys():
            self.surface_unit = self.unit_dict['surface'][0]
            self.surface_state = self.state_dict['surface'][0]
        specs = merge_object_dict(self.specs,
                                  dict={'PPI': self._PPI['pipes'],
                                  'multipliers': self._cost_mult['pipes']})
        self._surface_pipe_unit = EconUnitSurfacePipes(specs=specs,
                                                       unit=self.surface_unit)


    def _instantiate_surface_power_plant_unit(self) -> None:
        specs = merge_object_dict(self.specs,
                                  dict={'PPI_PE': self._PPI['PE'],
                                        'PPI_pump': self._PPI['pump'],
                                        'PPI_TG': self._PPI['T-G'],
                                        'PPI_HX': self._PPI['HX'],
                                        'multipliers': self._cost_mult['plant']})
        self._surface_power_plant_unit = EconUnitSurfacePowerPlant(specs=specs,
                                                                     unit=self.surface_unit)


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

        self.specs.project_maturity = self.get_project_maturity()
        self.specs.active_monitoring_area = self.get_active_monitoring_area()
        self.specs.num_patterns = self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1]


    def get_project_maturity(self):
        if self.specs.project_maturity == None:
            raise RuntimeError(f"Required parameter: 'project_maturity' is not found in specs")
        return self.specs.project_maturity.upper()


    def get_active_monitoring_area(self) -> float:
        if self.specs.fluid_name != 'CO2' or self.specs.well_pattern == 'AGS':
            return 0.
        NX, NY = self.specs.well_pattern_dimens
        if self.specs.well_pattern == 'DOUBLET':
            L_pattern = self.specs.well_spacing # L_pattern = pattern level length
            NY = 0
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


    def _compute_annual_results(self, d) -> None:
        """
        Args:
            results: a dictionary containing time series summary of physic-based simulation results
            -> Get annual/averaged results for LCOE calculation
        """
        dt = self.specs.dt # dt in year
        var_names = [var for var in dir(self.surface_state) if not var.startswith("__")]
        for name in var_names:
            key = f"surface_{name}"
            if key in d:
                try:
                    setattr(self.surface_state, name, np.mean(d[key]) / dt)
                except:
                    continue


    def _compute_capex(self) -> None:
        self._results['CAPEX_well'] = self._well_unit.execute()
        self._results['CAPEX_permitting'] = self._permitting_unit.execute()
        self._results['CAPEX_exploration'] = self._exploration_unit.execute()
        self._results['CAPEX_surface_gathering_system'] = self._surface_pipe_unit.execute()
        self._results['CAPEX_surface_plant'] = self._surface_power_plant_unit.execute(self.surface_state)
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
        W_net_total = self._surface_power_plant_unit.get_net_W_total()
        self._results['Net_Electricity_Generated_kWe'] = W_TO_KW * W_net_total
        self._results['LCOE'] = self._get_LCOE(W_net_total)
        self._results['SpCC'] = self._get_specific_capital_cost(W_net_total)


    def get_results(self) -> dict:
        return self._results


    def execute(self, results: dict) -> None:

        self._compute_annual_results(results)

        self._compute_capex()

        self._compute_LCOE()

#TODO: current genGEO-based econ unit is too complicated. Implement a simpler method as a native econ unit.
#      Then move this whole package to tango.units.genGEO.economic
