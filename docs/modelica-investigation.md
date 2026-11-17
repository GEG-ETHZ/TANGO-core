# Modelica and Rumoca investigation

**Investigation, not adopted.** This page records what we learned by building geothermal models in [Rumoca](https://github.com/CogniPilot/rumoca), a Rust-native Modelica compiler, as a possible future modeling layer for TANGO. It covers why we looked, what ran, what broke and why, and how the result compares with TANGO's current TESPy plant. The framing and the open questions live in [`long_term_architecture_exploration.md`](long_term_architecture_exploration.md).

**Short version (2026-11, Rumoca 0.10.4):** an R134a organic Rankine cycle (ORC) built from DLR's ThermofluidStream library simulates in Rumoca, and every state point matches CoolProp and the equivalent TESPy network to within 0.0001 kJ/kg. Getting there took patches to 44 files of ThermofluidStream's source. The patches work around Rumoca language gaps, which we reduced to 14 self-contained reproducers plus one that needs the library. One gap silently produces wrong results. Rumoca's solver was not the problem; its coverage of the Modelica language used by fluid libraries was.

## Why we looked

TANGO couples the injection well, reservoir, production well, and surface plant into a closed loop and steps it through time. Today it solves that loop sequentially. [`SystemBCIteration`](../src/tango_core/orchestrators/system_bc_iteration.py) cuts the circuit at the injection well, guesses the injection enthalpy, solves each component in order, and relaxes the guess until the loop closes. The run log of `templates/hydro_ORC_electric.yml` shows one to five such passes per yearly timestep. The surface plant is a TESPy network. TESPy solves the plant simultaneously, but some plant pressures must be fixed as design constants rather than derived from flow resistance.

We want temperature, pressure, and mass flow fully coupled as one system of differential-algebraic equations (DAEs):

- **Coupled constraints.** "Injection pressure stays below the fracturing pressure" becomes an equation instead of nested fixed-point loops.
- **Hourly surface-plant steps.** The plant should respond to hourly ambient temperature and hourly mass-flow changes. The plant settles in minutes, so a quasi-steady solve per hour is enough; fast plant dynamics aren't needed.
- **Reservoir coupling both ways.** The reservoir should be usable either inside the coupled system or as a separately time-marched component.
- **External simulators.** Other tools should couple through FMI.

Modelica fits this problem. It is a standardized language for writing models as equations, not a solver. A Modelica tool compiles a model into a hybrid DAE system (continuous equations plus events), reduces and sorts it, and hands it to a numerical solver. Connectors enforce conservation at every junction. Commercial Modelica tools are expensive, and OpenModelica has no native macOS binaries. Rumoca is open source, written in Rust, has a Python story, and uses the diffsol DAE solver. That made it the option to test.

## The ORC spike (2026-11, Rumoca 0.10.4)

### What we built

ThermofluidStream (DLR, BSD-3) is a Modelica fluid library built to avoid large nonlinear equation systems. That makes it a gentler target for a young compiler than MSL's `Modelica.Fluid`. We adapted its `Idealized.Examples.ClausiusRankine.Step7ClosedLoop` into a closed R134a cycle: pump, preheater, evaporator, superheater, turbine, condenser, subcooler, and a loop breaker that imposes the pump inlet state and checks that the loop closes. Mass flow steps from 10 kg/s to 12 kg/s mid-run, standing in for an hourly flow change.

| Component | Outlet | At 10 kg/s |
|---|---|---|
| Pump (isentropic efficiency 0.75) | 25 bar, 28.31 °C | 19.2 kW |
| Preheater | saturated liquid, 77.58 °C | 785.2 kW |
| Evaporator | saturated vapor, 77.58 °C | 1,111.6 kW |
| Superheater | 85.00 °C | 125.0 kW |
| Turbine (isentropic efficiency 0.80) | 7.7 bar, 37.15 °C | 192.0 kW |
| Condenser | saturated liquid, 29.99 °C | −1,806.0 kW |
| Subcooler | 27.00 °C | −43.1 kW |

- **Power and efficiency:** 172.8 kW net at 8.55% thermal efficiency.
- **Balances:** the energy balance closes to about 1e-10 W, and the loop-closure mismatch is zero.
- **Flow step:** all powers scale by 1.2 at 12 kg/s.
- **Cross-checks:** every state point matches CoolProp 6.8.0, and a TESPy 0.11.2 network of the same cycle gives identical states and powers. That network uses the component types `GraphSurface` uses: `CycleCloser`, `Compressor` as pump, `SimpleHeatExchanger`, and `Turbine`.
- **Timing** (Apple Silicon laptop, `rumoca sim bench`):

  | | One-time cost | Per state |
  |---|---|---|
  | Rumoca 0.10.4 | 9.1 s (5.7 s compile, 3.4 s backend build) | 0.26 ms (502 states in 0.13 s) |
  | TESPy 0.11.2 | 0.03 s (build and first solve) | 6.1 ms (warm re-solve) |

  Break-even is about 1,600 states. A year of hourly steps (8,760) would take about 11 s in Rumoca and about 53 s in TESPy. The comparison flatters Rumoca: the loop breaker makes this ORC an explicit chain with no coupled algebraic blocks, while TESPy runs a full Newton solve every time. A two-stream heat exchanger model would add nonlinear systems on Rumoca's side.

This is the idealized cycle. Each heat exchanger is a single stream with a specified outlet state, and mass flow is prescribed. TANGO's production ORC (`templates/hydro_ORC_electric.yml`) uses two-stream heat exchangers with brine on one side and R245fa. The ThermofluidStream components for that (discretized heat exchangers, pumps, and turbines) are blocked by gaps R12 and R13 below.

### What broke in Rumoca, and why

The table below lists the gaps. Out of the box, none of ThermofluidStream's 11 top-level examples and only 2 fluid-free base models of its roughly 90 `Idealized` examples simulate on 0.10.4. Each ID is a self-contained reproducer in the reproduction bundle.

| ID | Gap | Effect on ThermofluidStream |
|---|---|---|
| **R01** | **Silent wrong result.** With `Evaluate=true` on an enumeration parameter, an `if`-equation comparing it to a literal takes the `else` branch when the enumeration type shares its name with the enclosing model. No warning. | `Idealized.Processes.Isobaric` and `Adiabatic` ignore their outlet specification. The first ORC that ran had a superheater cooling the fluid and a 1.8 MW energy imbalance. |
| R03 | `integer(div(a, b))` with Integer arguments compiles, then fails at simulation with a type-mismatch error. | R134a spline lookup, so every R134a property call |
| R04 | Record output fields set on different branches are rejected. | IF97 water and R134a property functions |
| R05 | `extends` modifiers on a record aren't used as defaults inside functions. | R134a Helmholtz coefficients |
| R07 | Record arrays sized by a record parameter fail the shape proof. | R134a Helmholtz coefficients |
| R08 | `scalar(size(v))` is unsupported. | R134a spline lookup |
| R09 | Calls to functions without outputs, used as statements, are unsupported. | R134a phase guard; MSL `Math.Nonlinear` (`error()`), so all IF97 and ideal-gas inversions |
| R10 | `assert` levels must be literals. | Every component, through `dropOfCommons.assertionLevel` |
| R12 | Package redeclares through a short class definition are lost. | All discretized heat exchangers |
| R13 | Function redeclares are rejected as "not a subtype" when the partial function carries a replaceable package. | Pump, compressor, and turbine |
| R14 | `getInstanceName()` is unsupported. | Nearly every component |
| R15 | `while` loops need a translation-time bound. | Bisection and Newton loops in media |
| R16 | An unknown solver annotation (`Dassl`) is a hard error. | Every example |
| R17 | Enumeration literals through an import alias in a modifier aren't parameter expressions. | Conditional connectors |

Seen only inside the libraries so far:
- A segfault on a function with three local constant aliases of the R134a spline tables, one unused. It reproduces against the libraries, with a passing control.
- A record set by a declaration modifier that isn't counted as defined.
- A zero-length array with `StateSelect.always` that fails the structural proof.

Each gap has a physics-preserving workaround in the patch. The one exception is the R134a phase-boundary guard, which is commented out. Most gaps sit in the media libraries' function code: records, loops, and statement calls. That code is what stands between Rumoca and `Modelica.Media`-style property models generally, not just R134a.

**What worked:**
- Structural analysis and the diffsol-backed simulation were solid, and once a model compiled, its numbers were exact.
- Diagnostics carry real source spans, so every workaround was quick to find.
- `--inspect structure` lists the BLT blocks and the variable-to-equation matching. That's how R01 was traced to the wrong equation.
- Rumoca also has steady-state gradients, adjoints, and a `--serve-stdio` mode that steps a model from another process. These cover optimization and hourly stepping from Python.

### What we found in ThermofluidStream

- Three directories have a `package.order` but no `package.mo`, which is invalid Modelica.
- `Processes.Turbine` is an ideal-gas model, unsuitable for ORC vapor near saturation. Its ideal-gas check compares `R_in` with itself, so it never fires.
- `Idealized.Processes.Adiabatic` with its `FullMedium` model uses real-fluid isentropic expansion, `h(p_out, s_in)`, and is the right component for ORC turbines and pumps.

## Earlier spike (2026-07, Rumoca 0.9.x)

- **MSL resolves cleanly.** Rumoca doesn't bundle the Modelica Standard Library; it reads a local MSL 4.1.0 checkout passed with `--source-root`. A source root must contain only libraries: a repository root holding other `.mo` trees fails to parse.
- **A single-flash geothermal loop flattened but was over-determined.** It was built from MSL `Fluid` components plus a hand-written flash separator and isentropic turbine, and it came out over-determined by 184 equations. That model was not re-run on 0.10.4.
- **The `rumoca-lsp` language server crashed in Helix** shortly after opening a buffer, although a manual JSON-RPC session worked. This was not re-tested.

## Where this stands

- **Rumoca is a credible path for an equation-based TANGO plant model, not yet a usable one.** The work needed is language coverage in Rumoca, not numerics.
- **We plan to contribute** the reproducers, help with the media-library gaps, and look into an ExternalMedia/CoolProp bridge, which TANGO needs for working fluids like R245fa.
- **The next modeling step** is two-stream heat exchangers and pressure-driven flow, once R12 and R13 are fixed. Then hourly stepping from Python through `--serve-stdio`.
- **`tango_core` work is unaffected.**
