"""Stage 3: fit a surrogate (regressors + feasibility classifier) on the LHS training data.

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
    gaussian_process_regressor_factory,
    random_forest_regressor_factory,
    save_surrogate,
    train_surrogate,
)


def build_parser() -> argparse.ArgumentParser:
    """CLI for the regressor choice and its hyperparameters, plus the feasibility classifier's."""
    params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        description="Fit a surrogate (regressors + feasibility classifier) on the LHS training data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--regressor",
        choices=["gaussian_process", "random_forest"],
        default=params.get("regressor", "gaussian_process"),
        help="Per-objective regressor. gaussian_process (default) predicts a smooth surface, "
        "which keeps NSGA2 able to distinguish nearby designs -- see surrogate_api.SurrogateModel's "
        "docstring. random_forest is this app's original choice, kept for comparison.",
    )
    parser.add_argument(
        "--gpr-n-restarts-optimizer",
        type=int,
        default=params.get("gpr_n_restarts_optimizer", 5),
        help="Only used when --regressor=gaussian_process.",
    )
    parser.add_argument(
        "--regressor-rf-n-estimators",
        type=int,
        default=params.get("regressor_rf_n_estimators", 300),
        help="Only used when --regressor=random_forest.",
    )
    parser.add_argument(
        "--classifier-n-estimators",
        type=int,
        default=params.get("classifier_n_estimators", 300),
    )
    parser.add_argument("--cv-folds", type=int, default=params.get("cv_folds", 5))
    parser.add_argument("--seed", type=int, default=params.get("surrogate_seed", 1))
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

    if args.regressor == "gaussian_process":
        regressor_factory = gaussian_process_regressor_factory(
            n_restarts_optimizer=args.gpr_n_restarts_optimizer,
            seed=args.seed,
        )
    else:
        regressor_factory = random_forest_regressor_factory(
            n_estimators=args.regressor_rf_n_estimators,
            seed=args.seed,
        )

    surrogate = train_surrogate(
        training_df,
        param_names,
        objective_names,
        regressor_factory=regressor_factory,
        classifier_n_estimators=args.classifier_n_estimators,
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
