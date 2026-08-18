"""Stage 1: draw a Latin Hypercube sample over hydro_df_electric's decision-variable bounds.

No simulation happens here — only ``ParamSpec.bounds`` are needed, so this
stage is cheap regardless of ``--n-samples``.

Usage: uv run python generate_lhs.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from common import DEFAULT_OUTPUT_DIR, PARAMS_FILE, param_specs

from tango_next.pymoo_api import load_params
from tango_next.surrogate_api import generate_lhs_samples


def build_parser() -> argparse.ArgumentParser:
    """CLI for the LHS design-matrix size/seed."""
    params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        description="Draw a Latin Hypercube sample over hydro_df_electric's decision variables.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--n-samples", type=int, default=params.get("n_lhs_samples", 500))
    parser.add_argument("--seed", type=int, default=params.get("lhs_seed", 1))
    parser.add_argument("--save-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(args: argparse.Namespace) -> None:
    """Generate the LHS design matrix and write it to ``<save-dir>/lhs_design_matrix.csv``."""
    params = param_specs()
    x = generate_lhs_samples(params, args.n_samples, args.seed)

    df = pd.DataFrame(x, columns=[p.name for p in params])
    df.insert(0, "row_idx", range(len(df)))

    args.save_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.save_dir / "lhs_design_matrix.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} LHS samples to {out_path}")


if __name__ == "__main__":
    main(build_parser().parse_args())
