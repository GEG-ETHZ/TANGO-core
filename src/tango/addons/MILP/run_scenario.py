#!/usr/bin/env python
"""Run optimization for a given scenario."""

import argparse
import os
import numpy as np
from scenario_loader import load_scenario
from optimizer.operation_optimization import OperationOptimizer
from post_processors.performance_metrics import PerformanceMetrics
from visualizers.profile_visualizer import ProfileVisualizer
from visualizers.load_duration import plot_load_duration_curve
from visualizers.energymix_visualization import plot_thermal_power_energymix, plot_weekly_detail


def run(scenario_path: str):
    """Run optimization for the given scenario."""
    # Load scenario
    demand, technologies, storage = load_scenario(scenario_path)
    
    # Output directory based on scenario name
    scenario_name = os.path.splitext(os.path.basename(scenario_path))[0]
    output_dir = os.path.join(os.path.dirname(__file__), "outputs", scenario_name)
    os.makedirs(output_dir, exist_ok=True)
    
    # Create and run optimizer
    opt = OperationOptimizer(demand, technologies, storage=storage)
    opt.add_variables()
    opt.add_demand_constraint()
    opt.add_generation_constraints()
    opt.add_soc_constraints()
    opt.add_storage_discharge_constraint()
    opt.add_coldstart_constraints()
    opt.add_ramp_constraints()
    opt.add_chp_constraints()  # CHP heat-to-power coupling
    opt.set_objective()
    results = opt.solve()
    
    # Print results
    print(f"\n--- Results ---")
    print(f"Variable Cost: €{results['variable_cost']:,.0f}")
    for name, gen in results["generation"].items():
        cs = results["coldstarts"][name]
        print(f"{name}: {gen.sum():,.0f} MWh, Coldstarts={cs}")
    
    if "storage" in results:
        flow = results["storage"]["flow"]
        print(f"Storage: Charged={np.maximum(flow, 0).sum():,.0f}, Discharged={np.maximum(-flow, 0).sum():,.0f} MWh")
    
    # Performance metrics
    metrics = PerformanceMetrics(technologies, storage=storage)
    metrics.print_report(results, results["coldstarts"])
    
    # Visualization
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
    
    print(f"\nPlots saved to: {output_dir}/")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MILP optimization")
    parser.add_argument("--scenario", "-s", default="scenarios/baseline.json",
                        help="Path to scenario JSON file")
    args = parser.parse_args()
    
    run(args.scenario)

