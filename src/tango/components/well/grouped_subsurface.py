"""An AGS subsurface grouped into one component: injection well -> horizontal well -> production well.

An advanced geothermal system (AGS) circulates its working fluid through a
sealed loop: down a vertical injection well, along a horizontal well at
depth, and back up a vertical production well, exchanging heat with the
rock by conduction only. ``GroupedSubsurfaceComponent`` groups those three
wells into one circuit component, so the whole subsurface can be simulated
by different models behind the same config shape:

- ``NumericalGroupedSubsurface`` (variant ``numerical``): the three wells are
  ``NumericalWell`` segments marched in sequence, exactly as when they are
  configured as three separate components.
- ``RaftGroupedSubsurface`` (variant ``raft``): RAFT simulates the wells and
  the surrounding rock (see ``tango.external.raft_wrapper``). Its segment
  blocks give only geometry (``well_length``, ``diameter``,
  ``pipe_roughness``), and a ``raft:`` block names RAFT's config template.

The loop's geometry is given as three segment blocks, each a well config::

    grouped_subsurface:
      type: grouped_subsurface
      variant: numerical
      component_idx: 0
      prev: 1
      next: 1
      injection_well: {well_length: 8000.0, diameter: 0.311, pipe_roughness: 5.5e-5}
      horizontal_well: {well_length: 3000.0, diameter: 0.311, pipe_roughness: 5.5e-5}
      production_well: {diameter: 0.311, pipe_roughness: 5.5e-5}

The production well's length and the horizontal well's ``wellhead_depth``
both equal the injection well's length, and ``layout.well_spacing`` equals
the horizontal well's length; these are derived (see
``tango.workflows.linked_quantities``). The loop sets each segment's
``common``, ``dt_years``, circuit indices, ``save_interval`` and
``angle_from_vert_deg`` itself, so a segment block may not give them.

Mass flow rate is assumed constant around the loop: the outlet carries the
inlet's mass rate.

Boundary conditions
-------------------
The loop is solved with its mass flow and temperature fixed at the inlet
(injection wellhead) and its pressure fixed at the outlet (production
wellhead), and it solves for the injection pressure that delivers that:

- **Inlet, set by tango:** the mass rate (``sim_config.mass_rate``) and the
  injection enthalpy (the surface plant's outlet, converged by
  ``SystemBCIteration``).
- **Outlet, set by tango:** the production wellhead pressure,
  ``target_extraction_pressure`` (from ``sim_config``, the same value the
  surface plant gets as the minimum pressure it needs at its inlet).
- **Solved by the subsurface model:** the injection wellhead pressure
  (``state.P_inlet``), the production temperature and enthalpy, and, for
  RAFT, the production mass flow.

``SystemBCIteration`` hands the solved injection pressure to the surface
plant in the same pass (``SurfaceComponent.set_injection_pressure``), so the
plant's circulation pump or valve delivers exactly the pressure the loop
needs. The surface plant's configured ``injection_pressure`` is then only
the first timestep's starting guess.

Why this way round: an external simulator (RAFT) may later lose fluid to
storage or leak-off. With the injected mass rate set at the inlet, a loss
shows up as a lower production flow, where a makeup tank can replace it
(GitHub #63); with the pressure set at the inlet instead, a loss would
change the injected rate, which tango controls. RAFT's own template is set
up this way too. Both variants use these boundary conditions, so they stay
directly comparable.

The numerical variant marches its wells from the inlet, so it finds the
injection pressure by shooting (``NumericalGroupedSubsurface``'s
``solve_for_outlet_pressure``): it marches from a trial injection pressure
and corrects the trial until the production pressure matches the target.
Given the injection pressure the old inlet-pressure-driven march used, it
reproduces that march's results (tested to 1e-6 relative in
``tests/unit/test_grouped_subsurface.py``).
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from tango.components.well.base import HORIZONTAL_ANGLE_DEG, WellRole, WellSection
from tango.components.well.numerical import NumericalInjectionWell, NumericalProductionWell, NumericalWell
from tango.core.component import FlowComponent
from tango.core.constants import YEAR_TO_SECOND
from tango.core.errors import ConfigError, ConvergenceError
from tango.core.locked_state import LockedState
from tango.core.specs import Common
from tango.core.state_methods import StateMethods
from tango.core.stream import Stream
from tango.external.raft_wrapper import LoopGeometry, RaftWrapper

SEGMENT_NAMES: tuple[str, str, str] = ("injection_well", "horizontal_well", "production_well")
"""The loop's segment blocks, in flow order."""

