# How many generations do the opt apps need? (`n_max_gen` study)

Started October 16, 2026. Results pending.

Every opt app currently runs NSGA-II for 200 generations with a population
of 45 (`n_max_gen` and `pop_size` in each app's `params.yaml`). Every run on
2026-10-14 ended at that cap, which is normal: pymoo runs here usually end at
`n_max_gen`, not on pymoo's own convergence check. The question is whether
200 is enough for the front, and the design picked from it, to stop changing
in a way that matters, or whether it's more than needed.

## Method

### Runs

Three apps of increasing difficulty, each run to 600 generations (3x the
current cap) with three seeds:

| App | Why | Euler time per 200 generations |
|---|---|---|
| `opt_hydro_direct_heat` | Cheap, 6 decision variables | ~6 min |
| `opt_hydro_sf_electric` | Flash plant, 7 decision variables | ~12 min |
| `opt_AGS_ORC_electric` | 8 decision variables, half of them pinned at bounds | ~20 min |

Each run uses the app's own `params.yaml` except for the generation cap, the
seed, and pymoo's convergence check, which is switched off so every run
reaches 600 generations. Each run records every design it evaluates and the
generation it was evaluated in (`--capture-trajectory`), in
`studies/n_max_gen/<app>/seed<N>/evaluations.csv`. The job script is
`tools/n_max_gen_study_job.sh`; its header has the submission loop. These
runs never touch the apps' DVC-tracked `outputs/`.

Submitted October 16, 2026 at commit `bb09ddc7`:

| App | Seed 1 | Seed 2 | Seed 3 |
|---|---|---|---|
| `opt_hydro_direct_heat` | 17268391 | 17268394 | 17268399 |
| `opt_hydro_sf_electric` | 17268402 | 17268406 | 17268408 |
| `opt_AGS_ORC_electric` | 17268411 | 17268415 | 17268418 |

**Seeds.** The seed sets NSGA-II's random choices: the starting population
and every mutation and crossover. Two runs with the same settings and
different seeds take different random paths toward the front. Seed 1 is the
seed the production runs use, so its first 200 generations repeat the
2026-10-14 run exactly. Comparing seeds shows how much of the
generation-to-generation change is real improvement and how much is noise:
once extra generations change the result less than switching seeds does,
more generations aren't buying anything.

### Measuring progress: hypervolume

All the analysis happens after the runs finish, from the saved
`evaluations.csv` files; no further simulations are needed.

1. **Front after each generation.** For each generation g, take every
   feasible design evaluated up to and including g and keep the
   non-dominated ones. That's the best front the run had found by then.
2. **Hypervolume of that front.** With two objectives (LCOE, to minimize, and
   power, to maximize), plot the front and pick one fixed reference point
   that's worse than every design in both objectives: higher LCOE and lower
   power than anything found. The hypervolume is the area between the front
   and that point: the part of objective space the front beats. A better
   front (cheaper, more powerful, or wider) covers more area, so the
   hypervolume grows. It never shrinks, because a design only leaves the
   front when something better replaces it. To make it comparable across
   generations, seeds and apps, both objectives are rescaled to 0-1 using
   the best and worst values seen across all of an app's runs, and the same
   reference point is used throughout.
3. **The pick.** For each generation, also record the design with the
   smallest `ideal_distance` (the default pick) and its LCOE and power, to
   see when the pick stops moving.

### Decision rule

For each app, the generation after which:

- the hypervolume grows by less than about 0.1% per 50 generations, and
- the pick's LCOE and power move less than they differ between seeds.

The recommended `n_max_gen` is that generation, with some margin, for each
kind of app. Whether `pop_size` should change too (45 designs is also how
finely the front is drawn) is a separate observation from the same data.

## Results

Pending.
