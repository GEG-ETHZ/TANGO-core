"""
A module for managing parameter translation mappings.

This module provides centralized access to translation mappings for variable
and parameter names. These mappings are used to translate human-readable
parameter names into corresponding paths or variables in the TANGO system.
"""

TARGET_PARAMETER_MAPPING = {
            "W_NET": "self.tango_instance.workflow.orchestrator.unit.surface.w_net",
            "W_COOLER": "self.tango_instance.workflow.orchestrator.unit.surface.w_cooler",
            "W_CONDENSER": "self.tango_instance.workflow.orchestrator.unit.surface.w_condenser",
            "W_TURBINE": "self.tango_instance.workflow.orchestrator.unit.surface.w_turbine",
            "W_PUMP": "self.tango_instance.workflow.orchestrator.unit.surface.w_pump",
            "W_DOWNHOLE_PUMP": "self.tango_instance.workflow.orchestrator.unit.surface.w_downhole_pump",
            "ELECTRIC_POWER_AVE": "self.tango_instance.workflow.economic.get_results()['Net_Electricity_Generated_kWe']",
            "THERMAL_POWER_AVE": "self.tango_instance.workflow.economic.get_results()['Net_thermal_power_Generated_kWe']",
            "WELL_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_well']",
            "PERMITTING_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_permitting']",
            "EXPLORATION_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_exploration']",
            "SURFACE_PIPES_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_surface_gathering_system']",
            "SURFACE_PLANT_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_surface_plant']",
            "TOTAL_CAPEX": "self.tango_instance.workflow.economic.get_results()['CAPEX_total']",
            "LCOE": "self.tango_instance.workflow.economic.get_results()['LCOE']",
            "SPCC": "self.tango_instance.workflow.economic.get_results()['SpCC']",
            "DELTA_P_PUMP": "self.tango_instance.workflow.orchestrator.unit.surface._dP_pump",
            "Q_PREHEATER": "self.tango_instance.workflow.orchestrator.unit.surface.q_preheater",
            "Q_BOILER": "self.tango_instance.workflow.orchestrator.unit.surface.q_boiler",
            "Q_DESUPERHEATER": "self.tango_instance.workflow.orchestrator.unit.surface.q_desuperheater",
            "Q_COOLER": "self.tango_instance.workflow.orchestrator.unit.surface.q_cooler",
            "Q_CONDENSER": "self.tango_instance.workflow.orchestrator.unit.surface.q_condenser",
            "DT_LMTD_RECUPERATOR": "self.tango_instance.workflow.orchestrator.unit.surface.dT_LMTD_recuperator",
            "DT_LMTD_BOILER": "self.tango_instance.workflow.orchestrator.unit.surface.dT_LMTD_boiler",
            "DT_LMTD_PREHEATER": "self.tango_instance.workflow.orchestrator.unit.surface.dT_LMTD_preheater",
            "INJECTION_WELL_OUTLET_T_MIN": "self.tango_instance.workflow._results['injection_well_T'][-1]",
            "PRODUCTION_WELL_OUTLET_T_MIN": "self.tango_instance.workflow._results['production_well_T'][-1]",
            "RESERVOIR_OUTLET_T_MIN": "self.tango_instance.workflow._results['reservoir_T'][-1]",
            "SURFACE_OUTLET_T_MIN": "self.tango_instance.workflow._results['surface_T_out'][-1]",
            "PRODUCTION_WELL_UP_OUTLET_T_MIN": "self.tango_instance.workflow._results['production_well_pump_T'][-1]",
            "INJECTION_WELL_OUTLET_P_MIN": "self.tango_instance.workflow._results['injection_well_P'][-1]",
            "PRODUCTION_WELL_OUTLET_P_MIN": "self.tango_instance.workflow._results['production_well_P'][-1]",
            "RESERVOIR_OUTLET_P_MIN": "self.tango_instance.workflow._results['reservoir_P'][-1]",
            "SURFACE_OUTLET_P_MIN": "self.tango_instance.workflow._results['surface_P_out'][-1]",
            "PRODUCTION_WELL_UP_OUTLET_P_MIN": "self.tango_instance.workflow._results['production_well_pump_P'][-1]"
        }

