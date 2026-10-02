"""Result aggregation and table generation for the tango Triemli EGS direct-heat sweep.

tango port of ``applications/run_EGS_direct_heat_sweep/summarize.py``.
Structure is a single 2-D depth x mass-flow pivot per metric — this sweep
has no loop-length/loop-diameter axes, unlike the AGS direct-heat sweep, so
there's no need to iterate over extra slices. ``CAPEX_total_USD``/
``LCOE_USD_per_kWh`` are read from each design point's
``DoubletEconomicComponent`` state (see ``sweep.py``'s module docstring) and
get their own pivot tables alongside the physics outputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl
from common import DEFAULT_SWEEP_DIR


def aggregate_results(results_dir: Path) -> pl.DataFrame:
    """Load all per-run JSON files and return a flat DataFrame."""
    rows = []
    for f in sorted(results_dir.glob("*.json")):
        with open(f) as fp:
            r = json.load(fp)
        if isinstance(r.get("error"), dict):
            r["error"] = r["error"].get("message", "error")
        rows.append(r)
    return pl.DataFrame(rows)


def pivot_table(df: pl.DataFrame, value_col: str) -> pl.DataFrame:
    """Pivot (depth x mass-flow) into a 2-D table for a single output column.

    Rows = well depth [m], columns = mass-flow rate [kg/s].
    Failed / null cells are shown as None.
    """
    successful = df.filter(pl.col("error").is_null())
    if successful.is_empty():
        return pl.DataFrame()

    # Round grid values to avoid float-equality mismatches
    tbl = (
        successful.with_columns(
            [
                pl.col("well_depth_m").round(0).cast(pl.Int64).alias("depth"),
                pl.col("mass_flow_kg_per_s").round(1).alias("mdot"),
                pl.col(value_col),
            ],
        )
        .select(["depth", "mdot", value_col])
        .pivot(on="mdot", index="depth", values=value_col, aggregate_function="first")
        .sort("depth")
    )
    return tbl


def print_pivot(label: str, df: pl.DataFrame, unit: str = "") -> None:
    """Print a pivot table with a formatted header."""
    if df.is_empty():
        print(f"\n{label}: no successful results.\n")
        return
    suffix = f"  [{unit}]" if unit else ""
    print(f"\n{'─' * 70}")
    print(f"  {label}{suffix}")
    print("  Rows = well depth [m] | Columns = mass flow rate [kg/s]")
    print(f"{'─' * 70}")
    with pl.Config(tbl_rows=30, tbl_cols=20, float_precision=2):
        print(df)


_PIVOT_SPECS: list[tuple[str, str, str]] = [
    ("T_prod_C", "T_production_degC", "°C"),
    ("specific_enthalpy_kJ_kg", "specific_enthalpy_kJ_kg", "kJ/kg"),
    ("thermal_power_kW", "thermal_power_kW", "kW"),
    ("CAPEX_total_USD", "CAPEX_total_USD", "USD"),
    ("LCOE_USD_per_kWh", "LCOE_USD_per_kWh", "USD/kWh"),
]

_PIVOT_LABELS: dict[str, str] = {
    "T_prod_C": "Production temperature",
    "specific_enthalpy_kJ_kg": "Specific enthalpy  (derived from thermal_power_kW / mass_flow_kg_per_s)",
    "thermal_power_kW": "Thermal power  (TESPy-solved district_heating_hx duty, net_thermal_W / 1000)",
    "CAPEX_total_USD": "Total CAPEX  (DoubletEconomicComponent)",
    "LCOE_USD_per_kWh": "Levelized cost of heat  (DoubletEconomicComponent)",
}


def main(quiet: bool = False, sweep_dir: Path | None = None) -> None:
    """Aggregate results, write CSVs, and print pivot tables."""
    sweep_dir = sweep_dir or DEFAULT_SWEEP_DIR
    results_dir = sweep_dir / "results"
    parquet_out = sweep_dir / "results.parquet"

    df = aggregate_results(results_dir)
    df.write_parquet(parquet_out)

    n_ok = df.filter(pl.col("error").is_null()).height
    n_fail = df.filter(pl.col("error").is_not_null()).height
    if not quiet:
        print(f"\nResults: {n_ok} succeeded, {n_fail} failed -> {parquet_out}")

    # ── write pivot CSVs (always, so the student always gets fresh files) ─────
    csv_dir = results_dir
    csv_paths: list[Path] = []
    for value_col, filename_stem, _unit in _PIVOT_SPECS:
        tbl = pivot_table(df, value_col)
        if not tbl.is_empty():
            csv_path = csv_dir / f"{filename_stem}.csv"
            tbl.write_csv(csv_path)
            csv_paths.append(csv_path)
    if not quiet:
        print(f"CSVs written to {csv_dir}/")
        for p in csv_paths:
            print(f"  {p.name}")

    if quiet:
        return

    # ── pivot tables for the student ──────────────────────────────────────────
    for value_col, _stem, unit in _PIVOT_SPECS:
        print_pivot(_PIVOT_LABELS[value_col], pivot_table(df, value_col), unit)

    # ── flag designs that meet the 105 °C threshold ───────────────────────────
    qualified = df.filter(
        pl.col("error").is_null() & (pl.col("T_prod_C") >= 105.0),
    )
    print(f"\n{'─' * 70}")
    print(f"  Designs with T_prod ≥ 105 °C:  {qualified.height} / {n_ok}")
    print(f"{'─' * 70}")
    if not qualified.is_empty():
        with pl.Config(tbl_rows=50, float_precision=1):
            print(
                qualified.select(
                    [
                        "well_depth_m",
                        "mass_flow_kg_per_s",
                        "T_prod_C",
                        "specific_enthalpy_kJ_kg",
                        "thermal_power_kW",
                        "CAPEX_total_USD",
                        "LCOE_USD_per_kWh",
                    ],
                ).sort(["well_depth_m", "mass_flow_kg_per_s"]),
            )

    # ── failed runs ───────────────────────────────────────────────────────────
    if n_fail > 0:
        print(f"\n{'─' * 70}")
        print(f"  Failed runs ({n_fail}):")
        print(f"{'─' * 70}")
        with pl.Config(tbl_rows=20):
            print(
                df.filter(pl.col("error").is_not_null()).select(
                    ["well_depth_m", "mass_flow_kg_per_s", "error"],
                ),
            )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Aggregate and display tango Triemli EGS sweep results",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument("--sweep-dir", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(quiet=args.quiet, sweep_dir=args.sweep_dir)
