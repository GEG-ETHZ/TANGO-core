# TANGO Serialization Interface Ideas - Discussion Notes

**Date:** Today's conversation  
**Topic:** Comparing fastsim's serialization/temporal data storage approach with TANGO's current implementation

---

## Main Discussion: fastsim vs TANGO Temporal Data Storage

### User Question 6
```
Can you access `../../../../code/fastsim/`? Please confirm this, and if yes, I'll then give you further instruction.
```

### Response 6
**Confirmed:** Successfully accessed `/Users/cb/code/fastsim/` directory.

### User Question 7
```
Relative to that folder, here are things to look at:
- `python/fastsim/__init__.py` 
    - `to_pydict`
    - `from_pydict`
- `fastsim-core/src/traits/serde_api.rs`
    - `SerdeAPI`

These methods provide an interface for serialization/deserialization that is used in nearly all structs. Also, any struct that will store temporal data has a `state` and `history` field (or attribute in Pythonic nomenclature). This way, vehicle simulations store temporal data in a hierarchical manner that maps to vehicle components. You can see examples of how this works in actual functional usage in `python/fastsim/demos/demo_hev.py`.

Is there any equivalent to this approach in TANGO? I would like an explanation of how temporal data is stored in TANGO.
- Is the data stored hierarchically?
- Is the storage of temporal data consistent at the system level and unit (after >15 years in mult-physics systems modeling, I would use the word "component" were TANGO uses "unit")?
- If I were to make a demo script similar to fastsim's `demo_hev.py` in TANGO, would the data be accessible in an interactive session from a live TANGO object after a similation is finished?
```

### Response 7: Initial Analysis

**fastsim Approach:**
- Hierarchical storage with `state` (current) and `history` (time series) fields
- Consistent `SerdeAPI` trait with `to_pydict()`/`from_pydict()` methods
- Data accessible after simulation via `to_dataframe()` method
- Example: `df["veh.pt_type.HEV.fc.history.pwr_prop_watts"]`

**TANGO Approach - Initial Findings:**

1. **Is data stored hierarchically?**
   - **No.** Temporal data stored in flat dictionary `workflow._results` with keys like `"unit_name_attribute"`
   - Each key maps to a list of values (one per timestep)
   - Units do not have standardized `state`/`history` fields

2. **Is storage consistent at system/unit level?**
   - **No.** Units store internal arrays (e.g., `WellUnitNative` has `_P`, `_T_f`, `_h`, etc.)
   - No standardized interface for temporal data
   - Data extraction uses `parse_results()` which inspects unit attributes via `REPORT_SETTINGS`
   - Different unit types expose different attributes

3. **Would data be accessible after simulation?**
   - **Partially.** The `workflow._results` dictionary persists after `tango.execute()`
   - However:
     - Data is flattened (not hierarchical)
     - No equivalent to `to_dataframe()`
     - No standardized way to access component-level history
     - Data also written to CSV files (`.smry.csv`, `.econ.csv`)

**Key Differences Summary:**
- fastsim: Hierarchical, standardized, accessible
- TANGO: Flat dictionary, unit-specific, CSV-focused

### User Question 8
```
Would you agree that fastsim's approach is better?
```

### Response 8: Assessment

**Yes, fastsim's approach is better for most use cases.**

**Advantages of fastsim:**
1. Hierarchical structure matches physical system
2. Consistent interface across components
3. Interactive exploration without CSV parsing
4. Built-in serialization/deserialization
5. Type safety and clear structure

**Where TANGO's approach might be acceptable:**
- Very large datasets (CSV more memory-efficient)
- Legacy/external tooling dependencies
- Simplicity for basic use cases

**Recommendation:** TANGO would benefit from adopting fastsim's pattern for better developer experience, post-processing, and maintainability.

### User Question 9: Important Clarification
```
I should add that in fastsim, `state` refers to a collection of current state variables (e.g. component temperature, vehicle speed) being simulated, and `history` collects values of state variables through time. `state` and `history` are simulation results. Also note that in fastsim, the `to_file` and `from_file` absolutely can write/read to file. With this reframing in mind, could you recreate the above analysis you did with the specific interest in how TANGO exposes results?

I think what you wrote before was pretty close to what I wanted, but I want to make sure you were correctly thinking about this nuance.
```

### Response 9: Reframed Analysis

**fastsim's Approach (Clarified):**
- `state`: Current values of state variables (simulation results at current timestep)
  - Example: `veh.pt_type.HEV.fc.state.pwr_prop_watts` = current power
- `history`: Time series of state variables (simulation results across all timesteps)
  - Example: `veh.pt_type.HEV.fc.history.pwr_prop_watts` = array of power over time
- Both are part of object structure and are simulation results
- `to_file()`/`from_file()` can serialize entire object (state + history)

**TANGO's Approach to Exposing Results:**