_SEGMENT_ANGLE_FROM_VERT_DEG: dict[str, float] = {
    "injection_well": 0.0,
    "horizontal_well": HORIZONTAL_ANGLE_DEG,
    "production_well": 180.0,
}

LOOP_SET_SEGMENT_KEYS: tuple[str, ...] = (
    "common",
    "dt_years",
    "component_idx",
    "prev",
    "next",
    "save_interval",
    "angle_from_vert_deg",
)
"""Segment fields the loop sets from its own fields; a segment block may not give them."""

_SHOOTING_REL_TOL: float = 1e-9
"""Relative tolerance on the production wellhead pressure for the numerical variant's shooting
solve (about 0.007 Pa at 7 MPa): tight enough that the solve reproduces an inlet-pressure-driven
march to far better than 1e-6."""

_SHOOTING_MAX_ITER: int = 20
"""Maximum marches the numerical variant's shooting solve tries before raising ``ConvergenceError``.
For liquid water the production pressure moves almost one-for-one with the injection pressure, so
it usually converges in 2-4."""


def _ls_nan() -> LockedState[float]:
    ls: LockedState[float] = LockedState(float("nan"))
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class GroupedSubsurfaceState(StateMethods):
    """Loop inlet (injection wellhead) and outlet (production wellhead) state for one solve."""

    h_inlet: LockedState[float] = field(default_factory=_ls_nan)
    """Specific enthalpy (J/kg) entering the injection well."""
    T_inlet: LockedState[float] = field(default_factory=_ls_nan)
    """Temperature (K) entering the injection well."""
    P_inlet: LockedState[float] = field(default_factory=_ls_nan)
    """Pressure (Pa) at the injection wellhead, solved by the subsurface model so the production wellhead
    reaches ``target_extraction_pressure``; ``SystemBCIteration`` makes it the surface plant's injection
    pressure."""
    mass_rate: LockedState[float] = field(default_factory=_ls_nan)
    """Mass flow rate (kg/s) around the loop."""
    h_outlet: LockedState[float] = field(default_factory=_ls_nan)
    """Specific enthalpy (J/kg) leaving the production well."""
    T_outlet: LockedState[float] = field(default_factory=_ls_nan)
    """Temperature (K) at the production wellhead."""
    P_outlet: LockedState[float] = field(default_factory=_ls_nan)
    """Pressure (Pa) at the production wellhead: ``target_extraction_pressure``, which tango sets (to
    within the numerical variant's shooting tolerance)."""
    heat_extracted_watts: LockedState[float] = field(default_factory=_ls_nan)
    """Rate of energy the fluid gains around the loop (W): ``mass_rate * (h_outlet - h_inlet)``."""


@dataclass
class GroupedSubsurfaceHistory:
    """Per-timestep history of ``GroupedSubsurfaceState``, one list per field."""

    h_inlet: list[float] = field(default_factory=list)
    T_inlet: list[float] = field(default_factory=list)
    P_inlet: list[float] = field(default_factory=list)
    mass_rate: list[float] = field(default_factory=list)
    h_outlet: list[float] = field(default_factory=list)
    T_outlet: list[float] = field(default_factory=list)
    P_outlet: list[float] = field(default_factory=list)
    heat_extracted_watts: list[float] = field(default_factory=list)

    def record(self, state: GroupedSubsurfaceState) -> None:
        """Append ``state`` as one timestep entry."""
        self.h_inlet.append(state.h_inlet.get_fresh())
        self.T_inlet.append(state.T_inlet.get_fresh())
        self.P_inlet.append(state.P_inlet.get_fresh())
        self.mass_rate.append(state.mass_rate.get_fresh())
        self.h_outlet.append(state.h_outlet.get_fresh())
        self.T_outlet.append(state.T_outlet.get_fresh())
        self.P_outlet.append(state.P_outlet.get_fresh())
        self.heat_extracted_watts.append(state.heat_extracted_watts.get_fresh())


