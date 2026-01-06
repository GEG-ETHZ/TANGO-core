"""Scenario loader - loads technology configurations from JSON files."""

import json
import os
import numpy as np
import pandas as pd
from typing import List, Optional, Tuple
from opt_inputs.tech_params import Technology, Storage
from pre_processors.demand_scaling import load_scaled_demand
from pre_processors.profile_generator import Profile


def load_temperature_profiles(data_dir: str) -> dict:
    """Load temperature profiles for heat pump COP calculation.
    
    Returns dict with keys: ambient_temp, river_temp, wastewater_temp, flow_temp, return_temp
    Each value is a numpy array of 8760 hourly values.
    """
    temp_file = os.path.join(data_dir, "Wien_2016_temperature_profiles.csv")
    if not os.path.exists(temp_file):
        print(f"Warning: Temperature profile not found at {temp_file}")
        return None
    
    df = pd.read_csv(temp_file)
    return {
        'ambient_temp': df['ambient_temp'].values,
        'river_temp': df['river_temp'].values,
        'wastewater_temp': df['wastewater_temp'].values,
        'flow_temp': df['flow_temp'].values,
        'return_temp': df['return_temp'].values
    }


def calculate_heat_pump_cop(
    source_temp: np.ndarray,
    flow_temp: np.ndarray,
    return_temp: np.ndarray,
    cop_nominal: float,
    source_temp_nominal: float = 7.0,
    flow_temp_nominal: float = 35.0,
    return_temp_nominal: float = 60.0,
    cop_sensitivity_source: float = 0.03,
    cop_sensitivity_flow: float = -0.02,
    cop_sensitivity_return: float = 0.01
) -> np.ndarray:
    """Calculate hourly COP for heat pump based on temperatures.
    
    Hotmaps formula:
        COP(h) = COP_nominal + (T_source(h) - T_source_nom) * sens_source
                             + (T_return(h) - T_return_nom) * sens_return
                             + (T_flow(h) - T_flow_nom) * sens_flow
    
    Args:
        source_temp: Hourly source temperature (air, river, wastewater, etc.)
        flow_temp: Hourly DH flow/inlet temperature
        return_temp: Hourly DH return temperature
        cop_nominal: Nominal COP at reference conditions
        source_temp_nominal: Reference source temperature [°C]
        flow_temp_nominal: Reference flow/inlet temperature [°C]
        return_temp_nominal: Reference return temperature [°C]
        cop_sensitivity_source: COP change per °C source temp (positive)
        cop_sensitivity_flow: COP change per °C flow temp (negative)
        cop_sensitivity_return: COP change per °C return temp (positive)
    
    Returns:
        Hourly COP values (clipped to minimum 1.0)
    """
    delta_source = source_temp - source_temp_nominal
    delta_flow = flow_temp - flow_temp_nominal
    delta_return = return_temp - return_temp_nominal
    
    cop = (cop_nominal + 
           delta_source * cop_sensitivity_source + 
           delta_return * cop_sensitivity_return +
           delta_flow * cop_sensitivity_flow)
    
    # COP must be at least 1.0 (thermodynamic limit)
    cop = np.clip(cop, 1.0, None)
    
    return cop


def calculate_heat_pump_restriction(
    source_temp: np.ndarray,
    min_source_temp: float,
    fadeout_source_temp: float
) -> np.ndarray:
    """Calculate hourly power restriction factor for heat pump.
    
    Returns 0-1 factor:
    - 0 when source temp < min_source_temp (shutdown)
    - Linear 0-1 between min and fadeout
    - 1 when source temp >= fadeout_source_temp (full power)
    
    Args:
        source_temp: Hourly source temperature
        min_source_temp: Minimum operating temperature (shutdown below this)
        fadeout_source_temp: Temperature for full power operation
    
    Returns:
        Hourly restriction factor (0-1)
    """
    factor = np.ones_like(source_temp)
    
    # Shutdown zone
    shutdown_mask = source_temp < min_source_temp
    factor[shutdown_mask] = 0.0
    
    # Fadeout zone (linear reduction)
    fadeout_mask = (source_temp >= min_source_temp) & (source_temp < fadeout_source_temp)
    if fadeout_source_temp > min_source_temp:
        factor[fadeout_mask] = (source_temp[fadeout_mask] - min_source_temp) / (fadeout_source_temp - min_source_temp)
    
    return factor


