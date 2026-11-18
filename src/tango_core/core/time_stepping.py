# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Configurable time stepping: the ``sim_config.time_stepping`` block and the steps it describes.

All times here are in seconds, measured from the start of operation.

A run's time steps come from one of two places:

- the shorthand ``sim_config.num_tsteps`` and ``sim_config.dt_years``,
  which puts every component on one shared fixed grid;
- the ``sim_config.time_stepping`` block, which groups the components into
  subsystems (each a contiguous run of circuit components) and gives each
  subsystem its own grid.

A grid is one of several schemes (``GridScheme``), picked per case for the
accuracy and run time it needs, and expands to a list of ``TimeStep``s.
Averages over a run weight each recorded value by the length of its step
(``time_weighted_mean``), so a short step counts for less than a long one.

With several subsystems, the times that every grid has a step end at are
the sync times. Between two sync times (a ``SyncInterval``) each subsystem
takes its own steps, and a stream passing from one subsystem to the next
is converted to the receiving subsystem's steps by a ``SyncRule``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)

from tango_core.core.stream import Stream

if TYPE_CHECKING:
    from collections.abc import Sequence

_GRID_END_REL_TOL: float = 1e-9
"""Relative tolerance for two times to count as the same (float noise only): two grids' ends, or two
grids' step ends at a sync time."""

_EDGE_SEPARATOR: str = "->"
"""Separator between the two subsystem names of a ``time_stepping.sync`` key."""


@dataclass(frozen=True)
class TimeStep:
    """One step of a time grid: the interval a component solves over.

    Attributes:
        index: Zero-based position of this step in its time grid.
        t_start: Time at the start of the step (s since the start of operation).
        dt: Length of the step (s).
    """

    index: int
    t_start: float
    dt: float

    @property
    def t_end(self) -> float:
        """Time at the end of the step (s since the start of operation)."""
        return self.t_start + self.dt


@dataclass
class TimeHistory:
    """The time axis of a component's recorded history: one entry per recorded step.

    Entry ``i`` describes the step whose values sit at position ``i`` of
    every other history list of the same component, so ``save_interval``
    thinning keeps the two aligned.
    """

    t_start: list[float] = field(default_factory=list)
    """Start time of each recorded step (s since the start of operation)."""
    dt: list[float] = field(default_factory=list)
    """Length of each recorded step (s)."""

    def record(self, step: TimeStep) -> None:
        """Append one recorded step."""
        self.t_start.append(step.t_start)
        self.dt.append(step.dt)

    @property
    def t_end(self) -> list[float]:
        """End time of each recorded step (s since the start of operation)."""
        return [t_start + dt for t_start, dt in zip(self.t_start, self.dt, strict=True)]


class SyncRule(StrEnum):
    """How a stream from one subsystem becomes the inlet of the next subsystem's steps.

    A rule is set per edge in ``time_stepping.sync``. An edge without one
    uses ``hold`` when the receiving subsystem takes more steps than the
    sending one, and ``period_average`` otherwise.
    """

    HOLD = "hold"
    """Each receiving step gets the sent value of the sending step that covers the receiving step's start."""
    PERIOD_AVERAGE = "period_average"
    """Each receiving step gets the average of the sent values over its own span, weighted by overlap."""


@dataclass(frozen=True)
class SyncInterval:
    """The span between two consecutive sync times, and each subsystem's steps within it.

    Attributes:
        index: Zero-based position of this interval in the run.
        t_start: Time at the start of the interval (s since the start of operation).
        t_end: Time at the end of the interval (s since the start of operation).
        steps: Each subsystem's steps in this interval, keyed by subsystem
            name, in time order. They cover the interval exactly.
    """

    index: int
    t_start: float
    t_end: float
    steps: dict[str, tuple[TimeStep, ...]]


class GridScheme(StrEnum):
    """How a subsystem's grid places its steps."""

    FIXED = "fixed"
    """``num_steps`` even steps of ``step`` seconds."""
    TIMES = "times"
    """An explicit, strictly increasing list of step end times."""


