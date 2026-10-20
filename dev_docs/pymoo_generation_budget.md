# How many generations do the opt apps need? (`n_max_gen` study)

Started October 16, 2026. Results October 19, 2026.

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

Submitted October 16, 2026 at commit `bb09ddc7` (a first submission,
17268391–17268418, failed in seconds on a stale uv environment and ran
nothing):

| App | Seed 1 | Seed 2 | Seed 3 |
|---|---|---|---|
| `opt_hydro_direct_heat` | 17269205 | 17269206 | 17269209 |
| `opt_hydro_sf_electric` | 17269210 | 17269211 | 17269212 |
| `opt_AGS_ORC_electric` | 17269213 | 17269214 | 17269215 |

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

All nine runs completed (27,000 evaluations each). Reproduce the numbers and
plots with `uv run python tools/n_max_gen_study_analysis.py` after syncing
`studies/n_max_gen/` from Euler; it writes `studies/n_max_gen/summary.csv`
and one `<app>_progress.png` per app.

**Sanity check passed.** Seed 1 reproduces the 2026-10-14 production runs:
all 45 designs on each app's production front appear, bit-identical, among
seed 1's evaluations up to generation 200.

### Hypervolume and pick per app

HV(200)/HV(600) is the share of the 600-generation hypervolume already
reached at the current cap. "Settled" is the first generation after which
the hypervolume grows by less than 0.1% over the next 50 generations ("—":
never, within 600).

| App | Seed | HV(200)/HV(600) | Settled at | Pick LCOE, g200 → g600 | Pick power, g200 → g600 |
|---|---|---|---|---|---|
| `opt_hydro_sf_electric` | 1 | 0.998 | 155 | 0.6280 → 0.6280 | 1.524 → 1.524 MW |
| | 2 | 0.998 | 170 | 0.6274 → 0.6274 | 1.523 → 1.523 MW |
| | 3 | 0.998 | 144 | 0.6262 → 0.6299 | 1.523 → 1.525 MW |
| `opt_AGS_ORC_electric` | 1 | 0.992 | 325 | 2.083 → 2.073 | 1.421 → 1.419 MW |
| | 2 | 0.996 | 164 | 2.134 → 2.144 | 1.438 → 1.442 MW |
| | 3 | 0.994 | 261 | 2.059 → 2.076 | 1.412 → 1.419 MW |
| `opt_hydro_direct_heat` | 1 | 0.960 | 502 | 0.0339 → 0.0334 | 30.8 → 30.7 MW |
| | 2 | 0.767 | — | 0.0293 → 0.0309 | 29.3 → 29.9 MW |
| | 3 | 0.847 | — | 0.0296 → 0.0308 | 29.5 → 30.0 MW |

### What it means

- **`opt_hydro_sf_electric` and `opt_AGS_ORC_electric`: 200 generations is
  enough.** By generation 200 the front has 99.2-99.8% of its 600-generation
  hypervolume, and the pick moves by at most ~0.8% in LCOE from 200 to 600.
  That's less than the difference between seeds (`opt_AGS_ORC_electric`'s
  picks span 2.07-2.14 $/kWh across seeds at generation 600), so extra
  generations buy less than rerunning with another seed would change.
- **`opt_hydro_direct_heat`: the problem is exploration, not the generation
  budget alone.** Two of three seeds were still improving at 600 and ended
  well below seed 1. The gap is almost entirely the high-power end of the
  front: seed 1 found designs up to 31.9 MW (mass rate at its 100 kg/s cap,
  a ~0.6 m injection well, target extraction pressure at its 10.5 MPa
  ceiling); seeds 2 and 3 topped out at 30.9 MW. Only ~40% of this app's
  evaluated designs were feasible, most of the rest wrongly so (see below),
  which made that corner hard to reach.
  The picks differ by ~8% in LCOE between seeds, much more than they move
  with extra generations.

### Why `opt_hydro_direct_heat` behaves differently

It has six decision variables, no more than the others, so that isn't the
reason. Rerunning 40 of seed 2's infeasible designs locally showed why:

- **15 hit the fracturing limit.** At 5 km, the injection well's outlet
  pressure is the ~49 MPa hydrostatic column plus the injection wellhead
  pressure, against a 53.96 MPa threshold, which leaves roughly 5 MPa of
  injection pressure. The most powerful design found sits 0.01 MPa below
  it.
- **25 were rejected by a bug, not by physics.** The pumped production well
  (`NumericalProductionWellWithPump.solve`) first marched the well without
  the pump, to see whether the pump was needed. When the unaided march
  couldn't lift the flow, its pressure went negative and CoolProp raised,
  so the design was scored infeasible before the pump was ever tried. With
  the pump (intake at ~95 bar), all 25 run fine. Fixed: an unaided march
  that can't lift the flow now just means the pump is needed. The well
  march also now raises a named `SaturationError` when the fluid would boil
  and `WellPressureCollapseError` when the pressure would reach zero,
  instead of an opaque CoolProp failure.

The bug hit high-flow designs hardest, which is exactly the high-power end
of the front, so the seeds' disagreement there partly reflects which of
them happened to find designs the bug let through. Every app whose
production well has a pump (`opt_hydro_sf_electric`,
`opt_hydro_sf_electric_5spot`, `opt_hydro_df_electric`,
`opt_hydro_ORC_electric`, `opt_hydro_direct_heat`, `opt_EGS_electric`,
`opt_EGS_direct_heat`) needs rerunning.

The high-power end also includes production-pump heating: pump work that
ends up as heat in the fluid. For a design away from the limits (60 kg/s),
raising `target_extraction_pressure` from 4.9 to 10.5 MPa adds 616 kW of
pump electricity and 0.44 MW of heat, at a worse LCOE (0.0422 → 0.0497).
That heat is usable and its electricity is paid for (see recommendation 3),
so it's a real trade-off.

### Recommendation

1. **Keep `n_max_gen: 200`** for the apps that behave like
   `opt_hydro_sf_electric` and `opt_AGS_ORC_electric`.
2. **`opt_hydro_direct_heat`: `pop_size` raised to 90** (more designs per
   generation, more diversity to reach the edges of the front). Rerun with
   several seeds to check that they now agree.
3. **Pump heating is counted, and paid for.** Pump work that ends up as
   heat in the fluid is usable heat, so the thermal-power objective
   rightly counts it. Its electricity is charged: the production pump's
   power is subtracted from net electric power, and for a heat plant that
   (negative) electric by-product is priced into O&M at
   `electricity_price` (`DoubletEconomicComponent._compute_lcoe`). The
   pump-heated designs at the front's high-power end are a real trade-off,
   not an artifact.
4. **Archive front available, off by default.** pymoo's final population
   holds at most `pop_size` non-dominated designs (45 here); the
   non-dominated set of everything evaluated has ~270-350 for
   `opt_hydro_direct_heat`. The `report_archive` option (`PymooConfig`,
   `--report-archive`, or `report_archive: true` in `params.yaml`) reports
   the latter without changing the search, but re-solves every reported
   design once for the report columns, an open-ended cost. Off everywhere
   unless a run needs it.

Not yet decided: which of these to adopt, and whether the other
direct-heat apps behave like `opt_hydro_direct_heat` (not tested here).
