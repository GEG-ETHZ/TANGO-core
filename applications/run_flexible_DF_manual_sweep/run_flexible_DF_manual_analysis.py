"""Analysis script for LHS Parameter Sweep results.

Generates summary statistics and breakdown tables from sweep results.

Usage:
    python run_flexible_DF_manual_analysis.py
    python run_flexible_DF_manual_analysis.py --sweep-dir /path/to/sweep
"""

import argparse
import json
import math
from collections import Counter
from pathlib import Path

import polars as pl

# Paths (same defaults as sweep script)
DEFAULT_SWEEP_DIR = Path(__file__).parent


def load_results(results_dir: Path) -> list[dict]:
    """Load all result JSON files from the results directory."""
    results = []
    for f in sorted(results_dir.glob("*.json")):
        with open(f) as fp:
            results.append(json.load(fp))
    return results


def generate_result_type_table(results: list[dict]) -> pl.DataFrame:
    """Generate a polars DataFrame of result types (success/error breakdown).

    Returns a DataFrame with Result Type, Count, and Percentage columns,
    including a success row.
    """
    # Count successes vs errors by type
    type_counts: Counter[str] = Counter()

    for r in results:
        if r["LCOE"] is not None and r["error"] is None:
            type_counts["Success"] += 1
        elif r["error"] is not None:
            error_type = (
                r["error"].get("type", "Unknown")
                if isinstance(r["error"], dict)
                else "Unknown"
            )
            type_counts[error_type] += 1
        else:
            type_counts["Unknown"] += 1

    total = sum(type_counts.values())

    # Sort by count descending, but keep Success at top
    sorted_types = sorted(
        type_counts.items(),
        key=lambda x: (0 if x[0] == "Success" else 1, -x[1]),
    )

    # Build DataFrame
    rows = []
    for result_type, count in sorted_types:
        pct = count / total * 100 if total > 0 else 0
        rows.append({"Result Type": result_type, "Count": count, "Percentage": pct})
    # Add total row
    rows.append({"Result Type": "Total", "Count": total, "Percentage": 100.0})

    return pl.DataFrame(rows)


def generate_lcoe_statistics(results: list[dict]) -> pl.DataFrame:
    """Generate LCOE statistics for successful runs as a polars DataFrame."""
    import numpy as np

    # Filter for valid LCOE values (not None, not NaN, not infinite)
    lcoe_values = [
        float(r["LCOE"])
        for r in results
        if r["LCOE"] is not None
        and not math.isnan(float(r["LCOE"]))
        and not math.isinf(float(r["LCOE"]))
    ]

    if not lcoe_values:
        return pl.DataFrame({"Statistic": ["No valid data"], "Value": [None]})

    stats = {
        "Count": float(len(lcoe_values)),
        "Min": min(lcoe_values),
        "Max": max(lcoe_values),
        "Mean": float(np.mean(lcoe_values)),
        "Median": float(np.median(lcoe_values)),
    }

    if len(lcoe_values) > 1:
        stats["Std Dev"] = float(np.std(lcoe_values))

    return pl.DataFrame(
        {"Statistic": list(stats.keys()), "Value": list(stats.values())}
    )


def generate_error_module_breakdown(results: list[dict]) -> pl.DataFrame:
    """Break down errors by module ID (for ValidationErrors) as a polars DataFrame."""
    module_counts: Counter[str] = Counter()

    for r in results:
        if r["error"] is not None:
            error = r["error"] if isinstance(r["error"], dict) else {}
            message = error.get("message", "")
            # Extract module id from validation error messages
            if "module id:" in message:
                # Parse "module id: injection_well" pattern
                for line in message.split("\n"):
                    if "module id:" in line:
                        module = line.split("module id:")[-1].strip()
                        if module:
                            module_counts[module] += 1
                            break

    if not module_counts:
        return pl.DataFrame({"Module": [], "Error Count": []})

    rows = [
        {"Module": module, "Error Count": count}
        for module, count in module_counts.most_common()
    ]

    return pl.DataFrame(rows)


def analyze_sweep(sweep_dir: Path) -> str:
    """Run full analysis and return markdown report with embedded polars tables."""
    results_dir = sweep_dir / "results"

    if not results_dir.exists():
        return f"Error: Results directory not found: {results_dir}"

    results = load_results(results_dir)

    if not results:
        return "Error: No results found."

    # Generate tables
    result_type_df = generate_result_type_table(results)
    lcoe_stats_df = generate_lcoe_statistics(results)
    error_module_df = generate_error_module_breakdown(results)

    # Build report sections
    sections = [
        "# LHS Sweep Analysis Report",
        "",
        f"**Sweep directory**: `{sweep_dir}`",
        f"**Total simulations**: {len(results):,}",
        "",
        "## Result Type Breakdown",
        "",
        str(result_type_df),
        "",
        "## LCOE Statistics",
        "",
        str(lcoe_stats_df),
    ]

    if len(error_module_df) > 0:
        sections.extend(
            [
                "",
                "## Errors by Module",
                "",
                str(error_module_df),
            ]
        )

    return "\n".join(sections)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze LHS Parameter Sweep results",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sweep-dir",
        type=Path,
        default=None,
        help=f"Directory containing sweep outputs (default: {DEFAULT_SWEEP_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for report (default: print to stdout)",
    )
    return parser.parse_args()


def main() -> None:
    """Run analysis and output report."""
    args = parse_args()
    sweep_dir = args.sweep_dir if args.sweep_dir is not None else DEFAULT_SWEEP_DIR

    report = analyze_sweep(sweep_dir)

    if args.output:
        args.output.write_text(report)
        print(f"Report saved: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
