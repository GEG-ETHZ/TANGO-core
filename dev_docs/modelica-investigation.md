# Rumoca / Modelica investigation (2026-07-29)

Quick, time-boxed spike to gauge whether [Rumoca](https://github.com/CogniPilot/rumoca)
(a Rust-native Modelica compiler) is a promising path forward for TANGO, prompted by
its LSP + playground + explicit multi-stage compiler pipeline looking like a clean,
modern alternative to the usual Dymola/OpenModelica story. See
`dev_docs/long_term_architecture_exploration.md` for the original parked discussion this
follows up on.

Two things were tried: getting the `rumoca-lsp` language server working in Helix
(editor tooling), and building a real multi-component Modelica model against the
Modelica Standard Library (MSL) to see how far a from-scratch system model gets in
one sitting.

## Attempt 1: Helix + rumoca-lsp — not working

- Rumoca's CLI (installed via the project's official install script) does **not**
  include an `lsp` subcommand. The language server is a **separate binary**,
  `rumoca-lsp`, built from the `rumoca-tool-lsp` crate. The install script needs
  `--with-lsp` to pull it in.
- Once installed, `rumoca-lsp` was wired into Helix via `~/.config/helix/languages.toml`
  (not `config.toml` — that file only understands `theme`/`keys`/`editor`; language
  servers are a separate config file, easy first mistake):
  ```toml
  [language-server.rumoca]
  command = "rumoca-lsp"

  [[language]]
  name = "modelica"
  scope = "source.modelica"
  file-types = ["mo"]
  language-servers = ["rumoca"]
  ```
- The binary itself is not broken: a manual JSON-RPC session (raw `initialize` →
  `initialized` → `textDocument/didOpen` on a real `.mo` file, piped over stdio)
  got a clean `initialize` response advertising hover/completion/definition/etc.,
  and did not crash.
- In live use in Helix, though, it reliably dies (`Language server exited`,
  `StreamClosed` in the Helix log) shortly after opening a real buffer. The manual
  stdio replay didn't reproduce it, so the trigger is something about Helix's
  actual session (exact capability negotiation, workspace-folder shape, or
  something Helix sends beyond the bare handshake) — not identified given the
  time-box.

**Where to pick this up:** capture rumoca-lsp's stderr directly (Helix's own log
just says the transport closed, not why) — e.g. wrap the command in a shell script
that tees stderr to a file before handing it to Helix, or run `rumoca-lsp` under
`RUST_BACKTRACE=1` if it supports that. If it's panicking on a specific request,
the backtrace should name it immediately.

## Attempt 2: build a real model against MSL — promising, inconclusive

**The actual MSL question, answered:** Rumoca does **not** bundle the Modelica
Standard Library. It's tested/verified against MSL 4.1.0 (a "180-model MSL parity
gate" is part of its own CI), but consuming it is on the user: point
`rumoca compile`/`rumoca sim` at a local MSL checkout via `--source-root <path>`
(or the `MODELICAPATH` env var). Confirmed by cloning
`github.com/modelica/ModelicaStandardLibrary` at tag `v4.1.0` and pointing rumoca
at it directly — resolution and typechecking against real MSL classes worked with
no friction.

**The model:** a single-flash geothermal loop — sump vessel → pump → adiabatic
down-well pipe → reservoir heat exchanger (lumped thermal-mass reservoir) →
adiabatic up-well pipe → flash valve → phase separator → {vapor: turbine →
condenser, liquid: bypass} → ideal mixing junction → back to the sump. This
mirrors TANGO's own single-flash surface topology (`src/tango/components/surface`),
which is why it was the natural test case rather than a toy example.

MSL has no ready-made two-phase flash-separator or steam-turbine component (this
is normal — most real Modelica system models mix MSL base classes with a handful
of custom components), so two small custom models were hand-written against
`Modelica.Media.Interfaces.PartialTwoPhaseMedium`:
- `FlashSeparator` — static (no-holdup) ideal separator: computes vapor quality
  from the inlet state via `Medium.vapourQuality`, splits mass flow, sets each
  outlet to its saturated enthalpy (`Medium.dewEnthalpy`/`bubbleEnthalpy`).
- `IsentropicTurbine` — expands to a fixed downstream pressure using
  `Medium.setState_psX` at constant entropy, applies an isentropic efficiency,
  outputs shaft torque through a standard `Modelica.Mechanics.Rotational` flange.

Everything else was stock MSL: `Fluid.Vessels.ClosedVolume`,
`Fluid.Machines.PrescribedPump`, `Fluid.Pipes.DynamicPipe` (adiabatic for the
well pipes, `ConstantFlowHeatTransfer` for the reservoir HX and condenser),
`Fluid.Valves.ValveIncompressible`, `Thermal.HeatTransfer.Components.{ThermalCollector,
HeatCapacitor}`, `Thermal.HeatTransfer.Sources.FixedTemperature`,
`Fluid.Fittings.TeeJunctionIdeal`.

**Result:**
- The model **flattened successfully** (`rumoca compile ... --emit flat-mo`)
  against the real MSL checkout, after two small, expected parameter-name fixes
  (`Modelica.Fluid.Machines.Pump` → `PrescribedPump`, since plain `Pump` wants an
  explicit mechanical shaft connector; dropped a bogus `p_nominal` on the valve).
  Error messages were specific enough to fix directly without spelunking through
  MSL source, which is a good sign for usability.
- `rumoca sim ... --inspect structure` (structural/DAE balance check) reports the
  model is **over-determined by 184 equations**. One confirmed bug was found and
  fixed in `FlashSeparator` (a redundant explicit mass-balance equation, already
  implied by the two split-flow equations — fixing it moved the imbalance from
  186 → 184), confirming the diagnostic is trustworthy and actionable. The
  remaining 184 wasn't run down given the time-box; likely candidates are how the
  two-phase medium's `ThermodynamicState`/`SaturationProperties` records interact
  with the custom components' equations, or a `heatPorts` array /
  `ThermalCollector` cardinality mismatch on the reservoir HX or condenser.

**Where to pick this up:** isolate the imbalance by building the model
incrementally (vessel + pump + pipe alone → check balance; add the reservoir HX →
check again; add the flash separator alone on a stub source/sink → check; add the
turbine alone → check) rather than debugging the full 1300-equation flattened
system at once. Rumoca's `--inspect structure` only reports the aggregate
count today, not which specific equations/variables are extra — worth checking
whether a more verbose mode exists, or filing that as a rumoca usability request,
before going down the manual-bisection path.

## Overall verdict

Promising, not conclusive. The concrete finding — rumoca resolves and typechecks
real MSL 4.1.0 classes cleanly via a plain `--source-root` checkout, with useful
error messages — de-risks the "no mature domain library ecosystem" concern raised
in the original parked discussion. Composing custom components with MSL base
classes worked mechanically on the first real attempt. The open question is
whether a genuinely correct, simulatable system model is quick to get right in
practice, or whether DAE-balance bugs like this one are a recurring tax — that
needs one more focused pass (structured bisection as above) to answer, not
re-litigating from scratch. The LSP/editor-integration side is a separate,
unrelated thread that's currently just broken and needs its own debugging
session (see Attempt 1).
