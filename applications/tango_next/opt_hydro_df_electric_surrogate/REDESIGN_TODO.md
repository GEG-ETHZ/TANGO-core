# Surrogate pipeline redesign — brainstorm state (2026-09-03)

Status: **brainstorming only, nothing below has been implemented yet.**
Chad said "don't act on this immediately" — this file exists so a fresh
Claude Code session can resume the conversation without losing context if
this one gets interrupted.

## Where this came from

Two real Euler runs of the LHS-based surrogate pipeline
(`applications/tango_next/opt_hydro_df_electric_surrogate/`) showed the
surrogate isn't trustworthy enough near the Pareto front:

- `(16,16)` MLP hidden layers: LCOE relative error at the real-sim-corrected
  Pareto edge — median 1.4%, max 4.3%. 12/45 surrogate-predicted designs
  survived real-sim validation as genuinely non-dominated.
- `(64,64)` MLP hidden layers (tried 2026-09-02, reverted): CV R²/MAE
  improved (classic overfitting signature — better on held-out folds of the
  SAME training distribution) but real-world accuracy at the edge got
  WORSE (median LCOE error 3.7%, only 10/45 survived). `params.yaml`
  reverted to `(16,16)` with this finding documented inline.

Chad's target: surrogate needs to be **within 1% of the real model in the
vicinity of the Pareto front**, or the pymoo result on the surrogate can't
be trusted.