class GroupedSubsurfaceComponent(FlowComponent, ABC):
    """Abstract base for a component covering a whole closed (AGS) loop. See the module docstring."""

    prev: int = Field(frozen=True)
    """Circuit index of the upstream component (the surface)."""
    next: int = Field(frozen=True)
    """Circuit index of the downstream component (the surface)."""
    common: Common = Field(frozen=True)
    """Shared fluid/rock parameters: the same ``Common`` instance every other
    component in the Workflow holds."""
    dt_years: float = Field(frozen=True)
    """Timestep duration (years)."""
    target_extraction_pressure: PositiveFloat = Field(frozen=True)
    """Production wellhead pressure (Pa) the loop delivers: its outlet boundary condition (see the
    module docstring). From ``sim_config.target_extraction_pressure``, the same value the surface plant
    gets as the minimum pressure it needs at its inlet."""

    state: GroupedSubsurfaceState = Field(default_factory=GroupedSubsurfaceState)
    history: GroupedSubsurfaceHistory = Field(default_factory=GroupedSubsurfaceHistory)

    @abstractmethod
    def well_sections(self) -> list[WellSection]:
        """Return the loop's drilled sections, in flow order, for the economic model."""

    @abstractmethod
    def solve_for_outlet_pressure(self, inlet: Stream, P_outlet: float) -> Stream:
        """Solve the loop for its injection pressure, given the inlet's mass rate and enthalpy and the production pressure.

        ``inlet.P`` is only a starting guess for the injection pressure; the
        solved value is ``state.P_inlet``. See the module docstring.

        Args:
            inlet: The stream entering the injection well.
            P_outlet: The production wellhead pressure (Pa) to deliver.

        Returns:
            The stream leaving the production well, at ``P_outlet``.
        """

    def solve(self, inlet: Stream) -> Stream:
        """Solve the loop with its production wellhead at ``target_extraction_pressure`` (see the module docstring)."""
        return self.solve_for_outlet_pressure(inlet, self.target_extraction_pressure)

    def required_injection_pressure(self) -> float:
        """Return the injection wellhead pressure (Pa) the last solve found, for ``SystemBCIteration``."""
        return self.state.P_inlet.get_fresh()

    def _record_loop_state(
        self,
        inlet: Stream,
        P_inlet: float,
        h_outlet: float,
        P_outlet: float,
        T_inlet: float,
        T_outlet: float,
    ) -> Stream:
        """Write ``state`` and ``outlet`` from the loop's inlet and outlet conditions, and return ``outlet``.

        ``P_inlet`` is the solved injection pressure, not ``inlet.P`` (a
        starting guess). The outlet's mass rate is the inlet's (constant mass
        flow around the loop).
        """
        s = self.state
        h_inlet = inlet.h.get_fresh()
        mass_rate = inlet.mass_rate.get_fresh()
        s.h_inlet.update(h_inlet)
        s.T_inlet.update(T_inlet)
        s.P_inlet.update(P_inlet)
        s.mass_rate.update(mass_rate)
        s.h_outlet.update(h_outlet)
        s.T_outlet.update(T_outlet)
        s.P_outlet.update(P_outlet)
        s.heat_extracted_watts.update(mass_rate * (h_outlet - h_inlet))
        self.outlet.h.update(h_outlet)
        self.outlet.P.update(P_outlet)
        self.outlet.mass_rate.update(mass_rate)
        return self.outlet


