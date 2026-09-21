# State Management Framework Evaluation

**Superseded, never filled in (as of 2026-08).** The comparison matrix below
was never populated — instead of adopting a third-party framework, tango
built a custom `LockedState` (`src/tango/core/locked_state.py`),
enforcing "each state variable updated exactly once per timestep" directly in
the codebase. See `docs/TANGO_vision_and_roadmap/README.md`'s Phase 2 checklist for
current status. Kept here for historical record of the criteria that were
considered, not as an open evaluation.

| Criteria                          | Framework 1 | Framework 2 | Framework 3 | Framework 4 |
|-----------------------------------|-------------|-------------|-------------|-------------|
| **Name**                          |             |             |             |             |
| **Python Support**                |             |             |             |             |
| **JS/TS Support**                 |             |             |             |             |
| **Physics Modeling Adaptability** |             |             |             |             |
| **Hierarchical State**            |             |             |             |             |
| **Validation/Constraints**        |             |             |             |             |
| **Time-Stepping Support**         |             |             |             |             |
| **Visualization/Debugging**       |             |             |             |             |
| **Performance Overhead**          |             |             |             |             |
| **License**                       |             |             |             |             |
| **Active Maintenance**            |             |             |             |             |
| **Notes**                         |             |             |             |             |


## Evaluation Criteria

**Python Support:** Good/Fair/Poor, specific version requirements, ecosystem maturity

**JS/TS Support:** Good/Fair/Poor, specific version requirements, framework compatibility (React/Vue/etc)

**Physics Modeling Adaptability:** Can it handle domain-specific constraints, physical units, conservation laws, numerical stability requirements?

**Hierarchical State:** Support for parent-child component relationships, tree traversal, cascade operations

**Validation/Constraints:** Built-in validation, type checking, invariant enforcement, custom validators

**Time-Stepping Support:** Handles iterative/temporal state evolution, lockable state variables, history management

**Visualization/Debugging:** Tools to inspect state, trace changes, visualize state connections/dependencies

**Performance Overhead:** Negligible/Low/Medium/High for tight simulation loops, memory footprint

**License:** MIT/Apache/BSD/GPL/proprietary - compatibility with TANGO

**Active Maintenance:** Last release date, community activity, issue response time, roadmap