class FixedGrid(BaseModel):
    """``num_steps`` even steps of ``step`` seconds, from the start of operation.

    With a single subsystem this is the same grid as the ``num_tsteps``/
    ``dt_years`` shorthand. It differs once there are several subsystems,
    each of which can have fixed steps of its own length.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scheme: Literal[GridScheme.FIXED]
    """Grid scheme selector, ``fixed``."""
    step: PositiveFloat
    """Step length (s)."""
    num_steps: PositiveInt
    """Number of steps."""

    @property
    def end(self) -> float:
        """Time at the end of the last step (s since the start of operation)."""
        return self.num_steps * self.step

    def steps(self) -> list[TimeStep]:
        """Expand to ``num_steps`` equal steps.

        Each step's ``dt`` is ``step`` itself, not a difference of two
        times, so every step solves over exactly the configured length.
        """
        return [TimeStep(index=k, t_start=k * self.step, dt=self.step) for k in range(self.num_steps)]


class TimesGrid(BaseModel):
    """Steps that end at each of an explicit list of times, the first one starting at 0."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scheme: Literal[GridScheme.TIMES]
    """Grid scheme selector, ``times``."""
    times: list[PositiveFloat] = Field(min_length=1)
    """End time of each step (s since the start of operation), strictly
    increasing. These are times, not step lengths; the last one is the end
    of the grid."""

    @field_validator("times")
    @classmethod
    def check_strictly_increasing(cls, times: list[float]) -> list[float]:
        """Reject a list of times that does not strictly increase.

        Raises:
            ValueError: Two consecutive times are equal or decreasing.
        """
        for earlier, later in zip(times, times[1:], strict=False):
            if later <= earlier:
                raise ValueError(
                    f"time_stepping times must strictly increase; {later:.6g} s follows {earlier:.6g} s.",
                )
        return times

    @property
    def end(self) -> float:
        """Time at the end of the last step (s since the start of operation)."""
        return self.times[-1]

    def steps(self) -> list[TimeStep]:
        """Expand to one step per listed time, each from the previous time (or 0) to that time."""
        steps = []
        t_start = 0.0
        for index, t_end in enumerate(self.times):
            steps.append(TimeStep(index=index, t_start=t_start, dt=t_end - t_start))
            t_start = t_end
        return steps


Grid = Annotated[FixedGrid | TimesGrid, Field(discriminator="scheme")]
"""Any grid scheme, selected by its ``scheme`` field."""


class Subsystem(BaseModel):
    """Components that step together on one grid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    components: list[str] = Field(min_length=1)
    """Names of the components in this subsystem, as keyed under ``components:``."""
    grid: Grid
    """Where this subsystem's steps fall."""

    @field_validator("components")
    @classmethod
    def check_unique(cls, components: list[str]) -> list[str]:
        """Reject a component listed twice.

        Raises:
            ValueError: A name appears more than once.
        """
        repeated = sorted({name for name in components if components.count(name) > 1})
        if repeated:
            raise ValueError(f"Subsystem lists {repeated!r} more than once.")
        return components


class TimeStepping(BaseModel):
    """Schema for the ``sim_config.time_stepping:`` YAML block.

    The project lifetime is where the grids end; every subsystem's grid
    must end at the same time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    subsystems: dict[str, Subsystem] = Field(min_length=1)
    """Subsystems keyed by name. Every circuit component belongs to exactly one."""
    sync: dict[str, SyncRule] = Field(default_factory=dict)
    """Sync rule per edge, keyed ``"<from> -> <to>"`` by subsystem name. An
    edge left out uses the default (see ``SyncRule``)."""

    @model_validator(mode="after")
    def check_subsystems(self) -> TimeStepping:
        """Check that no component is in two subsystems, all grids end together, and ``sync`` names real subsystems.

        Raises:
            ValueError: A component in two subsystems, grids that end at
                different times, or a ``sync`` key that is not
                ``"<from> -> <to>"`` for two different subsystems.
        """
        seen: dict[str, str] = {}
        for name, subsystem in self.subsystems.items():
            for component in subsystem.components:
                if component in seen:
                    raise ValueError(
                        f"Component {component!r} is in both subsystem {seen[component]!r} and {name!r}.",
                    )
                seen[component] = name
        ends = {name: subsystem.grid.end for name, subsystem in self.subsystems.items()}
        first_end = next(iter(ends.values()))
        if not all(math.isclose(end, first_end, rel_tol=_GRID_END_REL_TOL) for end in ends.values()):
            listed = ", ".join(f"{name} at {end:.6g} s" for name, end in ends.items())
            raise ValueError(f"Every subsystem's grid must end at the same time; they end {listed}.")
        for key in self.sync:
            self.edge(key)
        return self

    def edge(self, key: str) -> tuple[str, str]:
        """Split a ``sync`` key ``"<from> -> <to>"`` into its two subsystem names.

        Raises:
            ValueError: The key is not two different subsystem names joined by ``->``.
        """
        sender, separator, receiver = (part.strip() for part in key.partition(_EDGE_SEPARATOR))
        if not separator or sender == receiver or not {sender, receiver} <= set(self.subsystems):
            raise ValueError(
                f"time_stepping.sync key {key!r} must be '<from> -> <to>' for two different subsystems, "
                f"from {sorted(self.subsystems)!r}.",
            )
        return sender, receiver

    def sync_rule(self, sender: str, receiver: str) -> SyncRule:
        """Return the rule for the edge from ``sender`` to ``receiver``: the configured one, or the default.

        The default is ``hold`` when ``receiver``'s grid has more steps than
        ``sender``'s, and ``period_average`` otherwise (see ``SyncRule``).
        """
        for key, rule in self.sync.items():
            if self.edge(key) == (sender, receiver):
                return rule
        n_sender = len(self.subsystems[sender].grid.steps())
        n_receiver = len(self.subsystems[receiver].grid.steps())
        return SyncRule.HOLD if n_receiver >= n_sender else SyncRule.PERIOD_AVERAGE

    @property
    def end(self) -> float:
        """Project lifetime (s): the time at which every subsystem's grid ends."""
        return next(iter(self.subsystems.values())).grid.end

    def intervals(self) -> list[SyncInterval]:
        """Split the run at the sync times, the step end times every subsystem's grid shares.

        With one subsystem, every step is its own interval.
        """
        grids = {name: subsystem.grid.steps() for name, subsystem in self.subsystems.items()}
        first, *others = grids.values()
        sync_times = [step.t_end for step in first]
        for steps in others:
            sync_times = _shared_times(sync_times, [step.t_end for step in steps], self.end)
        intervals: list[SyncInterval] = []
        position = dict.fromkeys(grids, 0)
        t_start = 0.0
        for index, t_end in enumerate(sync_times):
            in_interval: dict[str, tuple[TimeStep, ...]] = {}
            for name, steps in grids.items():
                begin = position[name]
                while not _same_time(steps[position[name]].t_end, t_end, self.end):
                    position[name] += 1
                position[name] += 1
                in_interval[name] = tuple(steps[begin : position[name]])
            intervals.append(SyncInterval(index=index, t_start=t_start, t_end=t_end, steps=in_interval))
            t_start = t_end
        return intervals


