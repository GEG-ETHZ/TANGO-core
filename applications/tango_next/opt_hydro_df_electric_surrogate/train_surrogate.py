"""Stage 3: fit a random-forest surrogate (regressors + feasibility classifier) on the LHS training data.

Usage: uv run python train_surrogate.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from common import DEFAULT_OUTPUT_DIR, PARAMS_FILE, objective_specs, param_specs

from tango_next.pymoo_api import load_params
from tango_next.surrogate_api import (
    classifier_diagnostics_df,
    diagnostics_df,
    save_surrogate,
    train_surrogate,
)


def build_parser() -> argparse.ArgumentParser:
    """CLI for the random-forest hyperparameters."""
    params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        description="Fit a random-forest surrogate (regressors + feasibility classifier) on the LHS training data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--n-estimators", type=int, default=params.get("rf_n_estimators", 300))
    parser.add_argument("--cv-folds", type=int, default=params.get("rf_cv_folds", 5))
    parser.add_argument("--seed", type=int, default=params.get("rf_seed", 1))
    parser.add_argument(
        "--classifier-threshold",
        type=float,
        default=params.get("classifier_threshold", 0.5),
        help="Predicted-feasible probability must be >= this to pass the classifier gate. "
        "Raise it (e.g. 0.7) to bias toward flagging MORE designs as infeasible if "
        "classifier_cv_recall_infeasible looks too low (missing true-infeasible designs "
        "is the costly error here, not over-rejecting feasible ones).",
    )
    parser.add_argument("--save-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(args: argparse.Namespace) -> None:
    """Train the surrogate and write ``surrogate_model.joblib``/diagnostics CSVs."""
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
        classifier_threshold=args.classifier_threshold,
    )

    diag = diagnostics_df(surrogate)
    classifier_diag = classifier_diagnostics_df(surrogate)
    print(diag.to_string(index=False))
    print(classifier_diag.to_string(index=False))

    args.save_dir.mkdir(parents=True, exist_ok=True)
    save_surrogate(surrogate, args.save_dir / "surrogate_model.joblib")
    diag.to_csv(args.save_dir / "surrogate_diagnostics.csv", index=False)
    classifier_diag.to_csv(args.save_dir / "surrogate_classifier_diagnostics.csv", index=False)


if __name__ == "__main__":
    main(build_parser().parse_args())
