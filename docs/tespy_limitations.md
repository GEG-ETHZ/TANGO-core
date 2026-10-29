# What TESPy silently accepts

A running list of things TESPy (the surface-plant solver behind
`GraphSurface`, `src/tango_core/components/surface/graph.py`) solves or returns
**without complaint** even though the result is physically wrong, ill-posed,
or not what the config meant. These are hard to catch because nothing
raises: a run finishes and produces a plausible-looking LCOE.

Keep this list current: add an entry whenever a new case turns up. It is
the evidence base for GitLab issue #71 (assess TESPy's suitability for
surface-plant simulation and investigate alternatives).

Each entry says what TESPy allows, where it hit TANGO, and what guard TANGO
has (or "none"). Entries tagged *[TANGO]* or *[CoolProp]* are not TESPy's
own behavior but belong to the same picture: silent wrong answers in the
surface-plant path.

## A pump can produce power and a valve can raise pressure

**TESPy allows:** with a fixed outlet pressure, a `Compressor` (used for
pumps) solves to negative power when the loop's natural driving pressure
(e.g. a thermosiphon) already exceeds the target: the pump "generates"
work. A `Valve` likewise solves to an outlet pressure *above* its inlet
when the natural pressure falls short. TESPy only solves square equation
systems, so one network can't decide which of the two the plant needs.

**TANGO workaround — the `PumpOrValve` pseudo-type:**

- `GraphSurface.init()` builds two complete TESPy networks, one with the
  node as a `Valve` and one as a `Compressor`.
- Each `solve()` tries the Valve network first and falls back to the
  Compressor network if the Valve result is invalid
  (`InvalidPowerStateError`) or fails (`TESPyCoolPropError`).
- `_check_pump_or_valve_validity` defines "invalid": a Compressor with
  power below `-_PUMP_POWER_TOLERANCE_W` (1 mW), or a `role: net_electric`
  Valve whose pressure rises.
- On the Valve leg, `efficiency` is ignored and the node is left out of the
  net-power sum.
- The workflow's loop check counts `PumpOrValve` as a pressure source.

**Remaining gaps:**

- The fallback is triggered by any `TESPyCoolPropError` on the Valve leg,
  including a genuine CoolProp failure that has nothing to do with whether
  `circulation_control` is a valve or a pump. The retry can't fix that, and
  the Compressor leg then fails for its own reason, so the error the user
  sees names the wrong problem. `InvalidPowerStateError` is no longer
  retried in general: only `ValveCannotRaisePressureError` (the Valve leg's
  pressure rose) and `TESPyConvergenceError` trigger the Compressor leg, so
  e.g. an ORC feed pump's negative power is reported as itself.
