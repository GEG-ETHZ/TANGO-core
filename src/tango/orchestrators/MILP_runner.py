"""MILP Runner - Orchestrates MILP optimization with TANGO geothermal integration.

This module runs the MILP optimizer using JSON scenario files.
It modifies/adds geothermal technology based on TANGO economic results.
"""

import sys
import os
import json
import numpy as np
from typing import Dict, List, Optional
from copy import deepcopy

# MILP addon directory
MILP_ADDON_DIR = os.path.join(os.path.dirname(__file__), "..", "addons", "MILP")


class MILPScenarioManager:
    """Manages MILP scenario JSON files and adds geothermal from TANGO."""
    
    def __init__(self, base_scenario_path: str):
        """Initialize with a base scenario JSON file.
        
        Args:
            base_scenario_path: Path to base JSON scenario (e.g., with_all_HP.json)
        """
        self.base_scenario_path = base_scenario_path
        self.scenario = self._load_scenario()
    
    def _load_scenario(self) -> Dict:
        """Load base scenario from JSON file."""
        if not os.path.exists(self.base_scenario_path):
            raise FileNotFoundError(f"Scenario file not found: {self.base_scenario_path}")
        
        with open(self.base_scenario_path, 'r') as f:
            scenario = json.load(f)
        
        print(f"[MILP] Loaded scenario: {scenario.get('name', 'Unknown')}")
        print(f"[MILP] Technologies: {len(scenario.get('technologies', []))}")
        return scenario
    
    def add_geothermal_from_tango(self, eco_results: Dict, dh_specs, thermal_power: float):
        """Add/update geothermal technology from TANGO results.
        
        Args:
            eco_results: Economic results from TANGO
            dh_specs: DistrictHeatingSpecs from TANGO
            thermal_power: Thermal power output in Watts
        """
        # Calculate geothermal parameters from TANGO
        net_thermal_mw = abs(thermal_power) / 1_000_000.0
        CAPEX = eco_results.get('CAPEX_total', 0)
        SpCC = CAPEX / net_thermal_mw if net_thermal_mw > 0 else 0
        
        # Create geothermal technology spec
        geothermal_tech = {
            "name": "Geothermal",
            "installed_capacity": net_thermal_mw,
            "min_generation": 0.0,
            "max_generation": net_thermal_mw,
            "SpCC": SpCC,
            "OPEX_fix": getattr(dh_specs, 'OPEX_fix', 2000.0) if hasattr(dh_specs, 'OPEX_fix') else 2000.0,
            "OPEX_var": getattr(dh_specs, 'OPEX_var', 1.1) if hasattr(dh_specs, 'OPEX_var') else 1.1,
            "coldstart_cost": getattr(dh_specs, 'coldstart_cost', 1000.0),
            "energy_carrier_price": "electricity_price",
            "emission_factor": 0.243,
            "efficiency": getattr(dh_specs, 'efficiency_thermal', 0.9),
            "lifetime": int(getattr(dh_specs, 'feeding_time', 25))
        }
        
        # Find existing geothermal and update, or add new
        existing_idx = None
        for i, tech in enumerate(self.scenario.get('technologies', [])):
            if tech.get('name', '').lower() == 'geothermal':
                existing_idx = i
                break
        
        if existing_idx is not None:
            self.scenario['technologies'][existing_idx] = geothermal_tech
            print(f"[MILP] Updated Geothermal: {net_thermal_mw:.2f} MW, SpCC: €{SpCC:,.0f}/MW")
        else:
            self.scenario['technologies'].insert(0, geothermal_tech)
            print(f"[MILP] Added Geothermal: {net_thermal_mw:.2f} MW, SpCC: €{SpCC:,.0f}/MW")
    
    def save_scenario(self, output_path: str) -> str:
        """Save modified scenario to JSON file.
        
        Args:
            output_path: Path for output JSON file
            
        Returns:
            Path to saved file
        """
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(self.scenario, f, indent=4)
        
        print(f"[MILP] Scenario saved to: {output_path}")
        return output_path
    
    def get_scenario(self) -> Dict:
        """Get the current scenario configuration."""
        return self.scenario


