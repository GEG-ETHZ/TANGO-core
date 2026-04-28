"""Parameter sensitivity sweep for flexible_SF_manual.yml

Creates a baseline TANGO instance, then clones and perturbs each numeric parameter
to determine which have no impact on LCOE.
"""

from pathlib import Path

from tango.runner import Runner


def get_nested_value(d: dict, path: str):
    """Get value from nested dict using dot-separated path."""
    keys = path.split(".")
    for key in keys:
        d = d[key]
    return d


def set_nested_value(d: dict, path: str, value):
    """Set value in nested dict using dot-separated path."""
    keys = path.split(".")
    for key in keys[:-1]:
        d = d[key]
    d[keys[-1]] = value


# Parameters to test: (path, perturbation_factor)
PARAMETERS = [
    # props
    "props.brine_density",
    "props.rock_density",
    "props.rock_cp",
    "props.rock_k",
    "props.thermal_gradient",
    # surface
    "surface.surface_temperature",
    "surface.injection_pressure",
    "surface.surface_pressure",
    "surface.pipe_diameter",
    "surface.approach_temperature",
    "surface.target_extraction_pressure",
    "surface.epsilon",
    # reservoir
    "reservoir.reservoir_depth",
    "reservoir.thickness",
    "reservoir.permeability",
    "reservoir.porosity",
    "reservoir.hydro_static_pressure",
    "reservoir.over_pressure_percentage",
    # injection_well
    "injection_well.well_length",
    "injection_well.diameter",
    "injection_well.epsilon",
    # "injection_well.well_length_seq",  # Economic param, should match well_length
    # "injection_well.well_diameter_seq",  # Economic param, should match diameter
    # production_well
    "production_well.well_length",
    "production_well.diameter",
    "production_well.epsilon",
    # "production_well.well_length_seq",  # Economic param, should match well_length
    # "production_well.well_diameter_seq",  # Economic param, should match diameter
    # production_well_pump
    "production_well_pump.well_length",
    "production_well_pump.diameter",
    "production_well_pump.epsilon",
    # schedule
    "schedule.mass_flow_rate",
    "schedule.well_spacing",
    "schedule.num_pp",
    # "schedule.time.num_tsteps",  # Simulation config, not physical
    # "schedule.time.dt",  # Simulation config, not physical
    # "schedule.bc_iteration.max_mass_rate",  # Simulation config, not physical
    "schedule.mass_rate.value",
    # economic
    "economic.discount_rate",
    # valve
    "valve.p_out",
    # turbine
    "turbine.efficiency",
    "turbine.p_out",
    # condenser
    "condenser.p_out",
    "condenser.vapor_mass_fraction_out",
    # pumps
    "pump.efficiency",
    "pump2.efficiency",
]

PERTURBATION = 1.1  # 10% increase


def main():
    """Run parameter sensitivity sweep and report LCOE impact."""
    input_file = Path(__file__).parent / "flexible_SF_manual.yml"

    # Create baseline
    print("Creating baseline runner...")
    runner_base = Runner(
        input_file=input_file,
        no_save=True,
        log_level="NONE",
    )

    # Run baseline
    print("Running baseline simulation...")
    baseline = runner_base.clone()
    baseline.start()
    baseline_lcoe = baseline.tango.workflow.economic._results["LCOE"]
    print(f"Baseline LCOE: {baseline_lcoe}")

    # Ensure _seq params match their scalar equivalents
    seq_mappings = [
        ("injection_well.well_length_seq", "injection_well.well_length"),
        ("injection_well.well_diameter_seq", "injection_well.diameter"),
        ("production_well.well_length_seq", "production_well.well_length"),
        ("production_well.well_diameter_seq", "production_well.diameter"),
    ]
    for seq_path, scalar_path in seq_mappings:
        scalar_val = get_nested_value(runner_base.tango.specs, scalar_path)
        set_nested_value(runner_base.tango.specs, seq_path, [scalar_val])

    # Results
    no_impact = []
    has_impact = []
    errors = []

    # Test each parameter
    for param_path in PARAMETERS:
        try:
            # Clone from base
            runner = runner_base.clone()

            # Get original value
            original_value = get_nested_value(runner.tango.specs, param_path)

            # Handle lists - perturb all elements
            if isinstance(original_value, list):
                if all(isinstance(x, (int, float)) for x in original_value):
                    new_value = [x * PERTURBATION for x in original_value]
                else:
                    print(f"  Skipping {param_path} (non-numeric list)")
                    continue
            elif isinstance(original_value, (int, float)):
                new_value = original_value * PERTURBATION
            else:
                print(f"  Skipping {param_path} (non-numeric: {type(original_value)})")
                continue

            # Perturb
            set_nested_value(runner.tango.specs, param_path, new_value)

            # Sync injection well length = production_well + production_well_pump lengths
            prod_len = get_nested_value(runner.tango.specs, "production_well.well_length")
            pump_len = get_nested_value(runner.tango.specs, "production_well_pump.well_length")
            set_nested_value(runner.tango.specs, "injection_well.well_length", prod_len + pump_len)

            runner.update_parameters()

            # Run
            print(f"Testing {param_path}: {original_value} -> {new_value}...", end=" ")
            runner.start()
            lcoe = runner.tango.workflow.economic._results["LCOE"]

            # Compare
            if lcoe == baseline_lcoe:
                print("NO IMPACT (LCOE unchanged)")
                no_impact.append(param_path)
            else:
                pct_change = (lcoe - baseline_lcoe) / baseline_lcoe * 100
                print(f"IMPACT: {pct_change:+.2f}%")
                has_impact.append((param_path, pct_change))

        except Exception as e:
            print(f"ERROR: {e}")
            errors.append((param_path, str(e)))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"\nParameters with NO IMPACT on LCOE ({len(no_impact)}):")
    for p in no_impact:
        print(f"  - {p}")

    print(f"\nParameters WITH IMPACT on LCOE ({len(has_impact)}):")
    for p, pct in sorted(has_impact, key=lambda x: abs(x[1]), reverse=True):
        print(f"  - {p}: {pct:+.2f}%")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for p, err in errors:
            print(f"  - {p}: {err}")


if __name__ == "__main__":
    main()