def load_scenario(scenario_path: str) -> Tuple[Profile, List[Technology], Optional[Storage]]:
    """Load a scenario from JSON file.
    
    Returns:
        (demand_profile, technologies, storage)
    """
    with open(scenario_path, 'r') as f:
        config = json.load(f)
    
    print(f"Loading scenario: {config['name']}")
    
    # Data directory contains all CSV files
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    
    # Load demand
    demand_config = config['demand']
    demand_file = os.path.join(data_dir, demand_config['file'])
    demand = load_scaled_demand(demand_file, demand_config['annual_total_mwh'])
    
    # Load electricity price profile for technologies that need it
    elec_price_file = os.path.join(data_dir, "Wien_2016_electricity_price_profile.csv")
    elec_price = Profile.from_csv(elec_price_file, column=1).values
    
    # Load radiation profile for Solar Thermal
    radiation_file = os.path.join(data_dir, "Wien_2016_radiation_profile.csv")
    radiation = None
    if os.path.exists(radiation_file):
        radiation = Profile.from_csv(radiation_file, column=0).values  # W/m²
    
    # Load temperature profiles for Heat Pumps
    temp_profiles = load_temperature_profiles(data_dir)
    
    # Load technologies
    technologies = []
    for tech_config in config['technologies']:
        # Handle price: can be number or "electricity_price" reference
        price = tech_config['energy_carrier_price']
        if price == "electricity_price":
            price = elec_price
        
        # Handle max_generation_profile for Solar Thermal (Hotmaps formula)
        max_gen_profile = None
        if tech_config.get('radiation_dependent', False) and radiation is not None:
            # Hotmaps: max_gen = capacity * radiation[t] / max(radiation)
            # This normalizes radiation to 0-1, no efficiency multiplier here
            # (efficiency is only used in marginal cost calculation)
            capacity = tech_config['installed_capacity']
            max_gen_profile = capacity * (radiation / radiation.max())
        
        # Handle Heat Pump temperature-dependent COP and restrictions
        efficiency = tech_config.get('efficiency')
        heat_pump_type = tech_config.get('heat_pump_type')
        
        if heat_pump_type and temp_profiles:
            # Select source temperature based on heat pump type (Hotmaps compatible)
            source_temp_map = {
                'air': temp_profiles['ambient_temp'],
                'river': temp_profiles['river_temp'],
                'wastewater': temp_profiles['wastewater_temp'],
                'wasteheat': np.zeros(8760)  # Hotmaps: constant 0 (no temp variation)
            }
            
            # Get source temperature profile
            source_temp = source_temp_map.get(heat_pump_type)
            
            if source_temp is not None:
                # COP parameters from config or defaults (Hotmaps compatible)
                cop_nominal = tech_config.get('cop_nominal', efficiency)
                source_temp_nominal = tech_config.get('source_temp_nominal', 7.0)
                flow_temp_nominal = tech_config.get('flow_temp_nominal', 90.0)  # Hotmaps: std_inlet_temp
                return_temp_nominal = tech_config.get('return_temp_nominal', 60.0)  # Hotmaps: std_return_temp
                cop_sens_source = tech_config.get('cop_sensitivity_source', 0.03)  # Hotmaps: cop_source_sens
                cop_sens_flow = tech_config.get('cop_sensitivity_flow', -0.02)  # Hotmaps: cop_inlet_sens
                cop_sens_return = tech_config.get('cop_sensitivity_return', 0.01)  # Hotmaps: cop_return_sens
                
                # Calculate hourly COP (Hotmaps formula)
                cop_profile = calculate_heat_pump_cop(
                    source_temp=source_temp,
                    flow_temp=temp_profiles['flow_temp'],
                    return_temp=temp_profiles['return_temp'],
                    cop_nominal=cop_nominal,
                    source_temp_nominal=source_temp_nominal,
                    flow_temp_nominal=flow_temp_nominal,
                    return_temp_nominal=return_temp_nominal,
                    cop_sensitivity_source=cop_sens_source,
                    cop_sensitivity_flow=cop_sens_flow,
                    cop_sensitivity_return=cop_sens_return
                )
                
                # Store hourly COP as efficiency (will be used by optimizer)
                # Note: efficiency becomes an array for heat pumps
                efficiency = cop_profile
                
                print(f"  {tech_config['name']}: COP range {cop_profile.min():.2f} - {cop_profile.max():.2f} (mean: {cop_profile.mean():.2f})")
                
                # Hotmaps formula: max_gen = Cap × (COP / COP_nominal) × restriction_factor
                # This scales capacity based on actual vs nominal COP
                cop_ratio = cop_profile / cop_nominal  # n_th / n_th_nom
                capacity = tech_config['max_generation']
                
                # Calculate restriction factor for air-source (can shut down in cold weather)
                if heat_pump_type == 'air':
                    min_temp = tech_config.get('min_source_temp', -15.0)
                    fadeout_temp = tech_config.get('fadeout_source_temp', -5.0)
                    restriction = calculate_heat_pump_restriction(source_temp, min_temp, fadeout_temp)
                    
                    # Apply COP ratio AND restriction to max_generation_profile
                    max_gen_profile = capacity * cop_ratio * restriction
                    
                    shutdown_hours = int(np.sum(restriction == 0))
                    if shutdown_hours > 0:
                        print(f"    Shutdown hours (T < {min_temp}°C): {shutdown_hours}")
                else:
                    # For other heat pumps (river, wastewater, wasteheat): only COP scaling
                    max_gen_profile = capacity * cop_ratio
                
                print(f"    Capacity scaling: {cop_ratio.min():.2f} - {cop_ratio.max():.2f} (mean: {cop_ratio.mean():.2f})")
        
        # Handle CHP sale electricity price (can be constant or "electricity_price" reference)
        sale_price = tech_config.get('sale_electricity_price')
        if sale_price == "electricity_price":
            sale_price = elec_price
        
        tech = Technology(
            name=tech_config['name'],
            installed_capacity=tech_config['installed_capacity'],
            min_generation=tech_config['min_generation'],
            max_generation=tech_config['max_generation'],
            SpCC=tech_config['SpCC'],
            OPEX_fix=tech_config['OPEX_fix'],
            OPEX_var=tech_config['OPEX_var'],
            coldstart_cost=tech_config['coldstart_cost'],
            energy_carrier_price=price,
            emission_factor=tech_config['emission_factor'],
            efficiency=efficiency,  # Can be scalar or array (heat pump COP profile)
            lifetime=tech_config.get('lifetime', 25),
            max_generation_profile=max_gen_profile,
            excess_heat_source_price=tech_config.get('excess_heat_source_price', 0.0),  # Hotmaps term
            # CHP-specific fields
            chp_type=tech_config.get('chp_type'),
            efficiency_el=tech_config.get('efficiency_el'),
            ratio_pmax=tech_config.get('ratio_pmax'),
            ratio_pmax_fw=tech_config.get('ratio_pmax_fw'),
            sale_electricity_price=sale_price,
            # Piecewise linear performance
            piecewise_file=tech_config.get('piecewise_file')
        )
        technologies.append(tech)
    
    # Load storage (optional)
    storage = None
    if 'storage' in config:
        s = config['storage']
        storage = Storage(
            name=s['name'],
            capacity=s['capacity'],
            hourly_losses=s['hourly_losses'],
            max_discharge_rate=s['max_discharge_rate'],
            max_charge_rate=s['max_charge_rate'],
            discharge_efficiency=s['discharge_efficiency'],
            charge_efficiency=s['charge_efficiency'],
            investment_cost_per_capacity=s['investment_cost_per_capacity'],
            lifetime=s.get('lifetime', 25)
        )
    
    return demand, technologies, storage


if __name__ == "__main__":
    # Test loading
    demand, techs, storage = load_scenario("scenarios/baseline.json")
    print(f"Demand: {demand.values.sum():.0f} MWh")
    print(f"Technologies: {[t.name for t in techs]}")
    print(f"Storage: {storage.name if storage else 'None'}")
