# Coupling External Simulators

Rules for code that couples tango to another package (RAFT today; other
reservoir or wellbore simulators later), e.g. `src/tango/external/`.

- **tango owns the interface, not the other package.** tango sets the
  boundary values it exchanges with the coupled package and reads back what
  the package returns at that interface. What happens inside the package
  (its discretization, solver tolerances, how it conserves mass along its
  own mesh) is the package's domain, not tango's.
  - Example: RAFT's finite element solution conserves mass over the whole
    well, not element by element. Checking every element's flow from tango
    reached into RAFT's interior; RAFT's developer pointed out it isn't
    tango's concern. tango checks only the inlet and outlet values that cross
    the interface.

- **Check at the interface, and only there.** Validate what tango sends and
  what comes back across the coupling (boundary values, mass rate in vs. out,
  a phase tango's own conversions rely on). Don't add checks on the coupled
  package's internal fields, even when the package exposes them (e.g. RAFT's
  `well_profiles()`): record them if useful, but don't judge them.

- **Never change the coupled package's own setup silently.** If the package's
  config (e.g. a RAFT template) has to match what the coupling needs (which
  end gets a pressure condition, which a flux), check it and raise a
  `ConfigError` naming the mismatch. Don't overwrite it. A silent switch can
  be harmless in one case (a closed loop) and wrong in another (an open
  system).

- **Don't alter the other package.** Never edit its source, and change its
  settings (in a template tango ships, e.g. a solver tolerance) only with its
  developer's agreement, documented where the setting lives. If something
  looks wrong inside the package, report it to its developer (an issue on
  their repository, or a question for the user to pass on) instead of working
  around it in tango.

- **Describe its physics from its own documentation.** Read the package's
  theory document (RAFT: `theory.md` at the pinned tag) before writing
  anything about its equations, equation of state or solver in a comment,
  docstring or reply. Explanations of its internals in tango are context, so
  keep them short and cite the source.