class NumericalGroupedSubsurface(GroupedSubsurfaceComponent):
    """Closed loop simulated by three ``NumericalWell`` segments marched in sequence.

    Gives the same result as configuring the three wells as separate
    circuit components; see the module docstring for the config shape.
    """

    injection_well: NumericalInjectionWell
    """The injection segment: a numerical injection well's config block."""
    horizontal_well: NumericalWell
    """The horizontal segment: a numerical horizontal well's config block."""
    production_well: NumericalProductionWell
    """The production segment: a numerical production well's config block."""

    @model_validator(mode="before")
    @classmethod
    def _configure_segments(cls, data: Any) -> Any:
        """Give each segment block the fields the loop sets for it (see ``LOOP_SET_SEGMENT_KEYS``).

        Raises:
            ConfigError: A segment block gives one of those fields itself.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for name in SEGMENT_NAMES:
            segment = data.get(name)
            if not isinstance(segment, dict):
                continue
            given = sorted(set(LOOP_SET_SEGMENT_KEYS) & segment.keys())
            if given:
                raise ConfigError(
                    f"grouped_subsurface.{name} gives {given!r}, which the loop sets for each segment itself; "
                    "leave them out of the segment block.",
                )
            data[name] = {
                **segment,
                "common": data.get("common"),
                "dt_years": data.get("dt_years"),
                "component_idx": data.get("component_idx"),
                "prev": data.get("component_idx"),
                "next": data.get("component_idx"),
                "save_interval": data.get("save_interval", 1),
                "angle_from_vert_deg": _SEGMENT_ANGLE_FROM_VERT_DEG[name],
            }
        return data

    @model_serializer(mode="wrap")
    def _omit_loop_set_segment_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Leave the loop-set fields out of each serialized segment block, so the dump loads back."""
        data: dict[str, Any] = handler(self)
        for name in SEGMENT_NAMES:
            segment = data.get(name)
            if isinstance(segment, dict):
                for key in LOOP_SET_SEGMENT_KEYS:
                    segment.pop(key, None)
        return data

    def segments(self) -> tuple[NumericalWell, NumericalWell, NumericalWell]:
        """Return the three segments in flow order."""
        return self.injection_well, self.horizontal_well, self.production_well

    def init(self) -> None:
        """Compute each segment's derived quantities."""
        for segment in self.segments():
            segment.init()

    def _march(self, inlet: Stream, P_inlet: float) -> Stream:
        """March the injection, horizontal and production wells in sequence from injection pressure ``P_inlet``."""
        stream = Stream.fresh(h=inlet.h.get_fresh(), P=P_inlet, mass_rate=inlet.mass_rate.get_fresh())
        for segment in self.segments():
            stream = segment.solve(stream)
        return stream

    def solve_for_outlet_pressure(self, inlet: Stream, P_outlet: float) -> Stream:
        """Find the injection pressure whose march delivers ``P_outlet`` at the production wellhead (shooting).

        Each trial restores the segments to the state they had when this
        solve started and marches all three wells from a trial injection
        pressure, so a trial never builds on another. The first trial starts
        from ``inlet.P``. The second assumes the production pressure moves
        one-for-one with the injection pressure (nearly true for liquid
        water); later trials use the secant through the last two. A trial
        whose production pressure is within ``_SHOOTING_REL_TOL`` of
        ``P_outlet`` is kept, its segments' state included, so the result is
        exactly an ordinary march from the found injection pressure.

        Raises:
            ConvergenceError: No trial reaches ``P_outlet`` within
                ``_SHOOTING_MAX_ITER`` marches.
        """
        start = {
            name: segment.snapshot_convergence_state()
            for name, segment in zip(SEGMENT_NAMES, self.segments(), strict=True)
        }
        P_in = inlet.P.get_fresh()
        previous: tuple[float, float] | None = None  # (injection pressure, residual) of the last trial
        for _ in range(_SHOOTING_MAX_ITER):
            for name, segment in zip(SEGMENT_NAMES, self.segments(), strict=True):
                segment.restore_convergence_state(start[name])
                segment.mark_all_stale()
            outlet = self._march(inlet, P_in)
            residual = outlet.P.get_fresh() - P_outlet
            if abs(residual) <= _SHOOTING_REL_TOL * abs(P_outlet):
                return self._record_loop_state(
                    inlet,
                    P_inlet=P_in,
                    h_outlet=outlet.h.get_fresh(),
                    P_outlet=outlet.P.get_fresh(),
                    T_inlet=self.injection_well.state.T_inlet.get_fresh(),
                    T_outlet=self.production_well.state.T_outlet.get_fresh(),
                )
            if previous is None or previous[1] == residual:
                step = -residual
            else:
                slope = (residual - previous[1]) / (P_in - previous[0])
                step = -residual / slope
            previous = (P_in, residual)
            P_in += step
        raise ConvergenceError(
            f"grouped_subsurface (numerical): no injection pressure found that delivers the production "
            f"wellhead pressure {P_outlet:.6g} Pa within {_SHOOTING_MAX_ITER} marches (last trial "
            f"{P_in:.6g} Pa).",
        )

    def snapshot_convergence_state(self) -> Any:
        """Deep-copy the loop's own ``state`` and every segment's (see ``Component.snapshot_convergence_state``)."""
        return {
            "loop": copy.deepcopy(self.state),
            **{
                name: segment.snapshot_convergence_state()
                for name, segment in zip(SEGMENT_NAMES, self.segments(), strict=True)
            },
        }

    def restore_convergence_state(self, snapshot: Any) -> None:
        """Restore the loop's own ``state`` and every segment's from a ``snapshot_convergence_state()`` result."""
        self.state = copy.deepcopy(snapshot["loop"])
        for name, segment in zip(SEGMENT_NAMES, self.segments(), strict=True):
            segment.restore_convergence_state(snapshot[name])

    def accept_timestep(self) -> None:
        """Pass the accept on to every segment."""
        for segment in self.segments():
            segment.accept_timestep()

    def _state_history_pairs(self) -> list[tuple[Any, Any]]:
        """Add every segment's ``(state, history)`` pairs to the loop's own."""
        pairs = super()._state_history_pairs()
        for segment in self.segments():
            pairs.extend(segment._state_history_pairs())  # noqa: SLF001
        return pairs

    def well_sections(self) -> list[WellSection]:
        """Return the three segments as injection, horizontal and production sections."""
        roles = (WellRole.INJECTION, WellRole.HORIZONTAL, WellRole.PRODUCTION)
        return [
            WellSection(role, segment.well_length, segment.diameter, tuple(segment.history.pump_power_watts))
            for role, segment in zip(roles, self.segments(), strict=True)
        ]


