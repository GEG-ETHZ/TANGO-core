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
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from tango.components.well.base import HORIZONTAL_ANGLE_DEG, WellRole, WellSection
from tango.components.well.numerical import NumericalInjectionWell, NumericalProductionWell, NumericalWell
from tango.core.component import FlowComponent
from tango.core.errors import ConfigError
from tango.core.locked_state import LockedState
from tango.core.specs import Common
from tango.core.state_methods import StateMethods
from tango.core.stream import Stream

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
    """Pressure (Pa) at the injection wellhead."""
    mass_rate: LockedState[float] = field(default_factory=_ls_nan)
    """Mass flow rate (kg/s) around the loop."""
    h_outlet: LockedState[float] = field(default_factory=_ls_nan)
    """Specific enthalpy (J/kg) leaving the production well."""
    T_outlet: LockedState[float] = field(default_factory=_ls_nan)
    """Temperature (K) at the production wellhead."""
    P_outlet: LockedState[float] = field(default_factory=_ls_nan)
    """Pressure (Pa) at the production wellhead."""
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

    state: GroupedSubsurfaceState = Field(default_factory=GroupedSubsurfaceState)
    history: GroupedSubsurfaceHistory = Field(default_factory=GroupedSubsurfaceHistory)

    @abstractmethod
    def well_sections(self) -> list[WellSection]:
        """Return the loop's drilled sections, in flow order, for the economic model."""

    def _record_loop_state(
        self,
        inlet: Stream,
        h_outlet: float,
        P_outlet: float,
        T_inlet: float,
        T_outlet: float,
    ) -> Stream:
        """Write ``state`` and ``outlet`` from the loop's inlet and outlet conditions, and return ``outlet``.

        The outlet's mass rate is the inlet's (constant mass flow around the loop).
        """
        s = self.state
        h_inlet = inlet.h.get_fresh()
        mass_rate = inlet.mass_rate.get_fresh()
        s.h_inlet.update(h_inlet)
        s.T_inlet.update(T_inlet)
        s.P_inlet.update(inlet.P.get_fresh())
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
    horizontal_well: NumericalWell
    production_well: NumericalProductionWell

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

    def solve(self, inlet: Stream) -> Stream:
        """March the injection, horizontal and production wells in sequence."""
        stream = inlet
        for segment in self.segments():
            stream = segment.solve(stream)
        return self._record_loop_state(
            inlet,
            h_outlet=stream.h.get_fresh(),
            P_outlet=stream.P.get_fresh(),
            T_inlet=self.injection_well.state.T_inlet.get_fresh(),
            T_outlet=self.production_well.state.T_outlet.get_fresh(),
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
