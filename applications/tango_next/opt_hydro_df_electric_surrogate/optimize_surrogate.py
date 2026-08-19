"""Stage 4: run NSGA2 against the trained surrogate instead of the real simulation.

**Timing comparison, by design:** every NSGA2 hyperparameter here
(``n_max_gen``/``pop_size``/``ftol``/``xtol``/``seed``) defaults to the
SAME value the real ``opt_hydro_df_electric`` app uses (read straight from
its own ``params.yaml`` via ``common.opt_app_pymoo_params()``, not a second,
independently-typed copy) — so this stage runs the identical GA search as
``opt_hydro_df_electric.py``'s real-sim optimization, with evaluation cost
as the ONLY thing that differs. Compare this stage's printed elapsed time
directly against a real run's own ``Minimization.run()`` timing (e.g. from
``opt_hydro_df_electric_<jobid>.out``) to see the actual surrogate speedup.

Usage: uv run python optimize_surrogate.py
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from common import (
    DEFAULT_OUTPUT_DIR,
    PARAMS_FILE,
    make_plots,
    objective_specs,
    opt_app_pymoo_params,
    param_specs,
)
from common import DISPLAY_RENAME as _DISPLAY_RENAME

from tango_next.pymoo_api import PymooConfig, load_params
from tango_next.surrogate_api import load_surrogate, run_surrogate_optimization
from tango_next.utils import print_dt


def build_parser() -> argparse.ArgumentParser:
    """CLI for the surrogate-driven NSGA2 — defaults mirror the real app's own params.yaml."""
    real_params = opt_app_pymoo_params()
    surrogate_params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        description="Run NSGA2 against the trained surrogate instead of the real simulation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--n-max-gen",
        type=int,
        default=surrogate_params.get("n_max_gen", real_params.get("n_max_gen", 200)),
    )
    parser.add_argument(
        "--pop-size",
        type=int,
        default=surrogate_params.get("pop_size", real_params.get("pop_size", 40)),
    )
    parser.add_argument(
        "--ftol",
        type=float,
        default=surrogate_params.get("ftol", real_params.get("ftol", 0.005)),
    )
    parser.add_argument(
        "--xtol",
        type=float,
        default=surrogate_params.get("xtol", real_params.get("xtol", 0.0005)),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=surrogate_params.get("optimize_seed", real_params.get("seed", 1)),
    )
    parser.add_argument("--save-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress pymoo's per-generation progress table (printed by default, "
        "same as the real opt_hydro_df_electric.py run — see run_surrogate_optimization's "
        "docstring for why this matters for a fair time comparison).",
    )
    return parser


def main(args: argparse.Namespace) -> None:
    """Run the surrogate-driven NSGA2 search and write ``surrogate_pareto_results.csv``."""
    print("optimize_surrogate.py starting at")
    print_dt()

    params = param_specs()
    objectives = objective_specs()
    surrogate = load_surrogate(args.save_dir / "surrogate_model.joblib")

    pymoo_config = PymooConfig(
        n_max_gen=args.n_max_gen,
        pop_size=args.pop_size,
        ftol=args.ftol,
        xtol=args.xtol,
        seed=args.seed,
    )
    print(
        f"Surrogate NSGA2: n_max_gen={pymoo_config.n_max_gen}, pop_size={pymoo_config.pop_size} "
        "(same GA config as the real opt_hydro_df_electric.py run, for a direct timing comparison)",
    )
    print("run_surrogate_optimization() starting at")
    print_dt()
    start = time.monotonic()
    df = run_surrogate_optimization(surrogate, params, pymoo_config, verbose=not args.quiet)
    elapsed = time.monotonic() - start
    print(f"Pareto front: {len(df)} designs")
    print(f"run_surrogate_optimization() finished in {elapsed:.1f}s")

    args.save_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.save_dir / "surrogate_pareto_results.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")

    if not args.no_plot:
        param_cols = [p.name for p in params]
        objective_cols = [_DISPLAY_RENAME.get(o.name, o.name) for o in objectives]
        make_plots(df, args.save_dir, param_cols, objective_cols)


if __name__ == "__main__":
    main(build_parser().parse_args())