VARIABLE_PARAMETER_MAPPING = {
            "mass_flow_rate": "self.tango_instance.specs['schedule']['mass_flow_rate']",
            "rock_density": "self.tango_instance.specs['props']['rock_density']",
            "rock_cp": "self.tango_instance.specs['props']['rock_cp']",
            "rock_k": "self.tango_instance.specs['props']['rock_k']",
            "surface_temperature": "self.tango_instance.specs['surface']['surface_temperature']",
            "surface_pressure": "self.tango_instance.specs['surface']['surface_pressure']",
            "thermal_gradient": "self.tango_instance.specs['props']['thermal_gradient']",
            "well_spacing": "self.tango_instance.specs['schedule']['well_spacing']",
            "num_pp": "self.tango_instance.specs['schedule']['num_pp']",
            "eta_pump": "self.tango_instance.specs['surface']['eta_pump']",
            "brine_density": "self.tango_instance.specs['props']['brine_density']",
            "pipe_diameter": "self.tango_instance.specs['surface']['pipe_diameter']",
            "approach_temperature": "self.tango_instance.specs['surface']['approach_temperature']",
            "condensation_pressure_offset": "self.tango_instance.specs['surface']['condensation_pressure_offset']",
            "temperature_range": "self.tango_instance.specs['surface']['temperature_range']",
            "total_pipe_length": "self.tango_instance.specs['surface']['total_pipe_length']",
            "eta_turbine": "self.tango_instance.specs['surface']['eta_turbine']",
            "porosity": "self.tango_instance.specs['reservoir']['porosity']",
            "permeability": "self.tango_instance.specs['reservoir']['permeability']",
            "initial_pressure": "self.tango_instance.specs['reservoir']['initial_pressure']",
            "initial_temperature": "self.tango_instance.specs['reservoir']['initial_temperature']",
            "reservoir_depth": "self.tango_instance.specs['reservoir']['reservoir_depth']",
            "hydro_static_pressure": "self.tango_instance.specs['reservoir']['hydro_static_pressure']",
            "over_pressure_percentage": "self.tango_instance.specs['reservoir']['over_pressure_percentage']",
            "thickness": "self.tango_instance.specs['reservoir']['thickness']",
            "area": "self.tango_instance.specs['reservoir']['area']",
            "net_to_gross_ratio": "self.tango_instance.specs['reservoir']['net_to_gross_ratio']",
            "well_eff_diameter": "self.tango_instance.specs['reservoir']['well_eff_diameter']",
            "injection_well_diameter": "self.tango_instance.specs['injection_well']['diameter']",
            "injection_well_length": "self.tango_instance.specs['injection_well']['well_length']",
            "injection_well_epsilon": "self.tango_instance.specs['injection_well']['epsilon']",
            "injection_well_probability_of_success": "self.tango_instance.specs['injection_well']['probability_of_success']",
            "injection_well_num_cells": "self.tango_instance.specs['injection_well']['num_cells']",
            "injection_well_wellhead_depth": "self.tango_instance.specs['injection_well']['wellhead_depth']",
            "production_well_diameter": "self.tango_instance.specs['production_well']['diameter']",
            "production_well_length": "self.tango_instance.specs['production_well']['well_length']",
            "production_well_epsilon": "self.tango_instance.specs['production_well']['epsilon']",
            "production_well_probability_of_success": "self.tango_instance.specs['production_well']['probability_of_success']",
            "production_well_num_cells": "self.tango_instance.specs['production_well']['num_cells']",
            "production_well_wellhead_depth": "self.tango_instance.specs['production_well']['wellhead_depth']",
            "discount_rate": "self.tango_instance.specs['economic']['discount_rate']",
            "turbine_p_out": "self.tango_instance.specs['turbine']['p_out']"
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
