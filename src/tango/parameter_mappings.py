"""
A module for managing parameter translation mappings.

This module provides centralized access to translation mappings for variable
and parameter names. These mappings are used to translate human-readable
parameter names into corresponding paths or variables in the TANGO system.
"""

TARGET_PARAMETER_MAPPING = {
            "W_NET": "self.tango_instance.workflow.orchestrator.unit.surface.w_net",
            "INLET_TEMP": "self.tango_instance.workflow.orchestrator.unit.surface.inlet_fluid.T",
            "WELL_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_well']",
            "PERMITTING_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_permitting']",
            "EXPLORATION_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_exploration']",
            "SURFACE_PIPES_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_surface_gathering_system']",
            "SURFACE_PLANT_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_surface_plant']",
            "TOTAL_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_total']",
            "ELECTRIC_POWER_AVE": "self.tango_instance.workflow.economic.get_results()['Net_Electricity_Generated_kWe']",
            "THERMAL_POWER_AVE": "self.tango_instance.workflow.economic.get_results()['Net_thermal_power_Generated_kWe']",
            "LCOE": "self.tango_instance.workflow.economic.get_results()['LCOE']",
            "SPCC": "self.tango_instance.workflow.economic.get_results()['SpCC']",
            "DELTA_P_PUMP": "self.tango_instance.workflow.orchestrator.unit.surface._dP_pump",
            "Q_PREHEATER": "self.tango_instance.workflow.orchestrator.unit.surface.q_preheater",
            "Q_BOILER": "self.tango_instance.workflow.orchestrator.unit.surface.q_boiler",
            "Q_DESUPERHEATER": "self.tango_instance.workflow.orchestrator.unit.surface.q_desuperheater",
            "W_TURBINE": "self.tango_instance.workflow.orchestrator.unit.surface.w_turbine",
            "Q_COOLER": "self.tango_instance.workflow.orchestrator.unit.surface.q_cooler",
            "Q_CONDENSER": "self.tango_instance.workflow.orchestrator.unit.surface.q_condenser",
            "W_COOLER": "self.tango_instance.workflow.orchestrator.unit.surface.w_cooler",
            "W_CONDENSER": "self.tango_instance.workflow.orchestrator.unit.surface.w_condenser",
            "DT_LMTD_RECUPERATOR": "self.tango_instance.workflow.orchestrator.unit.surface.dT_LMTD_recuperator",
            "W_DOWNHOLE_PUMP": "self.tango_instance.workflow.orchestrator.unit.surface.w_downhole_pump",
            "DT_LMTD_BOILER": "self.tango_instance.workflow.orchestrator.unit.surface.dT_LMTD_boiler",
            "INJECTION_WELL_OUTLET_T_MIN": "self.tango_instance.workflow._results['injection_well_T'][-1]",
            "PRODUCTION_WELL_OUTLET_T_MIN": "self.tango_instance.workflow._results['production_well_T'][-1]",
            "RESERVOIR_OUTLET_T_MIN": "self.tango_instance.workflow._results['reservoir_T'][-1]",
            "SURFACE_OUTLET_T_MIN": "self.tango_instance.workflow._results['surface_T_out'][-1]",
            "PRODUCTION_WELL_UP_OUTLET_T_MIN": "self.tango_instance.workflow._results['production_well_pump_T'][-1]",
            "INJECTION_WELL_OUTLET_P_MIN": "self.tango_instance.workflow._results['injection_well_P'][-1]",
            "PRODUCTION_WELL_OUTLET_P_MIN": "self.tango_instance.workflow._results['production_well_P'][-1]",
            "RESERVOIR_OUTLET_P_MIN": "self.tango_instance.workflow._results['reservoir_P'][-1]",
            "SURFACE_OUTLET_P_MIN": "self.tango_instance.workflow._results['surface_P_out'][-1]",
            "PRODUCTION_WELL_UP_OUTLET_P_MIN": "self.tango_instance.workflow._results['production_well_pump_P'][-1]",
            "DT_LMTD_PREHEATER": "self.tango_instance.workflow.orchestrator.unit.surface.dT_LMTD_preheater",
            "EXT_TEMP": "self.tango_instance.workflow._results['production_well_T'][-1]"
        }

