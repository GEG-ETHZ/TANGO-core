# Surrogate pipeline redesign — implemented, awaiting Chad's review (2026-09-03)

Status: **built and smoke-tested locally (tiny toy sizes), NOT yet run at
real Euler scale.** Chad said "get after it... do the whole pipeline then
ask for my review" (2026-09-03) — this file exists so a fresh Claude Code
session can resume the conversation without losing context if this one
gets interrupted. See "What was actually built" below for the current
state; everything under "Open questions" further down is either resolved
or explicitly deferred, not blocking review.

## Where this came from

Two real Euler runs of the LHS-based surrogate pipeline
(`applications/opt_hydro_df_electric_surrogate/`) showed the
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

## What was actually built (2026-09-03)

- **`ParamToleranceDuplicateElimination`** (new class in `src/tango_core/pymoo_api.py`,
  next to `Minimization`) — two designs are duplicates if EVERY param is
  within `tol_frac` of the other's OWN `bounds` range (not one combined
  Euclidean distance against a fixed absolute epsilon like pymoo's own
  `DefaultDuplicateElimination`, which conflates parameters of wildly
  different scales/units). Answers Q2's design question: passed as
  `NSGA2(..., eliminate_duplicates=...)`, so pymoo's `Mating.do()` filters
  near-duplicates out BEFORE they're real-simulated, not just afterward.
  Q2's "unresolved" caveat still stands as documented in the class's own
  docstring: only catches duplicates within the current offspring
  batch/population, not the full multi-generation history.
- **`Minimization.capture_trajectory_path`** (new optional field + private
  `_append_trajectory` method, `pymoo_api.py`) — when set, appends EVERY
  generation's newly-evaluated individuals (`algorithm.off`, which pymoo's
  own `Algorithm.advance()` sets unconditionally every call to `next()`,
  including generation 1's initialization — no special-casing needed) to a
  CSV, one row per individual, schema-identical to `surrogate_api`'s
  LHS-sweep training rows (param columns, objective columns — `NaN`, not
  absent, for infeasible designs, since appending one small `DataFrame` per
  generation needs identical columns every chunk or `to_csv(mode="a")`
  silently misaligns them — a subtlety this took an extra edit to get
  right — `success` bool, `row_idx`). Hooked into `run()`'s existing
  per-generation loop, right where `_save_intermediate` already lives.
  Per-individual `n_gen` is read from `off.get("n_gen")` (what pymoo itself
  stamps at infill-time), NOT `algorithm.n_gen` (a property that's already
  incremented for the NEXT round by the time `next()` returns — confirmed
  via a smoke test that initially mislabeled generation 1 as 2).
- **`run_trajectory.py`** (new app script, replaces `generate_lhs.py` +
  `sweep_lhs.py`, both deleted) — builds `NSGA2(pop_size=trajectory_pop_size,
  eliminate_duplicates=ParamToleranceDuplicateElimination(...))`, wraps it
  in a `Minimization` with `pymoo_config=PymooConfig(n_max_gen=trajectory_n_gen,
  ftol=0.0, xtol=0.0, ...)` (ftol/xtol pinned to 0.0 so `trajectory_n_gen`
  is a hard generation count, not convergence-dependent — `DefaultMultiObjectiveTermination`
  would otherwise stop early), `capture_trajectory_path=outputs/lhs_training_data.csv`,
  `save_results=False`. Also writes `outputs/trajectory_pareto_results.csv`
  (the real trajectory's own final front — a free diagnostic, not required
  by anything downstream).
- **`train_surrogate.py`/`optimize_surrogate.py`/`validate_surrogate.py`**:
  genuinely UNCHANGED (optimize_surrogate.py got two doc/print-string edits
  only, no logic changes) — confirmed via the local smoke test below that
  `train_surrogate.py` consumes `run_trajectory.py`'s output with zero
  code changes, as designed.
