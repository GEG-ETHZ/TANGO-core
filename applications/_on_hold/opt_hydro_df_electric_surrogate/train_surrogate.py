# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Stage 3: fit a surrogate (regressors + feasibility classifier) on the LHS training data.

Usage: uv run python train_surrogate.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from common import DEFAULT_OUTPUT_DIR, PARAMS_FILE, objective_specs, param_specs

from tango_core.pymoo_api import load_params
from tango_core.surrogate_api import (
    classifier_diagnostics_df,
    diagnostics_df,
    gaussian_process_regressor_factory,
    mlp_regressor_factory,
    random_forest_regressor_factory,
    save_surrogate,
    train_surrogate,
)


def _parse_hidden_layer_sizes(value: str) -> tuple[int, ...]:
    """``"16,16"`` -> ``(16, 16)`` -- argparse type for ``--mlp-hidden-layer-sizes``.

    Args:
        value: Comma-separated layer widths, e.g. ``"16,16"``.
    """
    return tuple(int(n) for n in value.split(","))


def build_parser() -> argparse.ArgumentParser:
    """CLI for the regressor choice and its hyperparameters, plus the feasibility classifier's."""
    params = load_params(PARAMS_FILE)
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Fit a surrogate (regressors + feasibility classifier) on the LHS training data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--regressor",
        choices=["gaussian_process", "random_forest", "mlp"],
        default=params.get("regressor", "mlp"),
        help="Per-objective regressor. mlp (default since 2026-09-01) predicts a smooth surface "
        "and scales well to large n_lhs_samples -- confirmed on a real Euler run to beat "
        "gaussian_process on both training speed and pareto-edge accuracy, see "
        "surrogate_api.SurrogateModel's docstring. gaussian_process is the smooth-surface "
        "reference case. random_forest is this app's original choice, kept for comparison.",
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
        "--mlp-hidden-layer-sizes",
        type=_parse_hidden_layer_sizes,
        default=_parse_hidden_layer_sizes(params.get("mlp_hidden_layer_sizes", "16,16")),
        help="Comma-separated layer widths, e.g. '16,16'. Only used when --regressor=mlp.",
    )
    parser.add_argument(
        "--mlp-alpha",
        type=float,
        default=params.get("mlp_alpha", 1e-3),
        help="L2 regularization strength. Only used when --regressor=mlp.",
    )
    parser.add_argument(
        "--mlp-max-iter",
        type=int,
        default=params.get("mlp_max_iter", 2000),
        help="Only used when --regressor=mlp.",
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
    elif args.regressor == "mlp":
        regressor_factory = mlp_regressor_factory(
            hidden_layer_sizes=args.mlp_hidden_layer_sizes,
            alpha=args.mlp_alpha,
            max_iter=args.mlp_max_iter,
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
