"""Result aggregation and table generation for the tango_next Triemli direct-heat sweep.

tango_next port of ``applications/run_AGS_direct_heat_sweep/summarize.py``.
Structure is unchanged except for the CAPEX/LCOE pivots and the qualified-
designs table: tango_next has no wired-up ``EconomicComponent`` yet (Phase 1
placeholder — see ``sweep.py``'s module docstring), so every CAPEX_*/LCOE_*
column in the aggregated results is always null. Rather than crash on an
all-null pivot or silently print empty tables, those pivots are skipped with
a printed note, and the qualified-designs table only lists the columns that
are actually populated (T_prod_C, specific_enthalpy_kJ_kg, thermal_power_kW).
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


def pivot_table(
    df: pl.DataFrame,
    value_col: str,
    loop_length_m: float | None = None,
    loop_diameter_m: float | None = None,
) -> pl.DataFrame:
    """Pivot (depth × mass-flow) into a 2-D table for a single output column, at one (loop
    length, loop diameter) slice.

    Rows = well depth [m], columns = mass-flow rate [kg/s]. Failed / null
    cells are shown as None. loop_length_m/loop_diameter_m filter to a
    single slice — a flat 2-D pivot can't show all four sweep axes at once,
    so callers iterate over (loop_length, loop_diameter) pairs (see main()).
    """
    successful = df.filter(pl.col("error").is_null())
    if loop_length_m is not None:
        successful = successful.filter((pl.col("loop_length_m") - loop_length_m).abs() < 1e-6)
    if loop_diameter_m is not None:
        successful = successful.filter((pl.col("loop_diameter_m") - loop_diameter_m).abs() < 1e-6)
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


def _loop_lengths(df: pl.DataFrame) -> list[float]:
    """Sorted unique loop lengths present in the results."""
    return sorted(df.select("loop_length_m").unique().to_series().to_list())


def _loop_diameters(df: pl.DataFrame) -> list[float]:
    """Sorted unique loop diameters present in the results."""
    return sorted(df.select("loop_diameter_m").unique().to_series().to_list())


# CAPEX_*/LCOE_* columns are deliberately NOT in this list — every value is
# None (no EconomicComponent wired up yet in tango_next, see sweep.py's
# module docstring), so a pivot table over them would be all-null. See
# main()'s printed note instead of a table for those.
_PIVOT_SPECS: list[tuple[str, str, str]] = [
    ("T_prod_C", "T_production_degC", "°C"),
    ("specific_enthalpy_kJ_kg", "specific_enthalpy_kJ_kg", "kJ/kg"),
    ("thermal_power_kW", "thermal_power_kW", "kW"),
]

_PIVOT_LABELS: dict[str, str] = {
    "T_prod_C": "Production temperature",
    "specific_enthalpy_kJ_kg": "Specific enthalpy  (derived from thermal_power_kW / mass_flow_kg_per_s)",
    "thermal_power_kW": "Thermal power  (TESPy-solved dh_hx duty, net_thermal_W / 1000)",
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
        print(f"\nResults: {n_ok} succeeded, {n_fail} failed → {parquet_out}")
        print(
            "Note: CAPEX_*/LCOE_USD_per_kWh columns are always null in this "
            "port — pending tango_next's Phase 2 economic component. No "
            "pivot tables or plots are generated for them.",
        )

    loop_lengths = _loop_lengths(df)
    loop_diameters = _loop_diameters(df)

    # ── write pivot CSVs (always, so the student always gets fresh files) ─────
    # One CSV per (value, loop length, loop diameter) — a flat 2-D pivot can't
    # show all four sweep axes, so loop length/diameter become filename
    # suffixes instead of table dimensions.
    csv_dir = results_dir
    csv_paths: list[Path] = []
    for value_col, filename_stem, _unit in _PIVOT_SPECS:
        for loop_length in loop_lengths:
            for loop_diameter in loop_diameters:
                tbl = pivot_table(df, value_col, loop_length_m=loop_length, loop_diameter_m=loop_diameter)
                if not tbl.is_empty():
                    diam_tag = f"{loop_diameter:.3f}".replace(".", "p")
                    csv_path = csv_dir / f"{filename_stem}__loop{int(round(loop_length))}m__d{diam_tag}m.csv"
                    tbl.write_csv(csv_path)
                    csv_paths.append(csv_path)
    if not quiet:
        print(
            f"CSVs written to {csv_dir}/ ({len(csv_paths)} files: "
            f"{len(_PIVOT_SPECS)} metrics x {len(loop_lengths)} loop lengths x "
            f"{len(loop_diameters)} loop diameters)",
        )

    if quiet:
        return

    # ── flag designs that meet the 105 °C threshold ───────────────────────────
    # (Per-combo pivot tables are no longer dumped to the console — with loop
    # length x loop diameter now many combinations, printing every metric's
    # table for every combo is unreadable. Use the CSVs above, or plot.py's
    # scatter/parallel-coordinates plots, for full exploration.)
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
                        "loop_length_m",
                        "loop_diameter_m",
                        "T_prod_C",
                        "specific_enthalpy_kJ_kg",
                        "thermal_power_kW",
                    ],
                ).sort(["well_depth_m", "mass_flow_kg_per_s", "loop_length_m", "loop_diameter_m"]),
            )

    # ── failed runs ───────────────────────────────────────────────────────────
    if n_fail > 0:
        print(f"\n{'─' * 70}")
        print(f"  Failed runs ({n_fail}):")
        print(f"{'─' * 70}")
        with pl.Config(tbl_rows=20):
            print(
                df.filter(pl.col("error").is_not_null()).select(
                    ["well_depth_m", "mass_flow_kg_per_s", "loop_length_m", "loop_diameter_m", "error"],
                ),
            )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Aggregate and display tango_next Triemli sweep results",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--quiet", "-q", action="store_true")
    parser.add_argument("--sweep-dir", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(quiet=args.quiet, sweep_dir=args.sweep_dir)