A prior 5-step accuracy-improvement plan (from an earlier session,
recovered from transcript `1a1a77d8-b645-493d-8fc8-ebf966406e96.jsonl` —
see this session's chat log around 2026-09-02 for the full recovered text)
proposed, least-to-most effort: (1) MLP hyperparameter grid search, (2) MLP
ensemble, (3) bump `n_lhs_samples` further, (4) one manual LHS refinement
round concentrated around the corrected Pareto front, (5) weighted-loss/
importance-sampling training.

Chad flagged step 3 (bumping `n_lhs_samples` well past 5000) as
undermining the whole point of having a surrogate — if you need that many
real sims to train it, you're not saving much over just running the real
optimizer.

I (Claude) built step 4 as `refine_lhs.py` — drew a second LHS batch inside
a padded bounding box around `outputs/corrected_pareto_results.csv`,
real-simmed it, appended to `outputs/lhs_training_data.csv`. **Superseded
by the redesign below** (Chad's answer to open question 4: "replace") and
deleted (2026-09-03) — never run, so nothing depends on it. If a padded-box
LHS refinement is ever wanted again, this transcript/prior git history has
the approach.

## The new idea (Chad's proposal, 2026-09-03)

Replace LHS-based training-data generation with **real-optimizer-trajectory-based**
training-data generation. Rough shape:

1. ~~Rip out surrogate infra~~ — turns out most of it survives unchanged
   (see "what stays / what changes" below). Only the training-data
   *generation* stage changes.
2. Run **real** NSGA2 (the actual `opt_hydro_df_electric` `Minimization`,
   not the surrogate) for a small number of generations — `pop_size=1000`,
   `n_gen` **parameterized**, separate param name from step 4's n_gen.
   Retain **every individual evaluated across every generation**, not just
   the final front (needs a pymoo `Callback` or `save_history=True` to
   capture full population history — this doesn't exist in the codebase
   yet, needs building).
3. Train the classifier + MLP regressors on that **full retained history**
   (same `train_surrogate()` as today — this function doesn't care where
   its input rows came from, no change needed there).
4. Run **another** NSGA2, this time surrogate-driven (same mechanism as
   today's `optimize_surrogate.py`), for its own **separately-parameterized**
   `n_gen`/`pop_size` (cheap, no real sim — can afford much deeper search,
   e.g. closer to the real run's 200 gens).
5. **`validate_surrogate.py`** (unchanged mechanism) — real-sim every
   design from step 4's front, require **all objectives within
   `validation_tolerance`, parameterized, target 1%** (this param already
   exists in `params.yaml`; currently `0.001` (0.1%) — just needs
   reconsidering/setting to `0.01` once the new pipeline is in place, no
   new plumbing needed).
6. Profit. (No loop — same "one-shot, not full active learning" philosophy
   as before, just a smarter one-shot sampling strategy.)

## Open questions / not yet resolved

- **Q1 (Chad, answered):** "I don't know of any reason to expect the
  optimizer to search aggressively near the feasible/infeasible boundary...
  might not be a strong correlation." I (Claude) had overclaimed this —
  retracted. Gen-0 (random init) gives LHS-like broad coverage; later
  generations concentrate near non-dominated designs; whether that also
  concentrates near the feasibility boundary specifically is unverified,
  not assumed either way now.
- **Q2, dedup filtering** — resolved in discussion (2026-09-03), not yet
  implemented:
  - The *check* itself (pairwise distance within a tolerance, e.g. all
    params within ±0.1% — **parameterize this tolerance**) is
    computationally trivial (`scipy.spatial.cKDTree`, O(n log n), sub-second
    for ~5000 rows) regardless of when it happens. Cost is not the
    deciding factor.
  - What matters: dedup **before** real-sim evaluation (saves the actually
    expensive resource — skip evaluating near-duplicate individuals at
    all) vs. **after** (real-sim cost already spent; only benefit left is
    honest CV metrics, since near-duplicate pairs split across CV folds
    inflate R²/MAE the same way the `(64,64)` overfit did).
  - Leaning toward: use pymoo NSGA2's built-in `eliminate_duplicates`
    mechanism (already exists, currently near-exact-match default) with a
    custom distance/tolerance, wired into step 2's real-NSGA2 run, so
    near-duplicates never get real-sim'd in the first place.
  - **Unresolved:** pymoo's built-in dedup likely only compares within a
    generation's offspring against the current population, not against the
    ENTIRE accumulated history across all 5 (or N) generations. A
    generation-4 individual could still duplicate a generation-1 one. May
    need a supplementary full-history pass — still cheap per the cost
    analysis above, just needs deciding whether it's necessary.
- **Q3, step 4's own pop_size** — Chad said step 4's `n_gen` should be a
  separate parameter from step 2's `n_gen`. Didn't explicitly say pop_size
  needs to be separate too (today's `optimize_surrogate.py` defaults
  pop_size/n_max_gen/ftol/xtol/seed from the REAL app's own params.yaml for
  direct comparison — see `common.py`'s `opt_app_pymoo_params()`). Confirm
  whether step 4 should keep mirroring the real app's config, or get its
  own fully independent GA config now that its role has changed (searching
  a cheap surrogate deeply, not directly comparing to the real run).
- **Q4 (Chad, answered):** replace `refine_lhs.py`'s padded-bounding-box
  approach entirely with this trajectory-based approach. Not deleting the
  file yet (see above) but it's dead-end infrastructure once this is built.
- **Not yet discussed:** how the captured per-generation history is stored
  (JSON-per-individual like today's `run_lhs_sweep`'s
  `results_dir`/`_evaluate_and_write` pattern? one CSV per generation? a
  single running file?) — probably want to reuse the existing
  atomic-JSON-per-row + resumability pattern (`_cached_row_is_valid`) since
  it already solves the "killed SLURM job, resume without rerunning
  everything" problem that matters on Euler.
- **Not yet discussed:** whether/how `dvc.yaml`'s DAG changes. The old
  `lhs_generate`/`lhs_sweep` stages get replaced by a
  "real-NSGA2-trajectory" stage; `train_surrogate`/`optimize_surrogate`/
  `validate_surrogate` stay conceptually the same (may need dep-path
  updates only).

## What stays unchanged (confirmed 2026-09-02/03 discussion)

- `surrogate_api.train_surrogate()` — trains on whatever rows it's handed,
  doesn't care about provenance.
- `surrogate_api.SurrogateModel`, the `mlp`/`random_forest`/
  `gaussian_process` regressor factories.
- `surrogate_api.validate_surrogate_pareto()` / `corrected_pareto_front()`.
- `optimize_surrogate.py`'s general shape (surrogate-driven NSGA2) — just
  its `n_gen`/`pop_size` sourcing may change per Q3 above.
- `validate_surrogate.py` — literally becomes "step 5" as-is, just with
  `validation_tolerance` reconsidered (target 1%, i.e. `0.01`).

## What needs building (none of this exists yet)

1. A pymoo `Callback` (or `save_history=True` post-processing) to capture
   every evaluated individual — params + objectives + feasibility — across
   all generations of a real NSGA2 run, not just the final front.
2. A results-writing pattern for that history (JSON-per-row +
   `_cached_row_is_valid`-style resumability, reusing/extending
   `surrogate_api`'s existing pattern where possible).
3. `pop_size`/`n_gen` params for the real trajectory run (new, separate
   name from `optimize_surrogate`'s existing gen count) — e.g.
   `trajectory_pop_size`, `trajectory_n_gen`.
4. A separate, explicitly-named `n_gen` (and TBD pop_size, see Q3) param
   for step 4's surrogate-driven run, distinct from step 2's.
5. The dedup mechanism (Q2) — likely a custom-tolerance
   `eliminate_duplicates` wired into step 2's real NSGA2, tolerance as a
   new parameter (e.g. `dedup_tol_frac: 0.001` for ±0.1%).
6. `validation_tolerance` set to `0.01` (already a param, just needs the
   value decision once the new pipeline exists) — this is the literal "must
   be within 1%" acceptance gate `validate_surrogate.py` already enforces
   (raises `SurrogateValidationError` if violated).
7. Updated `dvc.yaml` DAG once the above is real code (see "not yet
   discussed" above).

## Resume instructions for a fresh session

Read this file, then re-read the working directory's current
`applications/tango_next/opt_hydro_df_electric_surrogate/` state (params.yaml,
dvc.yaml, existing scripts) to confirm nothing's drifted, then pick up at
whichever open question above Chad wants to resolve next. Nothing here has
been implemented — this is planning only.
