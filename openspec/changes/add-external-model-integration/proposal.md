# Proposal

## Why

TANGO is the integrating framework for models built by other teams: in FlexGEO alone, the reversible ORC / heat pump (T2.2), the HT-ATES model (GOLEM), DH Profile Modelling, GeoDENs and the Hotmaps dispatch module; RAFT before them. These models were written to answer their authors' questions, not to be called from another program. The first integrations show the same problems again and again: code that is not an installable package, exact version pins that conflict with TANGO's, one operating point per call, warnings as English sentences, no tests, and validity ranges stated only in a README. Some partners do not use version control at all.

Each integration has so far been worked out from scratch. `.agent/rules/external-coupling.md` holds the lessons from RAFT (TANGO owns the interface; check only at the interface; never change the other package), but nothing states what a coupled model must provide, how TANGO wraps it, or how the work is agreed with its authors.

The lesson from earlier work is also that rewriting a partner's model in TANGO is not an option: it duplicates their work, drifts from their version, and loses their ownership of the physics. The work is to make their model usable, together with them.

This change turns the RevORC integration (the first done this way) into a reusable specification, so the next integrations start from it.

## What Changes

- Add the capability `external-model-integration`: requirements that every coupling of an external model to TANGO meets, on the TANGO side and on what the external package provides.
- Define the integration process: for each model, an OpenSpec change in the model's own repository (what the package provides, agreed with its authors, with who does each task) and one in TANGO-core (the coupling), the TANGO change referring to the other.
- Define a readiness checklist for external packages: installable, tested against stored reference outputs, documented with units and validity ranges, machine-readable bounds and status, batch evaluation, a licence, dependency ranges compatible with TANGO's.
- Define the TANGO side: a wrapper module per model in `src/tango_core/external/`, a backend protocol so a model can be replaced (surrogate, then detailed model), an optional dependency group pinned to the authors' releases, interface checks with an error/warn policy, and a test that the wrapper reproduces the package's own reference outputs.
- Point `.agent/rules/external-coupling.md` and `src/tango_core/external/` documentation at the spec, and audit the RAFT coupling against it.

### Non-goals

- Coupling any particular model. RevORC is coupled in `add-revorc-coupling`, which follows this spec.
- Rules for models that TANGO itself owns (wells, TESPy plants).
- A plugin system or entry points for third-party components. Every coupling is a registered TANGO component with a wrapper, as today.

## Capabilities

### New Capabilities

- `external-model-integration`: the requirements and process for coupling a model owned by another team to TANGO.

### Modified Capabilities

None. No specs exist yet in `openspec/specs/`.

## Impact

- New spec, `openspec/specs/external-model-integration/spec.md`, on archive.
- `.agent/rules/external-coupling.md`: refers to the spec; keeps its RAFT examples.
- New `src/tango_core/external/README.md`: how to add a coupling, linking the spec.
- `src/tango_core/external/raft_wrapper.py` and its tests: audited; gaps recorded in `.agent/FINDINGS.md`, not fixed here.
- No code behaviour changes.
