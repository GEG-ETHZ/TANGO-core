# tango: Progress Summary & Forward Plan — October 2026

*Prepared 2026-10-02, updated 2026-10-05. Covers October 1–5 so far; extend as the month goes
on. Managerial-level summary — for engineering detail, see the GitLab
issues linked below and `dev_docs/tango_tasks.md`. Continues from
`dev_docs/tango_progress_summary_sep_2026.md`.*

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

## Smaller items worth noting

- Documentation split: developer docs moved to `dev_docs/`; `docs/` now
  holds user-facing documentation that ships with the package, starting
  with a verified bibliography (`docs/SOURCES.md`).
- New GitLab issues: EGS stimulation cost (#66), the per-config review
  checklist (#67), cogeneration and seasonal heat demand (#69). Chad is
  now assigned on all of his issues.

## Where things stand

The model is now energy-consistent across component boundaries, and the
example set is complete and regression-tested. Every example now uses
realistic, cited component efficiencies. The next phase is quality:
reviewing each example systematically.

## Immediate next steps

1. Review every example's phase diagram and physics against the checklist
   in GitLab #67, and roll the CO2 EGS example's cleanup (no throttling
   inside heat exchangers, flow-ordered descriptive node names, component
   diagrams) out to all examples.
2. Reservoir mass imbalance (#63, high priority), which builds on this
   month's enthalpy change.
