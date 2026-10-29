# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``Component.snapshot_convergence_state()`` /
``restore_convergence_state()``.

``inlet`` is not a stored ``Component`` field — ``solve(inlet)`` takes it as
a call parameter (see ``FlowComponent.solve()``'s docstring) — and ``outlet``,
while still a stored field, is written from exactly the same values every
concrete ``solve()`` also records into ``state`` (``state.T_outlet``/
``P_outlet``/``mass_rate``, or their production-well equivalents). This
module deliberately reads everything back through ``component.state``
instead of ``component.outlet``, since ``state`` is what
``snapshot_convergence_state()``/``restore_convergence_state()`` actually
scope to (see ``Component.snapshot_convergence_state()``'s docstring) — the
same values, reached the way these two methods themselves reach them.

``history`` is deliberately excluded from the convergence snapshot (``state``
is the ONLY thing ``snapshot_convergence_state()`` deep-copies) because it
must persist across a within-timestep re-solve rather than be rolled back to
whatever it was when the snapshot was taken. This module checks that
``restore_convergence_state()`` is a true no-op with respect to ``history``:
it neither rewinds it nor duplicates entries.

``test_history_restored`` checks this in isolation, against a single
``LumpedReservoir`` built by hand. ``test_history_restored_across_full_workflow``
checks the same invariant end-to-end, for every component wired into a real
circuit (``templates/hydro_sf_electric.yml``, driven through its
actual orchestrator) — the surface/well/reservoir component types differ
enough (a TESPy graph, spatially-discretized numerical wells, a lumped
reservoir) that the isolated check alone doesn't prove the invariant holds
for all of them.

Conversely, ``test_every_convergence_field_restored_for_lumped_reservoir``
checks the other direction for ``LumpedReservoir`` specifically: every field
declared on ``LumpedReservoirState`` (discovered via ``dataclasses.fields()``,
not a hand-maintained list — that IS the entirety of what a snapshot covers,
since ``snapshot_convergence_state()`` just deep-copies ``self.state`` whole)
must actually come back to its snapshotted value — not just the handful
(``T_outlet``/``P_outlet``) exercised incidentally by other tests.

``test_power_output_reproducible_across_convergence_attempts`` checks the
practical consequence of both: ``SystemBCIteration``'s inner convergence
loop (``_converge_injection_enthalpy`` in ``system_bc_iteration.py``) restores the
same snapshot before every re-solve attempt, so feeding the reservoir the
SAME injection-temperature guess on two different inner iterations must
yield the SAME reservoir power output. Before the fix that introduced
tracking ``energy_extracted`` as a proper cumulative ``state`` field, it
didn't — the reservoir's own previous-outlet bookkeeping lived somewhere a
restore never rolled back, so each additional iteration solved from a
silently drifted starting point ("moving goalposts").

``test_surface_power_output_reproducible_across_convergence_attempts``
checks a related but distinct property for ``GraphSurface`` (the
TESPy-backed power plant). ``GraphSurface.state`` carries no cross-timestep
accumulator — every field is recomputed from scratch from ``inlet`` each
``solve()`` call — so restoring ``state`` alone guarantees nothing here; the
one thing that DOES persist across ``solve()`` calls without being part of
``state`` is ``injection_pressure`` (a plain ``Component`` field, driven
directly by ``SystemBCIteration``'s outer BC loop — see
``SurfaceComponent.injection_pressure``'s docstring), plus the TESPy
network's own private, non-Pydantic, warm-started connection state
(``self._network``/``self._conns``), which ``snapshot_convergence_state()``
never touches at all. This checks that resetting ``injection_pressure``
explicitly (the same value ``SystemBCIteration`` would have converged to)
and re-solving the SAME inlet reproduces the SAME net power output, even
after an intervening solve with a DIFFERENT ``injection_pressure`` and a
DIFFERENT inlet guess perturbed both.
"""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml

from tango_core.components.reservoir.lumped import LumpedReservoir
from tango_core.core.fluid_state import COOLPROP_BACKEND, FluidState
from tango_core.core.locked_state import LockedState
from tango_core.core.stream import Stream
from tango_core.workflows.workflow import Workflow

TEMPLATES_DIR = Path(__file__).parents[2] / "templates"
HYDRO_SF_ELECTRIC = TEMPLATES_DIR / "hydro_sf_electric.yml"

_COMMON_FIELDS: dict[str, float | str] = {
    "fluid_name": "water",
    "rock_density": 2700.0,
    "rock_cp": 1000.0,
    "rock_k": 3.0,
    "thermal_gradient": 0.035,
    "surface_temperature": 288.0,
    "surface_pressure": 101325.0,
}


def _inlet_at(T: float, P: float, mass_rate: float) -> Stream:
    """An inlet ``Stream`` at a readable (T, P), converted to the stream's enthalpy with this file's fluid."""
    h = FluidState.with_PT(
        str(_COMMON_FIELDS["fluid_name"]),
        P,
        T,
        str(_COMMON_FIELDS.get("coolprop_backend", COOLPROP_BACKEND)),
    ).H
    return Stream.fresh(h=h, P=P, mass_rate=mass_rate)


_RESERVOIR_FIELDS: dict[str, float] = {
    "dt_years": 1.0,
    "reservoir_depth": 5000.0,
    "thickness": 300.0,
    "porosity": 0.1,
    "permeability": 1e-14,
    "hydro_static_pressure": 50e6,
    "over_pressure_percentage": 10.0,
    "well_pattern": "DOUBLET",
}


def _reservoir_cfg(idx: int) -> dict:
    return dict(
        component_idx=idx,
        prev=idx - 1,
        next=idx + 1,
        common=dict(_COMMON_FIELDS),
        **_RESERVOIR_FIELDS,
    )


def _run_workflow(res: LumpedReservoir, timestep: int) -> None:
    """Run one "timestep" of the workflow: solve and record history."""
    inlet = _inlet_at(350.0, 5.1e7, 50.0)
    if timestep > 0:
        res.mark_all_stale()
    res.solve(inlet)
    res.record(timestep)


def test_history_restored() -> None:
    """Restoring a convergence snapshot must not roll back or duplicate history."""
    res = LumpedReservoir.from_dict(_reservoir_cfg(2))

    # Run the workflow once and take a snapshot + a copy of history at that point.
    _run_workflow(res, 2)
    snapshot = res.snapshot_convergence_state()
    history_at_snapshot = copy.deepcopy(res.history)

    # Run the workflow again, growing history further.
    _run_workflow(res, 1)
    history_before_restore = copy.deepcopy(res.history)

    # Sanity check: history actually grew, so the parity check below is meaningful.
    assert history_before_restore != history_at_snapshot

    # Restore the earlier snapshot (rolls back state) and check that history
    # is untouched by the restore.
    res.restore_convergence_state(snapshot)
    new_history = copy.deepcopy(res.history)

    assert new_history == history_before_restore


def _raw_value(value: Any) -> Any:
    """Read a ``state`` field's underlying value for equality comparison.

    Every ``LumpedReservoirState``/``GraphSurfaceState`` field is a
    ``LockedState``, which deliberately defines no ``__eq__`` — it compares
    by identity only (see its module docstring's bypass-prevention design),
    so two independently deep-copied instances holding the identical value
    would otherwise never compare equal. Reach through the same
    mangled-name access ``LockedState.__get_pydantic_core_schema__`` itself
    uses for serialization, rather than ``get_fresh()``/``get_stale()``,
    since a field's status (fresh vs stale) isn't what this test cares
    about — only whether the restored value matches the snapshotted one.
    """
    if isinstance(value, LockedState):
        return value._LockedState__value  # noqa: SLF001
    return value


def test_every_convergence_field_restored_for_lumped_reservoir() -> None:
    """Every field on ``LumpedReservoirState`` must come back unchanged after a restore.

    ``snapshot_convergence_state()`` deep-copies ``self.state`` whole, so
    this test doesn't hand-pick fields either — it discovers the exact same
    set from ``dataclasses.fields(LumpedReservoirState)`` and checks every
    one of them, individually, actually rolls back to its snapshotted
    value: the derived depletion coefficients (``p1``/``p2``/``p3``), the
    outlet fields (``T_outlet``/``P_outlet``), the cumulative
    ``energy_extracted`` accumulator, and ``ever_solved``.
    """
    res = LumpedReservoir.from_dict(_reservoir_cfg(2))

    _run_workflow(res, 0)
    snapshot = res.snapshot_convergence_state()

    field_names = [f.name for f in dataclasses.fields(type(res.state))]
    values_at_snapshot = {name: _raw_value(getattr(snapshot, name)) for name in field_names}

    # Solve a second time so every one of those fields has something to roll
    # back from: T_outlet/P_outlet advance, p1/p2/p3 are recomputed from
    # updated fluid properties, and energy_extracted accumulates further.
    _run_workflow(res, 1)
    values_before_restore = {name: _raw_value(getattr(res.state, name)) for name in field_names}

    changed = {name for name in field_names if values_before_restore[name] != values_at_snapshot[name]}
    assert changed, (
        "solving a second time changed none of the convergence fields — "
        "the restore check below would be meaningless"
    )

    res.restore_convergence_state(snapshot)

    for name in sorted(field_names):
        restored = _raw_value(getattr(res.state, name))
        assert restored == values_at_snapshot[name], (
            f"{name!r} was not restored to its snapshotted value "
            f"(snapshot={values_at_snapshot[name]!r}, after restore={restored!r})"
        )


def _reservoir_power_watts(res: LumpedReservoir) -> float:
    """Thermal power extracted by the reservoir this solve (W): mdot·(h_out − h_in)."""
    s = res.state
    return s.mass_rate.get_fresh() * (s.h_outlet.get_fresh() - s.h_inlet.get_fresh())


def _reservoir_outlet_state(res: LumpedReservoir) -> tuple[float, float, float]:
    """(T_outlet, P_outlet, mass_rate) as this solve committed them to ``state``."""
    s = res.state
    return s.T_outlet.get_fresh(), s.P_outlet.get_fresh(), s.mass_rate.get_fresh()


def _resolve_from_snapshot(res: LumpedReservoir, snapshot: Any, inlet: Stream) -> float:
    """Restore ``snapshot``, solve with ``inlet``, and return the resulting power (W).

    Mirrors the exact per-component order ``SystemBCIteration``'s inner
    convergence loop uses before every re-solve attempt (see
    ``_converge_injection_enthalpy`` in ``system_bc_iteration.py``):
    ``restore_convergence_state()`` -> ``mark_all_stale()`` -> ``solve(inlet)``.
    """
    res.restore_convergence_state(snapshot)
    res.mark_all_stale()
    res.solve(inlet)
    return _reservoir_power_watts(res)


def test_power_output_reproducible_across_convergence_attempts() -> None:
    """Two convergence-loop attempts with the same restored snapshot and the
    same injection-temperature guess must produce the identical reservoir
    power output.

    Regression test for the "moving goalposts" fixed-point iteration this
    module's docstring describes: re-solving the SAME guess on a later
    inner iteration must reproduce the FIRST iteration's answer exactly,
    not drift toward something new each time.
    """
    res = LumpedReservoir.from_dict(_reservoir_cfg(2))

    # Commit a real, non-trivial previous timestep first, so there is
    # meaningful prior-outlet state (T_outlet/P_outlet, energy_extracted,
    # ...) to snapshot and restore from — matching how SystemBCIteration
    # only ever restores a snapshot taken at the END of a real, solved
    # timestep.
    _run_workflow(res, 0)
    snapshot = res.snapshot_convergence_state()

    same_guess = _inlet_at(340.0, 5.05e7, 48.0)

    # Convergence-loop attempt #1.
    power_1 = _resolve_from_snapshot(res, snapshot, same_guess)
    state_1 = _reservoir_outlet_state(res)

    # Sanity check: solving the SAME guess again but WITHOUT restoring first
    # (i.e. starting from wherever attempt #1 left T_outlet/P_outlet/
    # energy_extracted) gives a DIFFERENT answer — the exact "moving
    # goalposts" failure mode this test guards against, and proof the
    # equality check below isn't trivially true regardless of restoring.
    res.mark_all_stale()
    res.solve(same_guess)
    power_without_restore = _reservoir_power_watts(res)
    assert power_without_restore != power_1, (
        "solving the same guess twice in a row without restoring first "
        "produced the same power output both times — this test's premise "
        "no longer holds, so the restore check below would be meaningless"
    )

    # Convergence-loop attempt #2: restore the SAME snapshot, SAME guess.
    power_2 = _resolve_from_snapshot(res, snapshot, same_guess)
    state_2 = _reservoir_outlet_state(res)

    assert power_2 == power_1, (
        f"reservoir power output was not reproducible across two "
        f"convergence-loop attempts from the same snapshot + inlet: "
        f"{power_1!r} -> {power_2!r}"
    )

    # Also assert the (T_outlet, P_outlet, mass_rate) triple committed to
    # `state` is the same after restoration.
    assert state_2 == state_1


def _load_hydro_sf_electric_workflow(num_tsteps: int) -> Workflow:
    """Build the hydro_sf_electric example with a reduced timestep count.

    Loads the YAML once and overrides ``sim_config.num_tsteps`` in memory
    (never touching the file on disk — same pattern ``test_lcoe_regression.py``
    uses for its ``_run_tango`` helper) so this test stays cheap
    regardless of the example's own configured ``num_tsteps``.
    """
    config: dict[str, Any] = yaml.safe_load(HYDRO_SF_ELECTRIC.read_text(encoding="utf-8"))
    config["sim_config"]["num_tsteps"] = num_tsteps
    return Workflow(config)


def test_surface_power_output_reproducible_across_convergence_attempts() -> None:
    """Two convergence-loop attempts with the same restored snapshot, the
    same reset ``injection_pressure``, and the same inlet must produce the
    same surface/power-plant net power output, even with a different
    ``injection_pressure`` + inlet solve in between.

    ``injection_pressure`` lives outside ``state`` (see
    ``SurfaceComponent.injection_pressure``'s docstring), so
    ``restore_convergence_state()`` never rolls it back — this test resets
    it explicitly rather than relying on the snapshot mechanism for it.
    """
    wf = _load_hydro_sf_electric_workflow(num_tsteps=1)
    wf.run()

    surface = wf._orchestrator.components["surface"]
    snapshot = surface.snapshot_convergence_state()
    original_injection_pressure = surface.injection_pressure

    s = surface.state
    guess = Stream.fresh(h=s.h_inlet.get_fresh(), P=s.P_inlet.get_fresh(), mass_rate=s.mass_rate.get_fresh())

    def _resolve(inlet: Stream) -> float:
        surface.restore_convergence_state(snapshot)
        surface.mark_all_stale()
        surface.solve(inlet)
        return surface.state.net_power_W.get_fresh()

    # Convergence-loop attempt #1, at the original (converged) injection_pressure.
    surface.set_injection_pressure(original_injection_pressure)
    power_1 = _resolve(guess)
    state_1 = (surface.state.T_outlet.get_fresh(), surface.state.P_outlet.get_fresh())

    # An intervening inner-loop attempt with a DIFFERENT injection_pressure
    # AND a different inlet — perturbs both the one persistent field outside
    # `state` and the TESPy network's invisible warm-start connection state.
    surface.set_injection_pressure(original_injection_pressure + 5e5)
    different_guess = Stream.fresh(
        h=guess.h.get_fresh() - 20_000.0,  # ~5 K colder for water
        P=guess.P.get_fresh(),
        mass_rate=guess.mass_rate.get_fresh(),
    )
    _resolve(different_guess)

    # Sanity check: solving the SAME guess again WITHOUT resetting
    # injection_pressure first (i.e. keeping the perturbed value from the
    # detour above) gives a DIFFERENT answer — proof the equality check
    # below isn't trivially true regardless of resetting it.
    power_without_reset = _resolve(guess)
    assert power_without_reset != pytest.approx(power_1, rel=1e-6), (
        "solving the same inlet again without resetting injection_pressure "
        "first reproduced attempt #1's power output anyway — this test's "
        "premise no longer holds, so the restore check below would be "
        "meaningless"
    )

    # Convergence-loop attempt #2: reset injection_pressure back to attempt
    # #1's value, SAME guess as attempt #1 — must reproduce the SAME answer
    # despite the detour above.
    surface.set_injection_pressure(original_injection_pressure)
    power_2 = _resolve(guess)
    state_2 = (surface.state.T_outlet.get_fresh(), surface.state.P_outlet.get_fresh())

    assert power_2 == pytest.approx(power_1, rel=1e-6), (
        f"surface net power output was not reproducible across two "
        f"convergence-loop attempts from the same snapshot + injection_pressure + inlet: "
        f"{power_1!r} -> {power_2!r}"
    )
    assert pytest.approx(state_1[0], rel=1e-6) == state_2[0]
    assert pytest.approx(state_1[1], rel=1e-6) == state_2[1]


def test_history_restored_across_full_workflow() -> None:
    """Restoring a convergence snapshot must not roll back or duplicate
    history, for every component wired into a real circuit.

    Runs the workflow's one configured timestep, snapshots every component,
    then drives one further timestep "by hand" — bypassing ``Workflow.run()``
    (which already consumed ``sim_config.num_tsteps``) by calling the
    orchestrator's own ``run_timestep()``/``record()`` directly, the same way
    ``SystemDirect.run()`` would for a real extra timestep. That grows every
    component's history AND mutates its ``state``, so restoring the earlier
    snapshot afterward has something real to roll back.
    """
    wf = _load_hydro_sf_electric_workflow(num_tsteps=1)
    wf.run()

    orchestrator = wf._orchestrator
    components = orchestrator.components
    assert components, "workflow produced no components to check"

    snapshot = {name: c.snapshot_convergence_state() for name, c in components.items()}
    history_at_snapshot = {name: copy.deepcopy(c.history) for name, c in components.items()}

    # One more real timestep, growing history and mutating `state` for every
    # component in the circuit.
    extra_t = orchestrator.n_tsteps
    orchestrator.run_timestep(extra_t)
    orchestrator.record(extra_t)

    history_before_restore = {name: copy.deepcopy(c.history) for name, c in components.items()}

    # Sanity check: history actually grew for every component, so the parity
    # check below is meaningful.
    for name in components:
        assert history_before_restore[name] != history_at_snapshot[name], (
            f"{name!r}: history did not grow after the extra timestep — "
            "the restore check below would be meaningless"
        )

    for name, component in components.items():
        component.restore_convergence_state(snapshot[name])

    for name, component in components.items():
        assert component.history == history_before_restore[name], (
            f"{name!r}: restore_convergence_state() rolled back or duplicated history"
        )
