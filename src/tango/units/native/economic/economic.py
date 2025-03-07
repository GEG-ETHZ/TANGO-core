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
from tango.core.abstracts.unit import *
from tango.units.dataclasses import CommonSpecs, field
from tango.units.native.economic import *
from tango import utils
from dataclasses import dataclass


def get_unit_obj(d, name) -> object:
    """
    Retrieves an object from a dictionary by name.

    Args:
        d (dict): Dictionary containing objects.
        name (str): Key name to search in the dictionary.

    Returns:
        object: The object corresponding to the key, or `None` if the key is not found.

    Example:
        >>> obj = get_unit_obj(my_dict, "unit_name")
    """
    return None if name not in d else d[name]


class Struct:
    """
    A simple class to allow dynamic attribute assignment.

    Methods:
        __init__(**entries):
            Initializes the struct with attributes from a dictionary.
    """

    def __init__(self, **entries):
        """
        Initializes the Struct object.

        Args:
            **entries: Key-value pairs to set as attributes.

        Example:
            >>> s = Struct(a=1, b=2)
            >>> print(s.a, s.b)
        """
        self.__dict__.update(entries)


def merge_object_dict(obj, dict) -> object:
    """
    Merges an object's attributes with a dictionary and returns a new `Struct`.

    Args:
        obj (object): The object to merge.
        dict (dict): The dictionary to merge.

    Returns:
        Struct: A new object containing attributes from both `obj` and `dict`.

    Example:
        >>> merged = merge_object_dict(my_obj, {"key": "value"})
    """
    d = vars(obj) | dict
    return Struct(**d)


@dataclass
class EconomicSpecsNative(CommonSpecs):
    """
    Specifications for the economic model in TANGO.
    """
    costs: dict = field(default_factory=dict)
    project_maturity: str = None
    type: str = ''
    PPI_table: str = 'PPI_Table.xlsx'
    cost_multiplier_table: str = 'cost_multiplier_table.xlsx'
    OPEX_cost_fraction: float = 0.045
    discount_rate: float = 0.096
    capacity_factor: float = 0.9
    monitoring_well_diameter: float = 0.216
    monitoring_well_probability_of_success: float = 1.0
    num_characterization_wells: int = 2
    horizontal_well_cost_multiplier: float = 1.15
    well_cost_model: str = 'gengeo'
    wellbore_solver: str = 'external'
    main_product: str = 'electricity'
    electricity_price: float = 0.25
    heat_price: float = 0.05

    def __post_init__(self):
        """
        Validates required fields and data consistency after initialization.

        Raises:
            RuntimeError: If required fields are missing.
            ValueError: If well pattern dimensions are invalid or unsupported.
        """
        required_fields = ['project_maturity', 'type']
        for s in required_fields:
            if getattr(self, s, None) is None:
                raise RuntimeError(f"Required parameter: {s} is not found.")
        if not isinstance(self.well_pattern_dimens, list):
            raise ValueError("Invalid data type for 'well_pattern_dimens'. Must be a list of two integers.")
        if len(self.well_pattern_dimens) != 2:
            raise ValueError("Invalid 'well_pattern_dimens'. Must contain exactly two integers.")
        if self.well_pattern in ['DOUBLET', 'AGS']:
            if self.well_pattern_dimens[0] > 1 and self.well_pattern_dimens[1] > 1:
                raise ValueError(f"Multiple well_pattern: {self.well_pattern} is not supported.")

        self.validate_costs()

    def validate_costs(self):
        """
        Validates the costs block configuration.
        Raises errors for invalid configurations.
        """
        if not self.costs:
            self.costs = {}

        for cost_name, config in self.costs.items():
            model_type = config.get('type', 'default')

            if model_type not in ['default', 'custom', 'custom_entire_pp', 'custom_cost_breakdown']:
                raise ValueError(
                    f"Invalid cost model type '{model_type}' for '{cost_name}'. "
                    f"Allowed types are 'default' or 'custom'."
                )

            if model_type == 'custom' and 'function' not in config:
                raise ValueError(
                    f"Cost model for '{cost_name}' is set to 'custom', but no 'function' is specified."
                )