- **`params.yaml`**: `trajectory_pop_size: 1000`, `trajectory_n_gen: 5`,
  `trajectory_seed: 1`, `trajectory_dedup_tol_frac: 0.001` added.
  `n_max_gen`/`pop_size`/`ftol`/`xtol`/`optimize_seed` UNCOMMENTED (now
  `optimize_surrogate`'s own real values, Q3 resolved as "give it its own
  config" — see below) rather than falling back to the real app's
  params.yaml. `validation_tolerance: 0.01` (was `0.001`) — Chad's literal
  1% target.
- **`dvc.yaml`**: `lhs_generate`/`lhs_sweep` replaced by one `run_trajectory`
  stage. `optimize_surrogate`'s deps switched from a whole-file
  `params.yaml` dep to proper per-key `params:` tracking now that its keys
  are no longer conditionally absent.
- **`surrogate_api.dedup_training_rows`** (2026-09-04, closes Q2's
  full-history gap): a second, post-hoc dedup pass, run once at the end of
  `run_trajectory.py` over the WHOLE retained trajectory (not just one
  generation's batch, which is all `ParamToleranceDuplicateElimination` can
  see). Two rows are duplicates if every param AND (for two feasible rows)
  every objective is within `trajectory_dedup_tol_frac` of the other's,
  normalized by that column's OBSERVED range across the dataset — uses
  `scipy.spatial.cKDTree` with Chebyshev (`p=inf`) distance, confirmed
  empirically cheap (~0.02s at 50,000 rows/5 columns, vs. ~1.6s for a naive
  O(n²) broadcast at just 10,000 — checking cost was never the
  consideration). Caught and fixed a real bug during testing: the first
  implementation normalized by the COMPARISON GROUP's own observed range,
  which is self-referential and nearly untriggerable for a small group (a
  2-row group's range IS the gap between them); fixed to normalize by the
  full dataset's range instead, computed once and reused consistently.
- **Local smoke test** (tiny sizes — `pop_size=20`, `n_gen=3`, `cv_folds=3`,
  `n_max_gen=20` — NOT representative of real accuracy, only confirms the
  pipeline runs mechanically end to end): `run_trajectory.py` → 60
  trajectory rows (43 feasible) → `train_surrogate.py` (LCOE CV r2=0.85) →
  `optimize_surrogate.py` (11-design front) → `validate_surrogate.py` (0/11
  survived at THIS toy scale — meaningless at pop_size=20/n_gen=3, real
  accuracy can only be judged from an actual Euler-scale run).
- **`refine_lhs.py`**: deleted per Q4 (already done before this build
  started).
- `outputs/` still has old LHS-era files on disk (`lhs_design_matrix.csv`,
  `lhs_sweep_results/`) — harmless (gitignored, no longer referenced by
  `dvc.yaml`), not cleaned up, safe to `rm -r` or leave.
- **`dvc.lock` NOT regenerated** — that requires an actual `dvc repro`
  (real Euler-scale multiprocessing job), which wasn't run. It'll pick up
  the new stage names/hashes automatically on the next real `dvc repro`.

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
- **Q3, step 4's own pop_size — resolved (2026-09-03), not asked but made
  a judgment call:** gave `optimize_surrogate` its own full GA config
  (`n_max_gen`/`pop_size`/`ftol`/`xtol`/`optimize_seed`, all uncommented in
  `params.yaml`) rather than keeping ANY of it mirroring the real app's
  config — the old "direct timing comparison" rationale for mirroring
  doesn't apply once stage 1 no longer runs an equivalent real NSGA2 search
  at those settings. Worth Chad confirming this judgment call specifically
  (not just the overall build) since it wasn't explicitly asked for.
- **Q4 (Chad, answered):** replace `refine_lhs.py`'s padded-bounding-box
  approach entirely with this trajectory-based approach. Not deleting the
  file yet (see above) but it's dead-end infrastructure once this is built.
- **Resolved by the build, worth flagging:** the captured history is
  written as ONE growing CSV (`Minimization._append_trajectory`, one
  `to_csv(mode="a")` call per generation), NOT the JSON-per-individual +
  `_cached_row_is_valid`-style resumability pattern `run_lhs_sweep` uses.
  Deliberate, not an oversight — see `_append_trajectory`'s own docstring:
  unlike independent LHS samples, a killed NSGA2 run can't cheaply resume
  its SEARCH at all (would need to pickle the whole live `Algorithm`,
  including a `multiprocessing.Pool` when `n_processes > 1`), so there's no
  resumability to preserve either way; a killed run just loses whatever
  generation was in progress, same as `_save_intermediate`'s existing
  partial-front behavior.
- **Resolved:** `dvc.yaml`'s `lhs_generate`/`lhs_sweep` stages replaced by
  one `run_trajectory` stage; `train_surrogate` unchanged;
  `optimize_surrogate` switched from a whole-file `params.yaml` dep to
  proper per-key tracking (see "What was actually built"); `validate_surrogate`
  unchanged mechanically, just `validation_tolerance` reconsidered.

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

## What's genuinely still open (not blocking review, but not done either)

1. ~~Q2's full-history dedup gap~~ — **resolved 2026-09-04**, see
   `dedup_training_rows` above.
2. **Not validated at real scale.** Everything above is confirmed
   mechanically correct (smoke-tested at toy sizes) but says NOTHING about
   whether this approach actually hits the 1% accuracy target better than
   the old LHS approach did — that's the whole point of running it for
   real on Euler next.
3. Whether `trajectory_pop_size=1000`/`trajectory_n_gen=5` (Chad's own
   sketched starting numbers) are remotely the right scale is unknown —
   first real run is the first real signal on that.

## Resume instructions for a fresh session

Read this file's "What was actually built" section, then re-read the
working directory's current `applications/opt_hydro_df_electric_surrogate/`
state (params.yaml, dvc.yaml, run_trajectory.py, and
`src/tango_core/pymoo_api.py`'s `ParamToleranceDuplicateElimination`/
`Minimization.capture_trajectory_path`) to confirm nothing's drifted since.
If Chad has already run this on Euler, check `outputs/` and
`dvc.lock` for real results before re-explaining the design from scratch.
