# tango: Progress Summary & Forward Plan — October 2026

*Prepared 2026-10-02, updated 2026-10-05, 2026-10-15, 2026-10-26,
2026-10-27, 2026-10-28, and 2026-10-29. Covers October 1–29. Managerial-level summary — for engineering detail,
see the issues linked below (GitLab numbers up to #75, GitHub from #94 on)
and `docs/tango_tasks.md`. Continues from
`docs/archive/tango_progress_summary_sep_2026.md`.*

## Found and fixed an energy leak at every component boundary: components now hand each other enthalpy, not temperature (2026-10-01)

**In plain terms:** each part of the model (wells, reservoir, surface plant)
passed its neighbor a temperature and pressure, and the neighbor
reconstructed the fluid's energy content from them. For CO2 close to its
critical point, that reconstruction is badly wrong — a quarter of a degree
of error becomes a large energy error — so energy silently disappeared at
a component boundary on every pass.

**How big:** in the CO2 EGS heat example, about 40 kJ/kg vanished between
the surface plant and the injection well every year — about 1.1 MW, close
to the plant's entire heat output. A second, smaller leak was found in the
pipe from wellhead to plant, which had been modeled as keeping
temperature constant (creating energy from nothing for CO2) instead of
keeping energy constant.

**Fix:** components now pass energy content (enthalpy) directly, the same
convention the Modelica modeling language uses, and work out temperature
themselves when they need it. Energy is now continuous across every
boundary. The leaks were found because the new phase diagrams showed gaps
in loops that should have closed.

**Effect on results:** water-based examples change by less than 0.1%.
CO2 examples change substantially, because their old numbers carried the
leak: e.g. the CO2 EGS heat example's cost fell 52% (heat output +43%);
the CPG heat example's cost rose 14.5% (the pipe fix).

## Fixed auto-pressure mode depleting the reservoir several times too fast (2026-10-01)

When TANGO solves for the injection pressure automatically, it iterates.
Each iteration was mistakenly counted as another year of heat extraction
from the reservoir, so a year that needed 9 iterations depleted the
reservoir 9 times. Fixed so each year depletes it once, however many
iterations it takes. The affected example's cost fell from 1.19 to 0.84,
and its results no longer depend on the solver's tolerance setting.

## Found a slow runaway in the CO2 EGS power example, redesigned it, and added direct-CO2 power examples (2026-10-01–02)

**The runaway:** with the energy leak fixed, the CO2 EGS power example's
net output went negative after 9 years. The cause: it reinjected lukewarm
CO2 that landed right at a point where CO2's density drops sharply with
small temperature changes. As the reservoir cooled slightly, the injected
CO2 got lighter, the natural circulation (thermosiphon) weakened, and
that made things worse — a runaway. Adding a cooler before reinjection
(cold CO2 is dense and stable) fixed it; the example now runs its full
25 years.

**Direct-CO2 power examples:** the CO2 power examples had used a binary
plant, where the CO2 heats a second fluid that drives the turbine. Using
the CO2 itself in the turbine — the main point of a CO2 geothermal system
— is much better on the same wells: cost 0.40 vs 1.55 (EGS) and 2.90 vs
10.9 (AGS), with realistic component efficiencies. Binary-plant examples now carry `ORC` in their file
names, and both versions are kept.

## Phase diagrams are interactive again, with engineering reference lines and true well paths (2026-10-01–02)

The interactive diagram is back (the September axis bug was traced to the
per-node text labels; names now appear on hover). Each diagram now shows
lines of constant temperature, entropy, density, and vapor quality, as in a
textbook chart, configurable per run; the wells are drawn along their
actual computed paths rather than as straight lines. The diagrams have
already earned their keep: they exposed the energy leak above, a hidden
pressure drop inside a heat exchanger, and the runaway.

## Third-party license compliance is now a release gate (2026-10-01)

Every MR into `main` and every release tag now runs a license check; it
fails if any shipped dependency's license isn't approved. Licenses that
need judgment (e.g. dual-licensed, or GPL with a linking exception) are
approved individually with a recorded reason, and re-flagged if the
license ever changes. All shipped and development dependencies currently
pass. Indirect dependencies matter as much as direct ones for a
distributed binary; none of TANGO's shipped dependencies blocks a
commercial release.

## Replaced idealized 100% turbine and pump efficiencies with published values (2026-10-02)

Nearly every example assumed perfect (100% efficient) turbines and pumps.
They now use published values: turbines 85% and surface pumps 75%
(DiPippo, *Geothermal Power Plants*, 2016), downhole pumps 55% overall
(a Dutch geothermal ESP design study, 2016); sources are collected in
`docs/SOURCES.md`.

**This raises costs substantially for power plants:** single-flash
hydrothermal power costs rise roughly 40–100%, binary plants about 18–21%;
heat plants change little (−5% to +10%). The turbine efficiency is the
largest single driver.

**Three marginal examples needed changes to stay net-positive:**

- *EGS power* ran a flash plant on ~115 degC brine at the real 3000 m site,
  too cold for flashing. Deepened to a hypothetical 5000 m (~174 degC),
  with 50 kg/s and 20 years; cost is now comparable to the hydrothermal
  flash example.
- *CPG power* depleted its reservoir at 200 kg/s; 125 kg/s keeps it
  producing for 20 years and is also its lowest-cost flow.
- *Binary CO2 AGS power* barely produces power with realistic
  efficiencies; shortened to 20 years. Its direct-CO2 sibling is the
  meaningful example for that cell. (After the well fix below it stays
  positive for 30 years, so the shorter run is no longer required.)

## Production wells had their rock temperatures upside down (2026-10-05)

**In plain terms:** each well exchanges heat with the surrounding rock,
which gets hotter with depth. Production wells were given the rock
temperatures in reverse: the bottom of the well saw near-surface rock
and the top saw the hottest, deepest rock. Every production well in every
example was affected. Found
from a phase diagram in which a production well gained heat near the
surface, where it should lose it.

**Effect on results:** small for hydrothermal, EGS and CPG examples (cost
within about 1%, slightly better for power), because their brine leaves
the reservoir at about rock temperature either way. Large for the closed
AGS loops, which collect most of their heat in the wells: the binary CO2
AGS power example's cost fell from 55 to 10.9, the direct-CO2 one by 8%,
and the CO2 AGS heat example's rose 61%. A new test checks that heat in
every well cell flows from hot to cold.

## The injection loop could stop iterating before it had actually closed (2026-10-05)

Each year TANGO iterates until the fluid leaving the surface plant matches
what enters the injection well. A wiring mistake meant the iteration's
own speed-up step never took effect, and the "close enough" test compared
against a value no component had used, so a year could be accepted with
the loop open by up to 3.6 kJ/kg (about 2% of an ORC plant's heat). Every
example now closes within the 1 kJ/kg tolerance; costs moved by under
0.25% except the binary CO2 AGS power example (+4.3%, before the well fix
above) and the auto-pressure example (−1%).

## Optimizations run on many processes again: workers now receive the config, not the live model (2026-10-13)

**In plain terms:** to use all 48 CPUs on Euler, the optimizer copies the
problem to each worker process. Python makes those copies by serializing
the object ("pickling"), and the problem carried a live, fully built model.
After the TESPy upgrade, a model containing a TESPy surface plant can no
longer be pickled (TESPy's units library holds unpicklable functions), so
every multi-process optimization of a TESPy plant failed before evaluating
a single design.

**Fix:** only plain data crosses a process boundary. The optimizer now holds
the config as a dictionary, exactly as written. It builds the model once
up front only to check that the config is valid, then discards it. It
deliberately does not keep the model's own filled-in copy of the config:
that copy pins defaults computed from other inputs (such as each well's
cell count, from its length) at the starting design's values. Each worker
builds its own model from the dictionary for every design it evaluates. The
LHS sweeps and surrogate-validation runs pass the config the same way.

**Why it matters beyond this bug:** parallel runs no longer depend on
whether any third-party solver object can be pickled, so a future solver
or external tool can't break them the same way. This works because the
config dictionary is the single source of truth and a model can always
be rebuilt from it. A test now pickles a TESPy-plant problem, checks that it
carries no live model, and checks that it still evaluates a design.

## Shared config values now have one source (2026-10-14)

**In plain terms:** several components need the same physical quantity
(the reservoir depth sets the well lengths; the depth also sets the
reservoir's starting pressure). Each config used to repeat these values by
hand, so an edit to one copy could leave another stale and the model ran
with both. Each such value is now written once and the rest derived from
it; a config that repeats a value and disagrees with it is rejected.

**Bugs it exposed:** the optimizer and the sweeps had fixed each well's cell
count at the starting design's value, so AGS designs with longer wells ran
on cells up to 4x coarser (up to 1.3% LCOE). Two sweeps moved depth and well
lengths independently, producing physically inconsistent designs. ORC
starting guesses were read in the wrong unit (10x too low). All fixed.
The reservoir's starting pressure is now computed from depth (2% lower than
the old hand-entered value in the hydrothermal configs).

The auto-pressure and auto-flow modes were removed: operating points now
come from the optimization apps instead.

## How a design is picked from each Pareto front, and how long the optimizer needs (2026-10-16–20)

Each optimization returns a Pareto front: designs trading cost against
output, none better than another on both. The recommended design is now
the one closest to the ideal corner (best cost and best output, each scaled
0–1 over the front). It replaces the old pick (closest to the front's
average), which moved whenever the optimizer happened to crowd designs into
one part of the front.

A study on Euler compared 200 and 600 generations over several random
seeds: 200 generations reach 99.2–99.8% of the 600-generation result, and
the pick moves less between generations 200 and 600 than between seeds,
so 200 stays the default. The optimizer can also optionally report every
good design it found, not just its final population's (off by default).

## The production pump was never tried on flows the well couldn't lift alone (2026-10-20)

**In plain terms:** a pumped production well first checks whether it can
lift the flow without its pump. When it couldn't, that check crashed inside
the fluid-property library before the pump was tried, and the optimizer
scored the design infeasible. In a sample of 40 rejected designs from the
hydrothermal heat optimization, 25 were this and run fine with the pump,
so every optimization with a pumped production well had been missing its
high-flow designs. All of them were rerun.

Two failure modes inside a well now raise named errors instead of a
fluid-library crash: the fluid starting to boil (`SaturationError`) and the
pressure falling to zero (`WellPressureCollapseError`), each naming the
well, depth, pressure, temperature, and flow.

## Every well now stays 5% away from boiling or condensing (2026-10-22)

The well models assume the fluid is a single phase, but some designs ran
right at the phase boundary: CO2 condensate entered the injection well
barely subcooled (a 2.4% pressure margin), and near-critical CO2 was
reinjected 4.9% from saturation. Every point in every well must now be at
least 5% (configurable) in pressure away from saturation, or the design is
rejected. The 5% is engineering judgment, documented with the practice that
motivated it. Three CO2 power configs now subcool their condensate by 3 K
instead of 1 K, and the CO2 EGS heat config reinjects at 8.0 MPa instead
of 7.5 MPa.

## Why the optimal designs sat on their search bounds (2026-10-19–26)

**In plain terms:** after the October reruns, most fronts had at least one
design variable pressed against the edge of the range the optimizer was
allowed to search. That means either the edge is a real physical limit, or
it's arbitrary and costing money. Each one was checked by rerunning the
picked design with that variable pushed past the edge:

- **Explain:** the bound is physical, or it costs nothing.
- **Hand off:** the bound is an engineering limit for domain experts to judge.
- **Widen:** the bound is arbitrary and costs LCOE; widen it and rerun.

| Variable at its bound | Apps | Finding | Action |
|---|---|---|---|
| Surface pipe diameter at 0.2 m | most | Pipe friction is free where the plant throttles the fluid anyway; the real limit (flow velocity) isn't modeled | Explain; hand off a velocity limit |
| Wellhead pressure target at 1.3 MPa | hydrothermal flash and ORC | Floor sits just above boiling; extra pressure is thrown away at the flash valve | Floor lowered from 4.9 MPa (12–17% cheaper); #108 |
| Condensing pressure at its floor | CO2 power apps | Floor = cooling limit plus 3 K subcooling | Explain |
| Mass rate at its cap | hydrothermal ORC and heat, EGS heat | More flow fractures the reservoir | Explain |
| Mass rate at its cap | EGS, hydrothermal flash power | Cap was arbitrary (EGS optimum ~150 kg/s, 11% cheaper) | Widened |
| Mass rate at 70 kg/s | CO2 AGS power | Near the optimum (80 kg/s is slightly worse) | Explain |
| Depth at its cap | all AGS | Binding: 9–12% cheaper per extra kilometer | Hand off (drilling cost beyond ~8 km, #120) |
| Loop length 8 km, loop diameter 0.75 m | all AGS | Near their optima | Explain |
| Vertical well diameter at 0.2 m | AGS heat | 0.15 m is 3.5% cheaper; the well can't lift the flow below ~0.08–0.10 m | Floor lowered to 0.15 m |
| ORC feed pump pressure at 0.35 MPa | CO2 EGS ORC | Optimum ~0.30 MPa (1.6% cheaper); falls apart below 0.25 MPa | Floor lowered to 0.25 MPa |
| Injection pressure, well diameter | CO2 EGS ORC, CPG heat | One step past the bound fractures the reservoir | Explain |
| Injection well diameter at 0.6 m | CPG power | 0.7 m is 0.4% cheaper; 0.6 m (24 inch) is already large | Explain; hand off well size |
| Well diameters at 0.15 m | EGS and hydrothermal heat | Below it the production well can't lift the flow | Explain |

Every opt app's bounds now carry a comment saying which of these applies.
The open engineering questions (AGS depth and drilling cost beyond ~8 km,
a surface-pipe velocity limit, well sizes, pump depth) are collected in
GitHub #120 for domain experts. Two related model gaps are tracked
separately: solving the wellhead pressure target from a saturation margin
(#108), and five-spot well patterns, which are costed as a single doublet
and carry the full flow in one injection well (#109); the five-spot
config and its optimization are marked invalid until that is fixed.

## Every example config now runs its optimized design (2026-10-26)

Each example config now holds its optimization's recommended design,
rounded to 3 significant figures, with a header recording where it came
from. Every pick beats the old hand-set design on both cost and output.
Three values sat exactly on a physical edge and were rounded toward the
safe side instead.

| Config | LCOE before → after ($/kWh) |
|---|---|
| CO2 AGS heat | 3.13 → 0.388 (−88%) |
| CO2 AGS ORC power | 14.0 → 4.16 (−70%) |
| Hydrothermal single-flash power | 1.46 → 0.472 (−68%) |
| Hydrothermal double-flash power | 0.980 → 0.424 (−57%) |
| Hydrothermal ORC power | 0.641 → 0.327 (−49%) |
| AGS heat | 1.35 → 0.719 (−47%) |
| AGS ORC power | 3.62 → 2.06 (−43%) |
| CO2 AGS power | 2.89 → 1.66 (−43%) |
| EGS power | 1.55 → 1.02 (−34%) |
| Hydrothermal heat | 0.0539 → 0.0360 (−33%) |
| CO2 EGS ORC power | 1.86 → 1.30 (−30%) |
| CO2 EGS heat | 0.333 → 0.284 (−15%) |
| CPG power | 0.335 → 0.304 (−9%) |
| CO2 EGS power | 0.395 → 0.365 (−8%) |
| EGS heat | 0.0983 → 0.0922 (−6%) |

The CPG heat config keeps its old design for now; see the next section.

## Heat plants that deliver negative heat are now rejected (2026-10-26)

**In plain terms:** the optimizer's pick for the CPG heat example looked
cheapest, but by year 20 its reservoir had cooled so far that the produced
CO2 was colder than the district-heating return water: the plant would
have had to heat the fluid instead of taking heat from it. Nothing
rejected this, so 25 of the 45 designs on that front had it. The model now
rejects any heat plant whose net heat output goes negative in any year,
and the CPG heat optimization is being rerun with that check. (The first
iteration of each year legitimately starts a closed loop from cold fluid,
so the check applies only once each year's iteration has converged.)

## RAFT now simulates an AGS loop's wells and rock, and extracts 1.5–2.4× the heat of tango's own wells (2026-10-15–27)

**In plain terms:** RAFT, the 3D finite-element simulator of wells and
surrounding rock developed by Bruce Gee (GEG), can now stand in for an AGS
loop's whole subsurface: injection well, horizontal well, production well,
and the rock around them. TANGO keeps the surface plant, the yearly loop
iteration, and the economics. The subsurface is one component,
`grouped_subsurface`, with two interchangeable models: tango's own
numerical wells, or RAFT.

**Result:** on the same site and plant, RAFT extracts 1.5–2.4× as much heat
as tango's numerical wells (production temperature 164 → 116 °C over 25
years, against 109 → 100 °C), and the cost of electricity falls from 3.42
to 2.12. RAFT's model was reviewed with its developer and is considered
sound; confidence in the numerical wells' analytical rock heat-exchange
model is lower. RAFT's along-well profiles show where the difference
arises: 1.5–1.7× the heat pickup in the horizontal well, and a production
well that keeps gaining heat on the way up where the numerical one loses
it.

**Guarding against silent errors:** TANGO now records what RAFT does inside
each year (how many internal time steps it took and why it shortened any,
and its pressure, temperature, and flow along the whole well) and stops
with a named error instead of continuing when RAFT accepts an inaccurate
time step, when the flow along the well drifts beyond RAFT's solver
tolerance, or when the water would boil anywhere along the well. CI runs
one simulated year on the real RAFT, so a change on RAFT's side shows up
before it reaches results.

**Found along the way:** the phase diagrams colored a whole well by the
phase at its midpoint, so deep AGS wells looked "supercritical" from top to
bottom; each stretch is now colored by its own phase, for every config.
The ORC power plants in the examples turned out to be modeled as one fixed
design point that only scales its flow as the geofluid cools, never
adjusting its pressures (GitHub #123). TANGO's and RAFT's fluid property
models differ slightly, so TANGO's heat figure for a RAFT run is 0.6–1.2%
lower than RAFT's own; this is documented.

## tango-core 1.1.0 is ready to be released as open source under Apache-2.0 (2026-10-28–29)

**In plain terms:** for FlexGEO's open-source modeling catalogue (D4.2,
due October 31), the whole of tango-core is released publicly rather than
split into separate packages. The group leader approved the Apache-2.0
license, the same one RAFT and METRO use. Version 1.1.0, the first
public release, is ready to be tagged on `main`; it includes the optimized example
designs (GitHub #56) and the RAFT coupling (GitHub #105). Making the
repository (`GEG-ETHZ/TANGO-core`) public and publishing 1.1.0 to PyPI
follow.

**What changed:**

- **License and credit.** The proprietary license and the internal
  distribution notice are replaced by Apache-2.0. ETH Zurich is named as
  the copyright holder, and Chad Baker and Dubhaltach McSweeney as authors,
  with their ORCIDs in the citation file, as ETH's open-source rules
  require. Every source file now states its copyright and license in a
  machine-readable header, and a check on every commit keeps it that way.
  The dependencies' licenses were audited, and all are compatible.
- **One name.** The package is installed as `tango-core`, imported as
  `tango_core`, and run as `tango_core`, where before it was installed as
  `tango-core`, imported as `tango`, and run as `tango_cli`.
- **Releases on PyPI.** Pushing a version tag uploads the release to
  TestPyPI automatically, and to PyPI (`pip install tango-core`) only after
  a maintainer has tried the TestPyPI copy and approved it. PyPI never
  accepts the same version twice, so a broken release can't reach users
  unchecked. No password or token is stored for this.
- **What goes public.** The issues and pull requests were reviewed before
  the switch; a few comments were edited and three issues moved to the
  private operations repository. Internal pages (task log, roadmap,
  progress summaries) stay in the repository but off the public
  documentation site and out of the published package.

**Still open:** making the repository and the documentation site public,
the one-time PyPI setup, and a citable DOI through Zenodo (GitHub #124,
deferred).

## Smaller items worth noting

- `tango_core run` now requires `--save-dir DIR` or `--no-save`, so a run
  can no longer throw its results away because the flag was forgotten
  (GitHub #125). RAFT's own output files are kept alongside tango's when
  `--save-dir` is given.

- Documentation split: developer docs moved to `dev_docs/`; `docs/` now
  holds user-facing documentation that ships with the package, starting
  with a verified bibliography (`docs/SOURCES.md`).
- New GitLab issues: EGS stimulation cost (#66), the per-config review
  checklist (#67), cogeneration and seasonal heat demand (#69). Chad is
  now assigned on all of his issues.
- Euler workflow: `just slurm` submits apps as one sequential chain (one
  node, which is billed far less than several) and refuses an app that
  already has a job queued, after a duplicate submission collided with
  itself; `just slurm-fetch` copies finished results back and pushes them
  to the DVC remote; `just slurm-clean` deletes old logs and partial
  results.
- Topology diagrams for 16 configs, exported to committed SVGs by
  `just diagrams` and checked by a test.
- CI: GitHub Actions now run the license check and release-tag checks
  that GitLab ran. The issue tracker is moving to GitHub by 2026-11-16.
- The surrogate-model optimization app is on hold (GitHub #106).

## Where things stand

The model is energy-consistent across component boundaries, every example
uses realistic, cited component efficiencies, and every example except CPG
heat now runs the design its optimization recommends. The optimizer's
search bounds are each either explained or handed off, and designs that
boil a well, collapse its pressure, or deliver negative heat are rejected
by name. An AGS loop's subsurface can be simulated by RAFT instead of
tango's own wells, with RAFT's internal behavior recorded and its silent
failure modes turned into errors (GitHub #105). All of this is in
version 1.1.0, the first public release, licensed under Apache-2.0, with
releases published to PyPI through a checked, two-stage process.

## Immediate next steps

1. Apply the rerun CPG heat optimization's pick to its config.
2. Domain-expert review of the engineering limits in GitHub #120.
3. Make the repository and the documentation site public, finish the
   one-time PyPI setup, and publish 1.1.0 to PyPI.
4. Review every example's phase diagram and physics against the checklist
   in GitLab #67.
5. Reservoir mass imbalance (#63, high priority).
6. Make the RAFT coupling's CI job a required check.