- A loop that resolves to a passive valve has no startup pump costed (#57).
- *[TANGO]* A `PumpOrValve` that runs as a pump is never costed:
  `DoubletEconomicComponent._injection_pump_cost` only counts nodes whose
  config type is `Compressor` (#72).
- *[TANGO]* A plain `type: Valve` node tagged `role: net_electric` is
  accepted and silently left out of the net-power sum
  (`GraphSurface._build_bundle`). A Valve does no work, so the tag can only
  be a config mistake; it should raise at build time. Guard: none.
- The longer-term replacement is a custom hybrid TESPy component, which
  needs a newer TESPy (see the version pin below).

**Where it hit:** the AGS closed loop originally had no pump anywhere
(`docs/bugs-fixed-in-tango.md`, "AGS closed loop has no pump
anywhere"; commit `0ecee63`). `CO2_EGS_direct_heat.yml` once resolved to a
phantom ~14 kW pump because its heat-exchanger outlet pressure was set too
low (commit `6b55b15`).

## A heat exchanger with a fixed outlet pressure above its inlet raises pressure for free

**TESPy allows:** `SimpleHeatExchanger`'s own equations are mass, fluid,
and energy balance; pressure is whatever the specs say. An absolute outlet
pressure (`p_out_megapascals`) above the actual inlet pressure solves
normally: the heat exchanger compresses the fluid and no work is charged
anywhere, so the downstream pump's work is understated.

**Why configs use an absolute value at all [TESPy + CoolProp]:** TESPy's
default initial guess for a new connection is below CO2's 5.18 bar triple
point, so a plain `pressure_ratio` fails outright with a CoolProp
out-of-range error. A fixed absolute pressure sidesteps that.

**Where it hit:**

- `CPG_direct_heat.yml`: fixed once (commit `09fcb48`: LCOE was a
  fictitious 0.031 instead of 0.27 USD/kWh), then regressed: the inlet
  fell to 32–44 bar against a fixed 50 bar outlet.
- `CO2_EGS_direct_heat.yml`: a fixed 11.0 MPa outlet against an inlet of
  104 bar falling to 89 bar.
- Both went unnoticed until the phase diagrams showed them, because the
  inlet pressure is set at run time by the wells.
- In both, the free compression was propping up the loop: it let the CO2
  be reinjected dense. With the pressure rise removed, both needed an
  injection cooler to reinject the CO2 cold and dense instead.

**TANGO guard:** `GraphSurface._check_passive_pressure` raises
`PassivePressureRiseError` whenever a heat exchanger, valve, separator,
mixer or cycle closer has a higher outlet pressure than inlet pressure
(checked after every solve). It is raised straight through the
`PumpOrValve` fallback, since switching `circulation_control` to a pump
can't fix an upstream node. `_validate_pressure_monotonicity` separately
compares *declared* `p_out_megapascals` values when the config is loaded.

## A heat exchanger with no pressure spec absorbs any pressure gap

**TESPy allows:** with neither `p_out` nor `pressure_ratio`, a heat
exchanger's inlet pressure (from the wells) and outlet pressure (from
`injection_pressure`) are pinned independently, and the component enforces
no relation between them. It silently absorbs whatever difference there is,
in either direction.

**Where it hit:** `AGS_direct_heat.yml` (commit `8708701`); now uses
`pressure_ratio: 0.99` plus a `PumpOrValve`.

**TANGO guard:** none in general; documented as a known gap in
`_validate_pressure_monotonicity`'s docstring and `docs/tango_tasks.md`.

## Large throttling inside a heat exchanger looks like normal operation

**TESPy allows:** a fixed outlet pressure far below the inlet is solved as
a heat exchanger with a huge pressure drop, so throttling that belongs in a
valve (and the wasted pressure it represents) is hidden inside the heat
exchanger.

**Where it hit:** `EGS_direct_heat.yml`'s heat exchanger drops 70 → 15 bar
(2026-10-02 runs). Similar large valve drops: `hydro_direct_heat.yml`
(70 → 20 bar), `CO2_EGS_ORC_electric.yml` (170 → 75 bar).

**TANGO guard:** none; manual check in #67.

## Over-specified or contradictory specs on one connection

**TESPy allows:** two specs pinning the same connection (e.g. a pump
`p_out` and `injection_pressure`; or a condenser's `T_out` and `x = 0` at a
fixed pressure) give an over-determined system. Depending on the case this
fails confusingly at solve time rather than at construction.

**Where it hit:** `AGS_direct_heat.yml`, `CPG_electric.yml` (see their
comments); `docs/bugs-fixed-in-tango.md`.

**TANGO guard:** convention only (no `p_out` on the circulation device).

## Unknown or misspelled config keys *[TANGO, surface nodes fixed]*

- Surface nodes: any key `GraphSurface` doesn't read, including a typo or
  a bare `p0_megapascals_out` / `h0_out` without the `{N}` port suffix,
  raises `ConfigError` listing the allowed keys (`_check_node_keys`).
  Before, such keys were silently ignored.
- Pressure units are now consistent: `p_out_megapascals` and the starting
  guess `p0_megapascals_out{N}` are both in MPa and converted to bar for
  TESPy. The old `p0_out{N}` key was passed through unconverted (bar), and
  the ORC configs and opt apps wrote MPa values into it, so their guesses
  were 10x too low. `h0_out{N}` stays in kJ/kg, TESPy's enthalpy unit here.
- TESPy's own component attributes behave the same way: a wrong attribute
  name fails silently at construction and only errors, confusingly, at
  solve time.

**TANGO guard:** none (contrast the phase-diagram config loader, which
rejects unknown keys).

## An unconverged solve returns normally

**TESPy allows:** `Network.solve()` can stop short of its convergence
tolerance and return without raising, leaving outlet values that may be
wrong.

**TANGO guard:** `GraphSurface` raises `TESPyConvergenceError` (a
`ConvergenceError`, so optimizers treat it as infeasible) whenever
`network.converged` is false. CoolProp failures inside TESPy surface as a
bare `ValueError`, which TANGO wraps as `TESPyCoolPropError`.

**A stall on pumps drawing saturated liquid, gone under exact HEOS.** With
the tabular `BICUBIC&HEOS` backend, TESPy sometimes stopped about 1 J/kg
short on the efficiency equation of a pump drawing exactly saturated liquid
(`hydro_df_electric.yml`'s `condensate_pump`, `EGS_electric.yml`'s
`brine_pump`) with every other equation satisfied. TANGO used to accept that
case with a warning. Under exact `HEOS`, the default since 2026-10-07, no
template stalls, and under `BICUBIC&HEOS` the stall came and went with
the run length and even between identical runs, so it was table noise.
The acceptance path was removed: an unconverged solve always raises.

**Condensers are subcooled.** Condenser outlets use
`subcooling_K: 1.0` (TESPy's `td_bubble`, relative to saturation at the actual
outlet pressure) instead of exactly saturated liquid, which also gives the
pump a margin against cavitation. A subcooled outlet can need TESPy
starting guesses (`p0_megapascals_out1`, `h0_out1`): without them,
`hydro_df_electric.yml` diverged in year 0 under `BICUBIC&HEOS` (it
converges without them under exact `HEOS`). Separator liquid can't be
subcooled. Every example condenser is now subcooled; the ORC and
`CPG_electric.yml` condensers needed their condensing pressure raised first
so the subcooled outlet stays above the site's cooling limit (surface
temperature plus approach, enforced by `GraphSurface._check_cooling_limit`;
GitLab #73).

## Power and heat are in watts regardless of the network's units

**TESPy allows:** `Network.units.set_defaults(enthalpy="kJ / kg")` changes
connection units only;
component `P.val` / `Q.val` are always in W, positive into the fluid. This
caused a silent 1000x power error during development.

**TANGO workaround:** net totals are summed as `-P.val` / `-Q.val` over
role-tagged nodes; negative net power raises `NegativeNetPowerError` only
when the plant has a `Turbine` (checked once per timestep, on the converged
state), and negative net thermal power raises
`NegativeNetThermalError` when the plant has `net_thermal` nodes.

## TESPy's own warnings are suppressed *[TANGO]*

`GraphSurface` sets `TESPyLogger` to `ERROR` (after importing tespy, which
resets it) to silence noisy "invalid value for pr/zeta" warnings. Genuine
bound violations are hidden along with the noise.

## Old TESPy versions started from a random guess *[TESPy, fixed by upgrade]*

`pyproject.toml` pinned `tespy==0.7.1.post1` until 2026-10-12. That version
started any mass flow without a guess from the global random number
generator, so the same ORC design could converge in one run and fail in the
next. On a 40-design sample of each ORC app's bounds, 45 designs failed to
converge. TESPy 0.11.2 seeds each starting value by its component's label,
and none of the same designs fail to converge. Its Newton solver is still
sensitive to the starting guess (oemof/tespy#314), and there is no warm
start: every solve begins from scratch.

## Tabular CoolProp errors near phase boundaries *[CoolProp, fixed by default]*

The `BICUBIC&HEOS` backend interpolates from a table, and TESPy trusts its
lookups without checking them. Since 2026-10-07 tango defaults to exact
`HEOS` (about 1.4-2.2x the runtime) because of two failures:

- **Just below saturation.** With a fixed outlet pressure, TESPy turns
  `subcooling_K` (`td_bubble`) into a fixed enthalpy once, before solving, from a
  (P, T) flash 1 K below saturation. `BICUBIC&HEOS` sometimes returns the
  wrong side of the saturation curve: for R245fa it gives 257.5 kJ/kg at
  0.145 MPa (exact: 230.8) and 343.7 kJ/kg at 0.14 MPa (exact: 229.6), while
  0.125 and 0.15 MPa are exact. `hydro_ORC_electric.yml` at 0.145 MPa had a
  13% vapor condenser outlet, a feed pump compressing wet vapor (201 kW
  instead of ~48 kW), and a solve that reported convergence. The CO2
  condensers in `CO2_AGS_electric.yml`/`CO2_EGS_electric.yml` were subcooled
  1.37 K instead of 1 K. Whether a pressure works depends on where it falls in
  the table, so a working pressure says nothing about its neighbors.
- **Near the CO2 critical point.** Table cells are coarse there:
  rebuilding enthalpy from (T, P) lost up to 42 kJ/kg per component boundary
  (about 1.1 MW in the CO2 EGS heat example) until streams carried enthalpy
  directly (commit `e11d0e6`), and a fixed 315 K target once solved to
  ~305.3 K. It also produces small run-to-run jitter (~3e-5 relative in
  CAPEX/LCOE; commit `4b6583d`).

A config can still opt into `common.coolprop_backend: BICUBIC&HEOS` for
speed; check its results against `HEOS` first.

## Negative heat extraction is accepted *[physics, no guard]*

Near CO2's critical point a small pressure change can dominate the enthalpy
balance, and a direct-heat design can converge to negative heat output.
`CO2_AGS_direct_heat.yml` did at 3000 m (confirmed by an independent
CoolProp check) and was deepened to 6000 m. A related case:
`CPG_direct_heat.yml` currently reinjects CO2 hotter than its reservoir, so
the reservoir contributes no heat and all delivered heat is pump work
(2026-10-02 runs). Nothing stops a direct-heat design from extracting
nothing, or less than nothing.