class EconomicStateNative:
    """
    Represents the economic state based on Adams et al. (2015).

    Attributes:
        mass_rate (float): Mass flow rate.
        inlet_fluid (FluidState): Inlet fluid state.
        outlet_fluid (FluidState): Outlet fluid state.
    """

    def __init__(self):
        """
        Initializes the EconomicStateNative object.
        """
        self.mass_rate: float = 0.0
        self.inlet_fluid: FluidState
        self.outlet_fluid: FluidState


class EconomicUnitNative(Unit):
    """
    Represents an economic unit in the TANGO framework.

    Attributes:
        unit_dict (dict): Dictionary mapping unit types to their corresponding units.
        state_dict (dict): Dictionary mapping unit types to their states.
        _results (dict): Dictionary to store economic results.
    """

    def __init__(self, specs: dict, nodes) -> None:
        """
        Initializes the EconomicUnitNative object.

        Args:
            specs (dict): Specifications for the economic unit.
            nodes (dict): Nodes representing units in the system.
        """
        super().__init__('econ', specs)
        self._compatibility_check()
        self._process_specs(nodes)
        self._set_unit_dict(nodes)
        self._initialize_constants()
        self._initialize_units()
        self._results = dict()

    def _compatibility_check(self) -> dict:
        """
        Checks compatibility of units with the economic model.

        Raises:
            ValueError: If an unsupported unit type is encountered.
        """
        for key in self.specs['graph']['nodes'].keys():
            unit_name = self.specs['graph']['nodes'][key]['unit']
            unit_type = self.specs['graph']['nodes'][key]['type']
            if unit_name.lower() not in UNIT_OPTIONS_FOR_ECONUNIT['native'][unit_type]:
                raise ValueError(f"Unit type: {unit_name} (node_id='{key}') is not supported.")

    def _process_specs(self, nodes) -> None:
        """
        Processes and validates specifications for the economic unit.

        Args:
            nodes (dict): Nodes representing units in the system.
        """
        combined_specs = self.specs['common'] | self.specs['economic'] | {'costs': self.specs.get('costs', {})}

        costs = combined_specs.get('costs', {})
        for cost_name, cost_config in costs.items():
            if ((cost_config.get('type') == 'custom_entire_pp') or cost_config.get('type') == 'custom'):
                function_name = cost_config.get('function')
                if not function_name:
                    raise ValueError(f"Cost model for '{cost_name}' is 'custom / custom_entire_pp' but no function is specified.")

                function_def = self.specs.get('functions', {}).get(function_name)
                if not function_def:
                    raise ValueError(f"Function '{function_name}' for '{cost_name}' is not defined in the 'functions' block.")

                cost_config['function_def'] = function_def

            elif (cost_config.get('type') == 'custom_cost_breakdown'):

                if 'breakdown' in cost_config:
                    for sub_cost, sub_function in cost_config['breakdown'].items():
                        sub_function_def = self.specs.get('functions', {}).get(sub_function)
                        if not sub_function_def:
                            raise ValueError(
                                f"Function '{sub_function}' for breakdown '{sub_cost}' in '{cost_name}' is not defined in the 'functions' block."
                            )
                        cost_config['breakdown'][sub_cost] = {'function': sub_function, 'function_def': sub_function_def}

        combined_specs['costs'] = costs
        self.specs = EconomicSpecsNative.from_dict(combined_specs)

    def _set_unit_dict(self, nodes) -> None:
        """
        Initializes dictionaries for unit and state mapping.

        Args:
            nodes (dict): Nodes representing units in the system.
        """
        self.unit_dict = dict()
        self.state_dict = dict()
        for id in nodes:
            self.unit_dict[nodes[id]['type']] = []
            self.state_dict[nodes[id]['type']] = []
        for id in nodes:
            self.unit_dict[nodes[id]['type']].append(nodes[id]['unit'])
            self.state_dict[nodes[id]['type']].append(nodes[id]['unit'])

    def _initialize_units(self) -> None:
        """
        Initializes components such as wells, permitting, exploration, and surface power plants.
        """
        self._instantiate_well_unit()
        self._instantiate_permitting_unit()
        self._instantiate_exploration_unit()
        self._instantiate_surface_pipe_unit()
        self._instantiate_surface_power_plant_unit()

    def _instantiate_well_unit(self) -> None:
        """
        Instantiates the well unit for the economic model.

        Combines specifications with cost multipliers and PPI values.
        """
        specs = merge_object_dict(
            self.specs,
            dict={'PPI': self._PPI['O&G'], 'multipliers': self._cost_mult['wells']}
        )
        self._well_unit = EconUnitWells(specs=specs, unit_dict=self.unit_dict)

    def _instantiate_permitting_unit(self) -> None:
        """
        Instantiates the permitting unit for the economic model.

        Logic:
        - Merges economic specifications with relevant PPI and multiplier values.
        - Initializes the `EconUnitPermitting` instance.

        Example:
            >>> self._instantiate_permitting_unit()
        """
        specs = merge_object_dict(self.specs, dict={
            'PPI_permitting': self._PPI['permitting'],
            'PPI_OnGs': self._PPI['O&G-s'],
            'multipliers': self._cost_mult['wellfield']
        })
        self._permitting_unit = EconUnitPermitting(specs=specs, well_econ_unit=self._well_unit)

    def _instantiate_exploration_unit(self) -> None:
        """
        Instantiates the exploration unit for the economic model.

        Logic:
        - Merges economic specifications with relevant PPI and multiplier values.
        - Initializes the `EconUnitExploration` instance.

        Example:
            >>> self._instantiate_exploration_unit()
        """
        specs = merge_object_dict(self.specs, dict={
            'PPI': self._PPI['O&G-s'],
            'multipliers': self._cost_mult['exploration']
        })
        self._exploration_unit = EconUnitExploration(specs=specs, well_econ_unit=self._well_unit)

    def _instantiate_surface_pipe_unit(self) -> None:
        """
        Instantiates the surface pipe unit for the economic model.

        Logic:
        - Retrieves surface unit and state from the unit dictionary.
        - Merges economic specifications with relevant PPI and multiplier values.
        - Initializes the `EconUnitSurfacePipes` instance.

        Example:
            >>> self._instantiate_surface_pipe_unit()
        """
        self.surface_unit, self.surface_state = None, None
        if 'surface' in self.unit_dict.keys():
            self.surface_unit = self.unit_dict['surface'][0]
            self.surface_state = self.state_dict['surface'][0]
        specs = merge_object_dict(self.specs, dict={
            'PPI': self._PPI['pipes'],
            'multipliers': self._cost_mult['pipes']
        })
        self._surface_pipe_unit = EconUnitSurfacePipes(specs=specs, unit=self.surface_unit)

    def _instantiate_surface_power_plant_unit(self) -> None:
        """
        Instantiates the surface power plant unit for the economic model.

        Logic:
        - Merges economic specifications with relevant PPI and multiplier values.
        - Initializes the `EconUnitSurfacePowerPlant` instance.

        Example:
            >>> self._instantiate_surface_power_plant_unit()
        """
        specs = merge_object_dict(self.specs, dict={
            'PPI_PE': self._PPI['PE'],
            'PPI_pump': self._PPI['pump'],
            'PPI_TG': self._PPI['T-G'],
            'PPI_HX': self._PPI['HX'],
            'multipliers': self._cost_mult['plant']
        })
        self._surface_power_plant_unit = EconUnitSurfacePowerPlant(specs=specs, unit=self.surface_unit)

    def _initialize_constants(self) -> None:
        """
        Initializes constants and economic parameters for the model.

        Logic:
        - Extracts cost year, PPI values, and multipliers from input tables.
        - Calculates additional economic parameters such as project maturity and active monitoring area.

        Example:
            >>> self._initialize_constants()
        """
        self._cost_year = datetime.strptime(self.specs.start_date, DATETIME_FMT).year
        self._PPI_table = utils.get_table(self.specs.PPI_table, header=1)
        self._cost_mult_table = utils.get_table(self.specs.cost_multiplier_table)

        self._PPI = dict()  # Producer Price Index (PPI)
        self._PPI['O&G'] = self.get_PPI_value(col_name="PPI_O&G")
        self._PPI['O&G-s'] = self.get_PPI_value(col_name="PPI_O&G-s")
        self._PPI['permitting'] = self.get_PPI_value(col_name="PPI_Permit")
        self._PPI['pipes'] = self.get_PPI_value(col_name="PPI_Pipe")
        self._PPI['T-G'] = self.get_PPI_value(col_name="PPI_T-G")
        self._PPI['pump'] = self.get_PPI_value(col_name="PPI_Pump")
        self._PPI['PE'] = self.get_PPI_value(col_name="PPI_PE")
        self._PPI['HX'] = self.get_PPI_value(col_name="PPI_HX")

        self._cost_mult = dict()  # Cost multipliers
        self._cost_mult['wells'] = self._get_multiplier_values(component="Wells")
        self._cost_mult['wellfield'] = self._get_multiplier_values(component="Well_field")
        self._cost_mult['pipes'] = self._get_multiplier_values(component="Surface_pipes")
        self._cost_mult['plant'] = self._get_multiplier_values(component="Surface_plant")
        self._cost_mult['exploration'] = self._get_multiplier_values(component="Exploration")

        self.specs.project_maturity = self.get_project_maturity()
        self.specs.active_monitoring_area = self.get_active_monitoring_area()
        self.specs.num_patterns = self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1]

    def get_project_maturity(self) -> str:
        """
        Retrieves the project maturity from specifications.

        Returns:
            str: The project maturity in uppercase.

        Raises:
            RuntimeError: If the `project_maturity` field is not found in the specifications.

        Example:
            >>> maturity = self.get_project_maturity()
        """
        if self.specs.project_maturity is None:
            raise RuntimeError("Required parameter: 'project_maturity' is not found in specs")
        return self.specs.project_maturity.upper()

    def get_active_monitoring_area(self) -> float:
        """
        Calculates the active monitoring area based on the well pattern and fluid type.

        Returns:
            float: The active monitoring area in square meters.

        Logic:
        - Depends on well pattern and well spacing for specific configurations.
        - If the fluid type is not CO2 or the well pattern is AGS, the area is set to zero.

        Example:
            >>> area = self.get_active_monitoring_area()
        """
        if self.specs.fluid_name != 'CO2' or self.specs.well_pattern == 'AGS':
            return 0.0
        NX, NY = self.specs.well_pattern_dimens
        if self.specs.well_pattern == 'DOUBLET':
            L_pattern = self.specs.well_spacing
            NY = 0
        elif '5SPOT' in self.specs.well_pattern:
            L_pattern = self.specs.well_spacing * np.sqrt(2.0)
        return (1600.0 + NX * L_pattern) * (1600.0 + NY * L_pattern)

    def get_PPI_value(self, col_name: str) -> float:
        """
        Retrieves a Producer Price Index (PPI) value for a specific column and year.

        Args:
            col_name (str): The name of the column in the PPI table.

        Returns:
            float: The interpolated or extrapolated PPI value for the specified column.

        Raises:
            ValueError: If the PPI value cannot be found.

        Example:
            >>> ppi = self.get_PPI_value("PPI_O&G")
        """
        df = self._PPI_table
        year = self._cost_year
        val = float(interp1d(df.Year, df[col_name], bounds_error=False, kind='linear')(year))
        if np.isnan(val):
            logging.warning(f"A value {year} is outside the interpolation range in PPI_table. Extrapolating a value for {col_name}.")
            return float(interp1d(df.Year, df[col_name], bounds_error=False, fill_value='extrapolate', kind='linear')(year))
        return val

    def _get_multiplier_values(self, component: str) -> list:
        """
        Retrieves cost multiplier values for a specific component.

        Args:
            component (str): The name of the component to retrieve multipliers for.

        Returns:
            list: A tuple containing the indirect cost multiplier (`X_IC`) and project contingency multiplier (`X_PC`).

        Example:
            >>> multipliers = self._get_multiplier_values("Wells")
        """
        df = self._cost_mult_table
        idx = df.index[df['Component'] == component]
        return df['X_IC'].iloc[idx].iloc[0], df['X_PC'].iloc[idx].iloc[0]

    def _compute_annual_results(self, d) -> None:
        """
        Computes annual and averaged results for Levelized Cost of Energy (LCOE) calculation.

        Args:
            d (dict): A dictionary containing time series summary of physics-based simulation results.

        Logic:
        - Iterates through key performance indicators (KPIs) such as thermal power, pump pressure, and heat rates.
        - Calculates time-weighted averages for each KPI based on time steps (`dt_list`).

        Notes:
        - Updates the surface state attributes with the computed annual/averaged values.

        Example:
            >>> self._compute_annual_results(results_dict)
        """
        self.total_time = sum(self.specs.dt_list)
        var_names = ['thermal_power', 'dP_pump', 'dT_LMTD_boiler', 'dT_LMTD_preheater', 'dT_LMTD_recuperator',
                     'dT_range', 'dT_range_CT', 'q_boiler', 'q_condenser', 'q_cooler', 'q_desuperheater',
                     'q_preheater', 'q_recuparator', 'q_recuperator', 'w_condenser', 'w_cooler',
                     'w_downhole_pump', 'w_net', 'w_pump', 'w_turbine']
        for name in var_names:
            key = f"surface_{name}"
            if key in d:
                try:
                    weighted_sum = 0
                    for i in range(len(self.specs.dt_list)):
                        weighted_sum += self.specs.dt_list[i] / self.total_time * d[key][i]
                    setattr(self.surface_state, name, weighted_sum)
                except:
                    continue

    def _compute_capex(self, evaluated_funcs, results) -> None:
        """
        Computes the Capital Expenditure (CAPEX) for all units.

        Logic:
        - Executes CAPEX calculations for well, permitting, exploration, surface gathering system, and surface plant.
        - Summarizes the total CAPEX.

        Updates:
        - `self._results` dictionary with individual and total CAPEX values.

        Example:
            >>> self._compute_capex()
        """
        self._results['CAPEX_well'] = self._well_unit.execute(evaluated_funcs)
        self._results['CAPEX_permitting'] = self._permitting_unit.execute(evaluated_funcs)
        self._results['CAPEX_exploration'] = self._exploration_unit.execute(evaluated_funcs)
        self._results['CAPEX_surface_gathering_system'] = self._surface_pipe_unit.execute(evaluated_funcs)
        self.calculate_and_set_average(results)
        if (self._surface_power_plant_unit._surface_unit.__class__.__name__ == 'SurfaceUnitFlexiblePP'):
            self._results['CAPEX_surface_plant'] = self._surface_power_plant_unit.execute(self.surface_state, evaluated_funcs, self.average_fp_result)
        else:
            self._results['CAPEX_surface_plant'] = self._surface_power_plant_unit.execute(self.surface_state, evaluated_funcs)
        val = sum(self._results[key] for key in self._results.keys())
        self._results['CAPEX_total'] = val

    def calculate_and_set_average(self, results):

        self.average_fp_result = {}
        for key in results.keys():
            if isinstance(results[key], list) and all(isinstance(x, (int, float)) for x in results[key]):
                average_value = sum(results[key]) / len(results[key]) if results[key] else 0
                self.average_fp_result[key] = [average_value]

    def _get_LCOE(self, w: float, w2: float) -> float:
        """
        Calculates the Simple Levelized Cost of Energy (sLCOE).

        Args:
            W (float): Net electricity produced [We].
            w2 (float): Auxiliary parameter for operational expenditure adjustment.

        Returns:
            float: The sLCOE in $/kWh.

        Formula:
            LCOE = CAPEX * (CRF + F_OM) / (W * Capacity_Factor * Total_Hours)

            Where:
            - CAPEX: Total capital expenditure [$]
            - CRF: Capital recovery factor
            - F_OM: OPEX cost fraction adjusted for auxiliary loads
            - W: Net electricity produced
            - Capacity_Factor: Plant capacity factor
            - Total_Hours: Annual operational hours

        Notes:
        - If CAPEX or W is non-positive, returns `NaN`.

        Example:
            >>> lcoe = self._get_LCOE(1e6, 1e3)
        """
        if (self.specs.main_product == 'electricity'):
            main_product = w
            bi_product = w2
            price = self.specs.heat_price
        elif (self.specs.main_product == 'heat'):
            main_product = w2
            bi_product = w
            price = self.specs.electricity_price

        CAPEX = self._results['CAPEX_total']
        if CAPEX <= 0:
            return np.nan
        d = self.specs.discount_rate
        t = self.total_time
        CF = self.specs.capacity_factor
        F_OM = self.specs.OPEX_cost_fraction - bi_product / 1000 * 8760 * price / CAPEX
        CRF = d * (1. + d) ** t / ((1. + d) ** t - 1.0)  # Capital recovery factor
        return CAPEX * (CRF + F_OM) / (main_product * W_TO_KW * CF * YEAR_TO_HOUR)


    def _get_specific_capital_cost(self, W: float) -> float:
        """
        Computes the specific capital cost per unit electricity capacity.

        Args:
            W (float): Net electricity produced [We].

        Returns:
            float: Specific capital cost in $/kWe.

        Notes:
        - If CAPEX or W is non-positive, returns `NaN`.

        Example:
            >>> spcc = self._get_specific_capital_cost(1e6)
        """
        CAPEX = self._results['CAPEX_total']
        if CAPEX <= 0 or W <= 0:
            return np.nan
        return CAPEX / (W * W_TO_KW)

    def _compute_LCOE(self) -> None:
        """
        Computes the Levelized Cost of Energy (LCOE) and related metrics.

        Updates:
        - `Net_Electricity_Generated_kWe`: Total net electricity generated [kWe].
        - `Net_thermal_power_Generated_kWe`: Total net thermal power generated [kWe].
        - `LCOE`: Levelized cost of energy in $/kWh.
        - `SpCC`: Specific capital cost in $/kWe.

        Example:
            >>> self._compute_LCOE()
        """
        W_net_total = self._surface_power_plant_unit.get_net_W_total()
        W_net_thermal = self._surface_power_plant_unit._W_net_thermal
        self._results['Net_Electricity_Generated_kWe'] = W_TO_KW * W_net_total
        self._results['Net_thermal_power_Generated_kWe'] = W_TO_KW * W_net_thermal
        self._results['LCOE'] = self._get_LCOE(W_net_total, W_net_thermal)
        self._results['SpCC'] = self._get_specific_capital_cost(W_net_total)

    def get_results(self) -> dict:
        """
        Retrieves the computed results.

        Returns:
            dict: A dictionary containing computed economic results.

        Example:
            >>> results = self.get_results()
        """
        return self._results

    def execute(self, results: dict, evaluated_funcs) -> None:
        """
        Executes the economic calculations.

        Steps:
        - Computes annual results.
        - Calculates CAPEX.
        - Computes LCOE.

        Args:
            results (dict): A dictionary containing physics-based simulation results.

        Example:
            >>> self.execute(simulation_results)
        """
        self._compute_annual_results(results)
        self._compute_capex(evaluated_funcs, results)
        self._compute_LCOE()