def calculate_annual_averages(values: List[float], time_steps: List[float]) -> Dict[int, float]:
    """Calculate time-weighted average value for each year.
    
    Args:
        values: List of values at each time step
        time_steps: List of time step durations (in years)
        
    Returns:
        Dictionary with year as key and average value as value
    """
    if len(values) != len(time_steps):
        raise ValueError("Values and time_steps must have the same length")
    
    if not values or not time_steps:
        raise ValueError("Input lists cannot be empty")
    
    cumulative_times = []
    cumulative_time = 0
    for dt in time_steps:
        cumulative_times.append(cumulative_time)
        cumulative_time += dt
    
    annual_data = {}
    
    for i, (value, dt) in enumerate(zip(values, time_steps)):
        start_time = cumulative_times[i]
        year = int(round(start_time, 10))
        
        if year not in annual_data:
            annual_data[year] = {'weighted_sum': 0, 'total_time': 0}
        
        annual_data[year]['weighted_sum'] += value * dt
        annual_data[year]['total_time'] += dt
    
    return {year: data['weighted_sum'] / data['total_time'] for year, data in annual_data.items()}


def run_milp_optimization(scenario_path: str, output_dir: str = None) -> Dict:
    """Run MILP optimization for a given scenario.
    
    Args:
        scenario_path: Path to scenario JSON file
        output_dir: Directory for output files
        
    Returns:
        Optimization results dictionary
    """
    # Add MILP addon to path
    sys.path.insert(0, MILP_ADDON_DIR)
    
    from scenario_loader import load_scenario
    from optimizer.operation_optimization import OperationOptimizer
    from post_processors.performance_metrics import PerformanceMetrics
    from visualizers.profile_visualizer import ProfileVisualizer
    from visualizers.load_duration import plot_load_duration_curve
    from visualizers.energymix_visualization import plot_thermal_power_energymix, plot_weekly_detail
    
    # Determine output directory
    if output_dir is None:
        scenario_name = os.path.splitext(os.path.basename(scenario_path))[0]
        output_dir = os.path.join(MILP_ADDON_DIR, "outputs", scenario_name)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n[MILP] Starting optimization...")
    print(f"[MILP] Scenario: {scenario_path}")
    print(f"[MILP] Output: {output_dir}")
    print("=" * 60)
    
    # Load scenario
    demand, technologies, storage = load_scenario(scenario_path)
    
    # Create and run optimizer
    opt = OperationOptimizer(demand, technologies, storage=storage)
    opt.add_variables()
    opt.add_demand_constraint()
    opt.add_generation_constraints()
    opt.add_soc_constraints()
    opt.add_storage_discharge_constraint()
    opt.add_coldstart_constraints()
    opt.add_ramp_constraints()
    opt.add_chp_constraints()
    opt.set_objective()
    
    results = opt.solve()
    
    # Print results
    print(f"\n[MILP] === Results ===")
    print(f"[MILP] Variable Cost: €{results['variable_cost']:,.0f}")
    
    for name, gen in results["generation"].items():
        cs = results["coldstarts"][name]
        print(f"[MILP] {name}: {gen.sum():,.0f} MWh, Coldstarts={cs}")
    
    if "storage" in results:
        flow = results["storage"]["flow"]
        print(f"[MILP] Storage: Charged={np.maximum(flow, 0).sum():,.0f}, "
              f"Discharged={np.maximum(-flow, 0).sum():,.0f} MWh")
    
    # Performance metrics
    metrics = PerformanceMetrics(technologies, storage=storage)
    metrics.print_report(results, results["coldstarts"])
    
    # Generate visualizations
    storage_flow = results["storage"]["flow"] if "storage" in results else None
    
    # Energy dispatch
    viz1 = ProfileVisualizer(ylabel="Power (MW)")
    viz1.add("Demand", demand.values)
    for name, gen in results["generation"].items():
        viz1.add(name, gen)
    viz1.plot_timeseries("Energy Dispatch", os.path.join(output_dir, "energy_dispatch.png"))
    
    # Storage plots
    if "storage" in results:
        viz_flow = ProfileVisualizer(ylabel="Power (MW)")
        viz_flow.add("Flow (MW)", results["storage"]["flow"])
        viz_flow.plot_timeseries("Storage Flow", os.path.join(output_dir, "storage_flow.png"))
        
        viz_soc = ProfileVisualizer(ylabel="Energy (MWh)")
        viz_soc.add("SOC (MWh)", results["storage"]["soc"])
        viz_soc.plot_timeseries("Storage SOC", os.path.join(output_dir, "storage_soc.png"))
    
    # Load duration curve
    plot_load_duration_curve(demand.values, results["generation"], storage_flow,
                            os.path.join(output_dir, "load_duration_curve.png"))
    
    # Thermal power energymix
    plot_thermal_power_energymix(demand.values, results["generation"], storage_flow,
                                 os.path.join(output_dir, "thermal_power_energymix.png"))
    
    # Weekly detail (winter)
    plot_weekly_detail(demand.values, results["generation"], storage_flow, week=3,
                      output_file=os.path.join(output_dir, "weekly_detail_winter.png"))
    
    print(f"\n[MILP] Plots saved to: {output_dir}/")
    print("=" * 60)
    
    return results