1. **Current State (equivalent to fastsim's `state`):**
   - Units store current state in attributes like:
     - `inlet_fluid`, `outlet_fluid` (FluidState objects)
     - `mass_rate` (current flow rate)
     - `_P[0]`, `_T_f[0]` (current pressure, temperature at specific locations)
     - `thermal_power` (current power output)
   - These are current simulation results, but not organized under a `state` attribute
   - Access: `tango.workflow.orchestrator.unit.reservoir.outlet_fluid.P` (current value)

2. **Historical Data (equivalent to fastsim's `history`):**
   - Stored in `workflow._results` dictionary
   - Each timestep, `parse_results()` extracts current state values and appends them to lists
   - Keys like `"reservoir_pressure"`, `"well_temperature"` map to lists of values over time
   - This is the time series, but it's separate from the units themselves
   - Access: `tango.workflow._results["reservoir_pressure"]` (list of values)

3. **Key Differences from fastsim:**
   - No standardized `state`/`history` structure on units
   - Current state scattered across unit attributes
   - History collected externally in `_results`, not stored on units
   - No `to_file()`/`from_file()` for units (only CSV output at workflow level)
   - No hierarchical access (e.g., `reservoir.well.history.pressure`)

**Comparison Table:**

| Aspect | fastsim | TANGO |
|--------|---------|-------|
| **Current state** | `unit.state.attribute` (standardized) | `unit.attribute` (scattered, unit-specific) |
| **History** | `unit.history.attribute` (on unit) | `workflow._results["unit_attribute"]` (external) |
| **Structure** | Hierarchical, consistent | Flat dictionary, inconsistent |
| **Serialization** | `to_file()`/`from_file()` on any unit | CSV export only at workflow level |
| **Post-simulation access** | `unit.history.*` directly accessible | `workflow._results` dict accessible |
| **Component hierarchy** | `veh.pt_type.HEV.fc.history.*` | Flattened keys like `"surface_power"` |

**Assessment:**
fastsim's approach is better because:
1. Clear separation: `state` (current) vs `history` (time series) is explicit
2. Results stay with units: History lives on component, not separate dictionary
3. Consistent interface: All components expose results the same way
4. Better organization: Hierarchical structure matches physical system
5. Serialization: Can save/load complete simulation states

**TANGO's Limitations:**
1. Current state not clearly separated from other attributes
2. History externalized: `_results` separate from units, harder to reason about component-level results
3. Inconsistent: Different units expose different attributes, no standard pattern
4. Limited serialization: Only CSV export, no way to save/load complete simulation state
5. Flattened structure: Loses component hierarchy in result keys

**Recommendation:**
TANGO would benefit from adopting fastsim's pattern:
- Add `state` attributes to units for current simulation results
- Add `history` attributes to units for time series
- Implement `to_file()`/`from_file()` for serialization
- Keep hierarchical structure (e.g., `reservoir.well.history.pressure`)

---

## Key Files Referenced

### fastsim Files
- `/Users/cb/code/fastsim/python/fastsim/__init__.py` - `to_pydict`, `from_pydict` methods
- `/Users/cb/code/fastsim/fastsim-core/src/traits/serde_api.rs` - `SerdeAPI` trait
- `/Users/cb/code/fastsim/python/fastsim/demos/demo_hev.py` - Example usage

### TANGO Files Analyzed
- `src/tango/workflows/native_workflow.py` - Workflow execution and result storage
- `src/tango/utils.py` - `parse_results()`, `append_results()`, `write_results()`
- `src/tango/core/abstracts/unit.py` - Base Unit class
- `src/tango/units/native/well/base.py` - Example unit implementation
- `src/tango/units/native/reservoir.py` - Example unit implementation
- `src/tango/runner.py` - Tango class and execution

---

## Implementation Recommendations

### Phase 1: Add State/History Structure to Units
1. Create base `State` and `History` dataclasses/classes
2. Add `state` and `history` attributes to Unit base class
3. Update units to populate these during simulation

### Phase 2: Implement Serialization Interface
1. Add `to_pydict()` and `from_pydict()` methods to Unit base class
2. Implement `to_file()` and `from_file()` methods
3. Support multiple formats (YAML, JSON, msgpack)

### Phase 3: Maintain Backward Compatibility
1. Keep `workflow._results` dictionary for existing code
2. Populate both old and new structures during transition
3. Add deprecation warnings for old access patterns

### Phase 4: Add Convenience Methods
1. Implement `to_dataframe()` method on workflow
2. Add hierarchical access helpers
3. Create visualization utilities

---

## Notes for Future Implementation

- User plans to provision a separate directory and git branch for implementation
- This document should serve as reference for the implementation work
- Key principle: Maintain backward compatibility while adding new capabilities
- Consider TANGO's multi-physics nature when designing hierarchy (reservoir → well → surface → power_plant)

