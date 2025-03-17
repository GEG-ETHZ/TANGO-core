"""
Module for managing parameter translation mappings.

Provides centralized access to translation mappings for parameter names, translating human-readable names to corresponding paths in the TANGO system.
"""

BASE_PATHS = {
    "target": "self.tango_instance.workflow.orchestrator.unit.surface.",
    "economic": "self.tango_instance.workflow.economic.get_results()['{key}']",
    "results": "self.tango_instance.workflow._results['{key}'][-1]",
    "specs": "self.tango_instance.specs"
}

TARGET_KEYS = {
    "W_NET", "W_COOLER", "W_CONDENSER", "W_TURBINE", "W_PUMP", "W_DOWNHOLE_PUMP",
    "Q_PREHEATER", "Q_BOILER", "Q_DESUPERHEATER", "Q_COOLER", "Q_CONDENSER",
    "DT_LMTD_RECUPERATOR"
}

ECONOMIC_KEYS = {
    "Net_Electricity_Generated_kWe": "ELECTRIC_POWER_AVE",
    "Net_thermal_power_Generated_kWe": "THERMAL_POWER_AVE",
    "CAPEX_total": "TOTAL_CAPEX",
    "LCOE": "LCOE",
    "SpCC": "SPCC",
    "CAPEX_well": "CAPEX_WELL",
    "CAPEX_permitting": "CAPEX_PERMITTING",
    "CAPEX_exploration": "CAPEX_EXPLORATION",
    "CAPEX_surface_gathering_system": "CAPEX_SURFACE_GATHERING_SYSTEM",
    "CAPEX_surface_plant": "CAPEX_SURFACE_PLANT"
}

RESULT_KEYS = {
    "injection_well_T": "INJECTION_WELL_OUTLET_T_MIN",
    "production_well_T": "PRODUCTION_WELL_OUTLET_T_MIN",
    "reservoir_T": "RESERVOIR_OUTLET_T_MIN",
    "surface_T_out": "SURFACE_OUTLET_T_MIN",
    "injection_well_P": "INJECTION_WELL_OUTLET_P_MIN",
    "production_well_P": "PRODUCTION_WELL_OUTLET_P_MIN",
    "reservoir_P": "RESERVOIR_OUTLET_P_MIN",
    "surface_P_out": "SURFACE_OUTLET_P_MIN"
}

TARGET_PARAMETER_MAPPING = {
    key: f"{BASE_PATHS['target']}{key.lower()}" for key in TARGET_KEYS
}
TARGET_PARAMETER_MAPPING.update({
    val: BASE_PATHS['economic'].format(key=key) for key, val in ECONOMIC_KEYS.items()
})
TARGET_PARAMETER_MAPPING.update({
    val: BASE_PATHS['results'].format(key=key) for key, val in RESULT_KEYS.items()
})

VARIABLE_CATEGORIES = {
    "schedule": ["mass_flow_rate", "well_spacing"],
    "props": ["rock_density", "rock_cp", "rock_k", "thermal_gradient", "brine_density", "num_pp"],
    "surface": [
        "surface_temperature", "surface_pressure", "eta_pump", "pipe_diameter",
        "temperature_range", "total_pipe_length", "eta_turbine", "approach_temperature",
        "condensation_pressure_offset"],
    "reservoir": ["porosity", "permeability", "initial_pressure", "initial_temperature", "reservoir_depth", "over_pressure_percentage", "thickness", "area", "net_to_gross_ratio", "well_eff_diameter", "hydro_static_pressure"],
    "injection_well": {
        "diameter": "injection_well_diameter",
        "well_length": "injection_well_well_length",
        "epsilon": "injection_well_epsilon",
        "vertical_deviation": "injection_well_vertical_deviation",
        "wellhead_depth": "injection_well_wellhead_depth",
        "num_cells": "injection_well_num_cells",
    },
    "production_well": {
        "diameter": "production_well_diameter",
        "well_length": "production_well_length",
        "epsilon": "production_well_epsilon",
        "vertical_deviation": "production_well_vertical_deviation",
        "wellhead_depth": "production_well_wellhead_depth",
        "num_cells": "production_well_num_cells",
    },
    "economic": ["discount_rate"]
}

VARIABLE_PARAMETER_MAPPING = {}

for category, parameters in VARIABLE_CATEGORIES.items():
    if isinstance(parameters, dict):
        for param_key, param_value in parameters.items():
            VARIABLE_PARAMETER_MAPPING[param_value] = f"{BASE_PATHS['specs']}['{category}']['{param_key}']"
    else:
        for param in parameters:
            VARIABLE_PARAMETER_MAPPING[param] = f"{BASE_PATHS['specs']}['{category}']['{param}']"

def get_target_translation(parameter_name: str) -> str:
    """
    Retrieve the mapped TANGO system path for a given parameter.

    Parameters
    ----------
    parameter_name : str
        Parameter name to be translated.

    Returns
    -------
    str
        Corresponding TANGO parameter path.

    Raises
    ------
    KeyError
        If the parameter is not found in the mapping.
    """
    if parameter_name in TARGET_PARAMETER_MAPPING:
        return TARGET_PARAMETER_MAPPING[parameter_name]
    raise KeyError(f"Target parameter '{parameter_name}' not found in translation mapping.")
