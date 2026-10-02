# AI-Assisted Error Interpretation — Implementation Sketch

*Supporting detail for the "Future Direction — AI-Assisted Error Interpretation" section
of `dev_docs/TANGO_vision_and_roadmap/README.md`. Split out here because it's implementation-level
detail (code, prerequisites) rather than vision-doc-level narrative.*

**Implementation sketch:**

```python
# tango_cli.py — outer try/except in the `run` subcommand
try:
    Workflow.from_file(path).run()
except Exception as exc:
    if ai_interpretation_enabled():
        agent_explain(exc, config=raw_yaml, component_states=last_states)
    else:
        raise
```

The `agent_explain` function can be a thin wrapper around the Claude API (or any
capable model) with a system prompt that describes the TANGO component model and
the most common failure modes. It should be opt-in (controlled by a CLI flag or
config setting) so that users who prefer raw tracebacks or who are working offline
are not affected.

**Error taxonomy prerequisite:** For the agent to produce useful output — and for
human debugging — TANGO needs a stable, identifiable set of exception types. The
design follows the same philosophy as Rust's `thiserror` + `anyhow` crates:
typed, catchable errors at library boundaries (`thiserror`-style), with rich
context chained in as they propagate up (`anyhow`-style via Python's
`raise TangoError(...) from exc`).

Concretely: every CoolProp call must be wrapped so that low-level property-lookup
failures surface as a `CoolPropError` (a TANGO-owned subclass of `TangoError`),
not as a raw `ValueError` or `CoolProp.CoolProp.CoolPropError` buried three frames
deep. The same applies to TESPy, which throws its own mix of solver-convergence and
bad-state-point errors: these become `TESPyError` at the TANGO boundary. With this
in place, callers at any layer of the stack can `except CoolPropError` or
`except TESPyError` (or the broader `TangoError`) and know immediately what kind of
failure they are handling — without parsing traceback strings or catching overly
broad base types like `ValueError`.

**Prerequisites:** Stable component serialization via `model_dump()` (already in place)
and a stable set of error types (`ConvergenceError`,
`FrackingError`, `SaturationError`, `CoolPropError`, `TESPyError`, etc.) with enough
context attached to be useful.
