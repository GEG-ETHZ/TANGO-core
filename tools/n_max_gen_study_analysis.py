"""Analyze the n_max_gen study (docs/pymoo_generation_budget.md).

Reads every ``studies/n_max_gen/<app>/seed<N>/evaluations.csv`` written by
``tools/n_max_gen_study_job.sh`` and, for each run and generation, rebuilds
the best front found so far (the non-dominated set of every feasible design
evaluated up to that generation) and computes:

- its hypervolume, with both objectives rescaled to 0-1 using the best and
  worst values on the union of that app's final fronts (all seeds), and one
  fixed reference point at 1.1 in both, so values are comparable across
  generations and seeds;
- the design closest to that front's ideal corner (``ideal_distance``, the
  default pick) and its objectives.

Writes ``studies/n_max_gen/summary.csv`` (one row per app, seed and
generation) and ``studies/n_max_gen/<app>_progress.png``, and prints a table
for the decision rule.

Usage, from the repo root:
    uv run python tools/n_max_gen_study_analysis.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting

from tango_core.pymoo_api import ideal_distance

STUDY_DIR = Path("studies/n_max_gen")
REFERENCE = 1.1
"""Hypervolume reference point in normalized units (just worse than the worst final-front value)."""
WINDOW = 50
"""Generations over which the hypervolume gain is measured."""
GAIN_TOL = 1e-3
"""A hypervolume gain below this fraction per ``WINDOW`` generations counts as settled."""


def non_dominated(f: np.ndarray) -> np.ndarray:
    """Rows of ``f`` (minimized objectives) that no other row dominates."""
    if len(f) == 0:
        return f
    return f[NonDominatedSorting().do(f, only_non_dominated_front=True)]


def hypervolume_2d(front: np.ndarray, ref: float) -> float:
    """Area dominated by a 2-objective (minimized) front, bounded by ``(ref, ref)``."""
    pts = front[(front[:, 0] < ref) & (front[:, 1] < ref)]
    if len(pts) == 0:
        return 0.0
    pts = pts[np.argsort(pts[:, 0])]
    area, prev_y = 0.0, ref
    for x, y in pts:
        if y < prev_y:
            area += (ref - x) * (prev_y - y)
            prev_y = y
    return area


def fronts_by_generation(df: pd.DataFrame, objectives: list[str]) -> dict[int, np.ndarray]:
    """Best front found up to and including each generation."""
    feasible = df[df["success"]]
    out: dict[int, np.ndarray] = {}
    front = np.empty((0, len(objectives)))
    for gen, chunk in feasible.groupby("n_gen"):
        front = non_dominated(np.vstack([front, chunk[objectives].to_numpy(dtype=float)]))
        out[int(gen)] = front
    return out


def analyze_app(app_dir: Path) -> pd.DataFrame:
    """Hypervolume and pick per seed and generation for one app."""
    runs = {
        int(p.name.removeprefix("seed")): pd.read_csv(p / "evaluations.csv")
        for p in sorted(app_dir.glob("seed*"))
    }
    first = next(iter(runs.values()))
    objectives = [c for c in first.columns if c not in {"row_idx", "success", "n_gen"}][-2:]
    fronts = {seed: fronts_by_generation(df, objectives) for seed, df in runs.items()}
    final_union = np.vstack([f[max(f)] for f in fronts.values()])
    lo, hi = final_union.min(axis=0), final_union.max(axis=0)
    span = np.where(hi > lo, hi - lo, 1.0)
    rows = []
    for seed, by_gen in fronts.items():
        for gen, front in by_gen.items():
            normalized = (front - lo) / span
            pick = front[int(ideal_distance(front).argmin())]
            rows.append(
                {
                    "app": app_dir.name,
                    "seed": seed,
                    "n_gen": gen,
                    "front_size": len(front),
                    "hypervolume": hypervolume_2d(normalized, REFERENCE),
                    f"pick_{objectives[0]}": pick[0],
                    f"pick_{objectives[1]}": pick[1],
                },
            )
    return pd.DataFrame(rows)


def settled_generation(hv: pd.Series) -> int | None:
    """First generation after which the hypervolume grows by < GAIN_TOL (relative) over the next WINDOW generations."""
    gens = hv.index.to_numpy()
    for g in gens:
        later = g + WINDOW
        if later > gens.max():
            return None
        if (hv.loc[later] - hv.loc[g]) / hv.loc[later] < GAIN_TOL:
            return int(g)
    return None


def plot_app(summary: pd.DataFrame, app: str) -> None:
    """Hypervolume and pick objectives vs. generation, one line per seed."""
    pick_cols = [c for c in summary.columns if c.startswith("pick_") and summary[c].notna().all()]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for seed, run in summary.groupby("seed"):
        axes[0].plot(run["n_gen"], run["hypervolume"], label=f"seed {seed}")
        for ax, col in zip(axes[1:], pick_cols, strict=True):
            sign = -1.0 if col.startswith("pick_negative_") else 1.0
            ax.plot(run["n_gen"], sign * run[col], label=f"seed {seed}")
    axes[0].set_ylabel("hypervolume (normalized)")
    for ax, col in zip(axes[1:], pick_cols, strict=True):
        ax.set_ylabel(col.removeprefix("pick_").removeprefix("negative_") + " of the ideal-corner pick")
    for ax in axes:
        ax.set_xlabel("generation")
        ax.axvline(200, color="grey", linestyle="--", linewidth=0.8)
        ax.grid(visible=True, alpha=0.3)
        ax.legend()
    fig.suptitle(f"{app}: best front found so far (dashed: current n_max_gen = 200)")
    fig.tight_layout()
    fig.savefig(STUDY_DIR / f"{app}_progress.png", dpi=130)
    plt.close(fig)


def main() -> None:
    """Analyze every app in the study and print the decision table."""
    summary = pd.concat(
        [analyze_app(d) for d in sorted(STUDY_DIR.iterdir()) if d.is_dir()],
        ignore_index=True,
    )
    summary.to_csv(STUDY_DIR / "summary.csv", index=False)
    for app, app_df in summary.groupby("app"):
        plot_app(app_df, str(app))
        print(f"\n## {app}")
        pick_cols = [c for c in app_df.columns if c.startswith("pick_") and app_df[c].notna().all()]
        for seed, run in app_df.groupby("seed"):
            hv = run.set_index("n_gen")["hypervolume"]
            at = {g: hv.loc[g] for g in (100, 200, 300, 400, 600)}
            settled = settled_generation(hv)
            final = run[run["n_gen"] == run["n_gen"].max()].iloc[0]
            at200 = run[run["n_gen"] == 200].iloc[0]
            print(
                f"seed {seed}: HV "
                + " ".join(f"g{g}={v:.4f}" for g, v in at.items())
                + f" | HV(200)/HV(600)={at[200] / at[600]:.4f} | settled at g={settled}"
                + " | pick g200 -> g600: "
                + ", ".join(f"{c.removeprefix('pick_')} {at200[c]:.4g} -> {final[c]:.4g}" for c in pick_cols),
            )
        finals = app_df[app_df["n_gen"] == app_df["n_gen"].max()]
        print(
            "seed spread at g600: "
            + ", ".join(
                f"{c.removeprefix('pick_')} {finals[c].min():.4g}..{finals[c].max():.4g}" for c in pick_cols
            ),
        )


if __name__ == "__main__":
    main()
