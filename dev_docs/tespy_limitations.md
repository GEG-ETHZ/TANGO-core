# What TESPy silently accepts

A running list of things TESPy (the surface-plant solver behind
`GraphSurface`, `src/tango/components/surface/graph.py`) solves or returns
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

- The fallback catches *any* `TESPyCoolPropError` on the Valve leg, so a
  genuine CoolProp failure is silently retried as a pump.
- A loop that resolves to a passive valve has no startup pump costed (#57).
- The longer-term replacement is a custom hybrid TESPy component, which
  needs a newer TESPy (see the version pin below).

**Where it hit:** the AGS closed loop originally had no pump anywhere
(`dev_docs/bugs-fixed-in-tango.md`, "AGS closed loop has no pump
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
  fictitious 0.031 instead of 0.27 USD/kWh). It has **regressed**: in the
  2026-10-02 runs the inlet is 32–44 bar against a fixed 50 bar outlet,
  every year.
- `CO2_EGS_direct_heat.yml`: the fixed 11.0 MPa was chosen below a
  ~11.3 MPa natural wellhead pressure, but the inlet is now 103 bar in
  year 0 falling to 88 bar, below the 110 bar outlet every year.
- Both regressions went unnoticed until the phase diagrams showed them,
  because the inlet pressure is set at run time by the wells and nothing
  compares it with the fixed outlet.

**TANGO guard:** none at run time. `_validate_pressure_monotonicity` only
compares *declared* `p_out_megapascals` values with each other. GitLab #67's
review checklist has a manual "no passive node raises pressure" check;
#62 covers valve pressure direction and efficiency bounds.

## A heat exchanger with no pressure spec absorbs any pressure gap

**TESPy allows:** with neither `p_out` nor `pressure_ratio`, a heat
exchanger's inlet pressure (from the wells) and outlet pressure (from
`injection_pressure`) are pinned independently, and the component enforces
no relation between them. It silently absorbs whatever difference there is,
in either direction.

**Where it hit:** `AGS_direct_heat.yml` (commit `8708701`); now uses
`pressure_ratio: 0.99` plus a `PumpOrValve`.

**TANGO guard:** none in general; documented as a known gap in
`_validate_pressure_monotonicity`'s docstring and `dev_docs/tango_tasks.md`.

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
comments); `dev_docs/bugs-fixed-in-tango.md`.

**TANGO guard:** convention only (no `p_out` on the circulation device).

## Unknown or misspelled config keys are dropped *[TANGO]*

- `_apply_node_config` reads only the keys it knows; any other key on a
  surface node, including a typo, is silently ignored.
- A bare `p0_out` / `h0_out` (without the `{N}` port suffix) never matches
  a connection and is a silent no-op.
- Units are inconsistent: `p_out_megapascals` is converted MPa → bar, but
  `p0_out{N}` / `h0_out{N}` pass straight through in TESPy's network units
  (bar, kJ/kg), so `p0_out1: 75` means 7.5 MPa.
- TESPy's own component attributes behave the same way: a wrong attribute
  name fails silently at construction and only errors, confusingly, at
  solve time.

**TANGO guard:** none (contrast the phase-diagram config loader, which
rejects unknown keys).

## An unconverged solve returns normally

**TESPy allows:** `Network.solve()` can run out of iterations and return
without raising.

**TANGO guard:** `GraphSurface` checks `network.converged` but only logs a
warning; the unconverged outlet values are still used. CoolProp failures
inside TESPy surface as a bare `ValueError`, which TANGO wraps as
`TESPyCoolPropError`.

## Power and heat are in watts regardless of the network's units

**TESPy allows:** `h_unit="kJ / kg"` changes connection units only;
component `P.val` / `Q.val` are always in W, positive into the fluid. This
caused a silent 1000x power error during development.

**TANGO workaround:** net totals are summed as `-P.val` / `-Q.val` over
role-tagged nodes; negative net power raises `InvalidPowerStateError` only
when the plant has a `Turbine`.

## TESPy's own warnings are suppressed *[TANGO]*

`GraphSurface` sets `TESPyLogger` to `ERROR` (after importing tespy, which
resets it) to silence noisy "invalid value for pr/zeta" warnings. Genuine
bound violations are hidden along with the noise.

## The pinned TESPy version is old

`pyproject.toml` pins `tespy==0.7.1.post1` (Dec 2023; current release is
0.11.x). That version has no custom-component API, its Newton solver is
sensitive to the initial guess (oemof/tespy#314), and there is no warm
start: every solve begins from scratch. The bump is in the backlog
(`dev_docs/tango_tasks.md`).

## Tabular CoolProp errors near the CO2 critical point *[CoolProp]*

The `BICUBIC&HEOS` backend loses accuracy near the critical point:
rebuilding enthalpy from (T, P) lost up to 42 kJ/kg per component boundary
(about 1.1 MW in the CO2 EGS heat example) until streams carried enthalpy
directly (commit `e11d0e6`). It also produces small run-to-run jitter
(~3e-5 relative in CAPEX/LCOE; commit `4b6583d`). A saturated state such as
a condenser outlet can't be rebuilt from (T, P) at all, so node states are
read as enthalpy straight off the TESPy connection.

## Negative heat extraction is accepted *[physics, no guard]*

Near CO2's critical point a small pressure change can dominate the enthalpy
balance, and a direct-heat design can converge to negative heat output.
`CO2_AGS_direct_heat.yml` did at 3000 m (confirmed by an independent
CoolProp check) and was deepened to 6000 m. A related case:
`CPG_direct_heat.yml` currently reinjects CO2 hotter than its reservoir, so
the reservoir contributes no heat and all delivered heat is pump work
(2026-10-02 runs). Nothing stops a direct-heat design from extracting
nothing, or less than nothing.