def _shared_times(times: list[float], other: list[float], end: float) -> list[float]:
    """The entries of ``times`` that are also in ``other`` (both increasing), in one pass over each."""
    shared = []
    j = 0
    for t in times:
        while j < len(other) and other[j] < t and not _same_time(other[j], t, end):
            j += 1
        if j < len(other) and _same_time(other[j], t, end):
            shared.append(t)
    return shared


def _same_time(a: float, b: float, end: float) -> bool:
    """Whether two times are equal up to float noise, relative to the project lifetime ``end``."""
    return math.isclose(a, b, rel_tol=_GRID_END_REL_TOL, abs_tol=_GRID_END_REL_TOL * end)


def sync_stream(rule: SyncRule, sent: Sequence[tuple[TimeStep, Stream]], step: TimeStep) -> Stream:
    """The inlet for receiving ``step``, from the streams a sending subsystem passed on over its own steps.

    A single sent value that covers ``step`` is passed on unchanged, under
    either rule, so two subsystems on the same grid give exactly the run of
    one subsystem on that grid. ``period_average`` averages ``h``, ``P``,
    and the mass rate separately, each weighted by overlap time; the mass
    rate is the same in every sent stream of a circuit that conserves mass.

    Args:
        rule: The edge's sync rule.
        sent: Each sending step in this interval with the stream it passed
            on, in time order.
        step: The receiving step.

    Returns:
        A fresh ``Stream`` for the receiving component's ``solve``.

    Raises:
        ValueError: No sent step covers ``step``.
    """
    tolerance = _GRID_END_REL_TOL * max(abs(step.t_end), 1.0)
    covering = [
        (sent_step, stream)
        for sent_step, stream in sent
        if sent_step.t_start < step.t_end - tolerance and sent_step.t_end > step.t_start + tolerance
    ]
    if not covering:
        raise ValueError(f"No sent stream covers the step from {step.t_start:.6g} s to {step.t_end:.6g} s.")
    if rule is SyncRule.HOLD or len(covering) == 1:
        _, stream = covering[0]
        return Stream.fresh(
            h=stream.h.get_fresh(),
            P=stream.P.get_fresh(),
            mass_rate=stream.mass_rate.get_fresh(),
        )
    overlaps = [
        min(sent_step.t_end, step.t_end) - max(sent_step.t_start, step.t_start) for sent_step, _ in covering
    ]
    return Stream.fresh(
        h=time_weighted_mean([stream.h.get_fresh() for _, stream in covering], overlaps),
        P=time_weighted_mean([stream.P.get_fresh() for _, stream in covering], overlaps),
        mass_rate=time_weighted_mean([stream.mass_rate.get_fresh() for _, stream in covering], overlaps),
    )


def time_weighted_mean(
    values: list[float] | tuple[float, ...],
    durations: list[float] | tuple[float, ...],
) -> float:
    """Mean of ``values``, each weighted by the length of the step it was recorded on.

    When every duration is equal this is the plain mean, and it is computed
    as one (``sum / len``) so that runs on an evenly spaced grid round
    exactly as they did before time weighting.

    Args:
        values: One recorded value per step.
        durations: The matching steps' lengths (s), e.g. ``TimeHistory.dt``.

    Returns:
        The weighted mean, or 0.0 if ``values`` is empty.

    Raises:
        ValueError: ``values`` and ``durations`` differ in length.
    """
    if len(values) != len(durations):
        raise ValueError(f"{len(values)} values but {len(durations)} durations; they must align one to one.")
    if not values:
        return 0.0
    if all(duration == durations[0] for duration in durations):
        return sum(values) / len(values)
    return sum(value * duration for value, duration in zip(values, durations, strict=True)) / sum(durations)