class WellSegment(BaseModel):
    """One segment of a grouped subsurface whose wells an external simulator models: geometry only."""

    model_config = ConfigDict(extra="forbid")

    well_length: PositiveFloat = Field(frozen=True)
    """Segment length along the flow path (m)."""
    diameter: PositiveFloat = Field(frozen=True)
    """Inner diameter (m)."""
    pipe_roughness: PositiveFloat = Field(frozen=True)
    """Absolute wall roughness (m)."""
    wellhead_depth: float = Field(default=0.0, frozen=True)
    """True vertical depth (m) of the segment's shallow end; for the horizontal
    well, derived from the injection well's length (see
    ``tango.workflows.linked_quantities``)."""


class RaftGroupedSubsurface(GroupedSubsurfaceComponent):
    """Closed loop simulated by RAFT: wells and surrounding rock (see ``tango.external.raft_wrapper``).

    RAFT models the loop as one well with one diameter and roughness, so the
    three segments must share them. The segment lengths must match the well
    alignment in RAFT's config template, which its mesh was built for.
    """

    injection_well: WellSegment
    """The injection segment's geometry."""
    horizontal_well: WellSegment
    """The horizontal segment's geometry."""
    production_well: WellSegment
    """The production segment's geometry."""
    raft: RaftWrapper
    """RAFT's config template and the RAFT model run from it, with RAFT's own
    per-timestep ``state``/``history``."""

    def segments(self) -> tuple[WellSegment, WellSegment, WellSegment]:
        """Return the three segments in flow order."""
        return self.injection_well, self.horizontal_well, self.production_well

    def init(self) -> None:
        """Check the segments and prepare RAFT's config from its template.

        Raises:
            ConfigError: The segments differ in diameter or roughness, or the
                RAFT template disagrees with this config (see
                ``RaftWrapper.prepare``).
        """
        for quantity in ("diameter", "pipe_roughness"):
            values = {getattr(segment, quantity) for segment in self.segments()}
            if len(values) > 1:
                raise ConfigError(
                    f"grouped_subsurface variant 'raft' models the loop as one well, so all three segments "
                    f"need the same {quantity}; got {sorted(values)}.",
                )
        self.raft.prepare(
            self.common,
            LoopGeometry(
                injection_length=self.injection_well.well_length,
                horizontal_length=self.horizontal_well.well_length,
                production_length=self.production_well.well_length,
                diameter=self.injection_well.diameter,
                pipe_roughness=self.injection_well.pipe_roughness,
            ),
        )

    def solve_for_outlet_pressure(self, inlet: Stream, P_outlet: float) -> Stream:
        """Run one RAFT trial over this timestep, with RAFT solving for the injection pressure."""
        result = self.raft.solve(inlet, self.dt_years * YEAR_TO_SECOND, P_outlet)
        return self._record_loop_state(
            inlet,
            P_inlet=result.P_inlet,
            h_outlet=result.h_outlet,
            P_outlet=result.P_outlet,
            T_inlet=result.T_inlet,
            T_outlet=result.T_outlet,
        )

    def snapshot_convergence_state(self) -> Any:
        """Deep-copy the loop's own ``state`` and RAFT's (RAFT restarts each trial from its accepted state itself)."""
        return {"loop": copy.deepcopy(self.state), "raft": copy.deepcopy(self.raft.state)}

    def restore_convergence_state(self, snapshot: Any) -> None:
        """Restore the loop's own ``state`` and RAFT's from a ``snapshot_convergence_state()`` result."""
        self.state = copy.deepcopy(snapshot["loop"])
        self.raft.state = copy.deepcopy(snapshot["raft"])

    def accept_timestep(self) -> None:
        """Keep RAFT's last trial for this timestep."""
        self.raft.accept()

    def _state_history_pairs(self) -> list[tuple[Any, Any]]:
        """Add RAFT's ``(state, history)`` pair to the loop's own."""
        pairs = super()._state_history_pairs()
        pairs.append((self.raft.state, self.raft.history))
        return pairs

    def well_sections(self) -> list[WellSection]:
        """Return the three segments as injection, horizontal and production sections (no downhole pumps)."""
        roles = (WellRole.INJECTION, WellRole.HORIZONTAL, WellRole.PRODUCTION)
        return [
            WellSection(role, segment.well_length, segment.diameter)
            for role, segment in zip(roles, self.segments(), strict=True)
        ]
