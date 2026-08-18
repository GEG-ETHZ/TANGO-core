"""Stage 3: fit a random-forest surrogate (one per objective) on the LHS training data.

Usage: uv run python train_surrogate.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from common import DEFAULT_OUTPUT_DIR, PARAMS_FILE, objective_specs, param_specs

from tango_next.pymoo_api import load_params
from tango_next.surrogate_api import diagnostics_df, save_surrogate, train_surrogate


def build_parser() -> argparse.ArgumentParser:
    """CLI for the random-forest hyperparameters."""
    params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        description="Fit a random-forest surrogate on the LHS training data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--n-estimators", type=int, default=params.get("rf_n_estimators", 300))
    parser.add_argument("--cv-folds", type=int, default=params.get("rf_cv_folds", 5))
    parser.add_argument("--seed", type=int, default=params.get("rf_seed", 1))
    parser.add_argument("--save-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(args: argparse.Namespace) -> None:
    """Train the surrogate and write ``surrogate_model.joblib``/``surrogate_diagnostics.csv``."""
    training_df = pd.read_csv(args.save_dir / "lhs_training_data.csv")
    param_names = [p.name for p in param_specs()]
    objective_names = [o.name for o in objective_specs()]

    surrogate = train_surrogate(
        training_df,
        param_names,
        objective_names,
        n_estimators=args.n_estimators,
        cv_folds=args.cv_folds,
        seed=args.seed,
    )

    diag = diagnostics_df(surrogate)
    print(diag.to_string(index=False))

    args.save_dir.mkdir(parents=True, exist_ok=True)
    save_surrogate(surrogate, args.save_dir / "surrogate_model.joblib")
    diag.to_csv(args.save_dir / "surrogate_diagnostics.csv", index=False)


if __name__ == "__main__":
    main(build_parser().parse_args())