VARIABLE_PARAMETER_MAPPING = {
            "MASS_FLOW_RATE": "self.tango_instance.specs['schedule']['mass_flow_rate']",
            "mass_flow_rate": "self.tango_instance.specs['schedule']['mass_flow_rate']",
            "rock_density": "self.tango_instance.specs['schedule']['rock_density']",
            "rock_k": "self.tango_instance.specs['schedule']['rock_k']",
            "surface_temperature": "self.tango_instance.specs['schedule']['surface_temperature']",
            "surface_pressure": "self.tango_instance.specs['schedule']['surface_pressure']",
            "thermal_gradient": "self.tango_instance.specs['schedule']['thermal_gradient']",
            "well_spacing": "self.tango_instance.specs['schedule']['well_spacing']",
            "epsilon": "self.tango_instance.specs['schedule']['epsilon']",
            "probability_of_success": "self.tango_instance.specs['schedule']['probability_of_success']",
            "eta_pump": "self.tango_instance.specs['schedule']['eta_pump']",
            "num_cells": "self.tango_instance.specs['schedule']['num_cells']",
            "wellhead_depth": "self.tango_instance.specs['schedule']['wellhead_depth']",
            "brine_density": "self.tango_instance.specs['schedule']['brine_density']",
            "pipe_diameter": "self.tango_instance.specs['schedule']['pipe_diameter']",
            "approach_temperature": "self.tango_instance.specs['schedule']['approach_temperature']",
            "condensation_pressure_offset": "self.tango_instance.specs['schedule']['condensation_pressure_offset']",
            "temperature_range": "self.tango_instance.specs['schedule']['temperature_range']",
            "total_pipe_length": "self.tango_instance.specs['schedule']['total_pipe_length']",
            "eta_turbine": "self.tango_instance.specs['schedule']['eta_turbine']",
            "porosity": "self.tango_instance.specs['schedule']['porosity']",
            "permeability": "self.tango_instance.specs['schedule']['permeability']",
            "initial_pressure": "self.tango_instance.specs['schedule']['initial_pressure']",
            "initial_temperature": "self.tango_instance.specs['schedule']['initial_temperature']",
            "reservoir_depth": "self.tango_instance.specs['schedule']['reservoir_depth']",
            "hydro_static_pressure": "self.tango_instance.specs['schedule']['hydro_static_pressure']",
            "over_pressure_percentage": "self.tango_instance.specs['schedule']['over_pressure_percentage']",
            "thickness": "self.tango_instance.specs['schedule']['thickness']",
            "area": "self.tango_instance.specs['schedule']['area']",
            "net_to_gross_ratio": "self.tango_instance.specs['schedule']['net_to_gross_ratio']",
            "well_eff_diameter": "self.tango_instance.specs['schedule']['well_eff_diameter']",
            "THICKNESS": "self.tango_instance.specs['reservoir']['thickness']"
        }


def get_target_translation(parameter_name: str) -> str:
    """
    Get the translation for a target parameter.

    Parameters
    ----------
    parameter_name : str
        The name of the parameter to translate.

    Returns
    -------
    str
        The corresponding TANGO parameter path.

    Raises
    ------
    KeyError
        If the parameter name is not found in the mapping.
    """
    try:
        return TARGET_PARAMETER_MAPPING[parameter_name]
    except KeyError:
        raise KeyError(f"Target parameter '{parameter_name}' not found in the translation mapping.")


def get_variable_translation(var_name: str) -> str:
    """
    Get the translation for a variable parameter.

    Parameters
    ----------
    var_name : str
        The name of the variable to translate.

    Returns
    -------
    str
        The corresponding TANGO variable path.

    Raises
    ------
    KeyError
        If the variable name is not found in the mapping.
    """
    try:
        return VARIABLE_PARAMETER_MAPPING[var_name]
    except KeyError:
        raise KeyError(f"Variable parameter '{var_name}' not found in the translation mapping.")