def process_json_and_run_milp(scenario_json_path: str, eco_results: Dict, dh_specs, 
                               results_over_time: Dict, dt_list: List[float]) -> Dict:
    """Main function to process JSON scenario and run MILP optimization.
    
    Args:
        scenario_json_path: Path to base JSON scenario file
        eco_results: Economic results from TANGO
        dh_specs: DistrictHeatingSpecs from TANGO
        results_over_time: Time series results from TANGO
        dt_list: List of time step durations
        
    Returns:
        Dictionary with status, scenario file, and results
    """
    print('[MILP] Processing scenario and running optimization')
    print(f'[MILP] Base scenario: {scenario_json_path}')
    print(f'[MILP] CAPEX: €{eco_results.get("CAPEX_total", 0):,.0f}')
    
    # Calculate thermal power for the operation year
    thermal_values = results_over_time.get('DH_heat_transfer_real', [])
    thermal_power = None
    
    if thermal_values and dt_list:
        annual_thermal_power = calculate_annual_averages(thermal_values, dt_list)
        operation_year = getattr(dh_specs, 'operation_year', 5)
        thermal_power = annual_thermal_power.get(operation_year - 1, 0)
        print(f'[MILP] Thermal power at year {operation_year}: {abs(thermal_power)/1e6:.2f} MW')
    
    try:
        # Load and modify scenario
        manager = MILPScenarioManager(scenario_json_path)
        
        # Add geothermal from TANGO results
        if thermal_power is not None:
            manager.add_geothermal_from_tango(eco_results, dh_specs, thermal_power)
        
        # Save modified scenario
        output_dir = os.path.join(MILP_ADDON_DIR, "outputs", "tango_integrated")
        os.makedirs(output_dir, exist_ok=True)
        modified_scenario_path = os.path.join(output_dir, "tango_scenario.json")
        manager.save_scenario(modified_scenario_path)
        
        # Run optimization
        milp_results = run_milp_optimization(modified_scenario_path, output_dir)
        
        return {
            "status": "success",
            "scenario_file": modified_scenario_path,
            "output_dir": output_dir,
            "results": milp_results
        }
        
    except Exception as e:
        print(f"[MILP] Error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# Default scenario path
DEFAULT_SCENARIO = os.path.join(MILP_ADDON_DIR, "scenarios", "with_all_HP.json")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="MILP Runner - Run MILP optimization")
    parser.add_argument("--scenario", "-s", default=DEFAULT_SCENARIO,
                        help="Path to JSON scenario file")
    parser.add_argument("--output", "-o", help="Output directory for results")
    
    args = parser.parse_args()
    
    run_milp_optimization(args.scenario, args.output)
