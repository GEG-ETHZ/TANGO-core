"""Config values that are linked across components: each has one source, the rest are derived.

Several quantities appear in more than one place in a config because more
than one component needs them: a doublet's reservoir depth is also the
injection well's length and the sum of the two production-well segments; an
AGS loop's depth is both vertical wells' length and the horizontal well's
starting depth. Writing each copy by hand lets them disagree silently, and
a sweep that changes one copy but not another gets a wrong answer with no
error.

``resolve_linked_quantities`` runs on the raw config before any component
is built. For each relation, a value the config leaves out is derived from
the ones it gives, and a value it does give must agree with the others or
``ConfigError`` is raised. So a config (or a sweep editing one) writes each
quantity once, and a stale copy is an error rather than a wrong result.

The relations depend on the subsurface topology, recognized by component
name:

- **Doublet** (``reservoir``, ``injection_well``, ``production_well_lower``,
  ``production_well_upper``): ``reservoir_depth`` = injection well length =
  upper + lower production segment lengths; the lower segment starts where
  the upper one ends; ``well_eff_diameter`` is the mean of the injection and
  production well diameters; ``hydro_static_pressure`` = ``brine_density``
  x ``gravity`` x ``reservoir_depth``.
- **AGS closed loop** (``injection_well``, ``horizontal_well``,
  ``production_well``): both vertical wells have the loop's depth as their
  length, the horizontal well starts at that depth, and
  ``layout.well_spacing`` (the surface distance between the wellheads) is
  the horizontal well's length.
- **AGS closed loop as one component** (any component with
  ``type: grouped_subsurface``): the same three relations, between its
  ``injection_well``, ``horizontal_well`` and ``production_well`` segment
  blocks.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tango_core.core.constants import GRAVITY
from tango_core.core.errors import ConfigError

_REL_TOL = 1e-9
"""Relative tolerance for given values to count as agreeing (float noise only)."""

Path = tuple[str, ...]


@dataclass(frozen=True)
class _Source:
    """One input to a relation; ``default`` stands in when the config leaves it out."""

    path: Path
    default: float | None = None


@dataclass(frozen=True)
class _Relation:
    """``target = fn(*sources)``; ``why`` explains the link in error messages.

    ``inverse`` (optional) recovers ``sources[inverse_index]`` from the target
    and the other sources, so the relation can also fill in a missing source.
    """

    target: Path
    sources: tuple[_Source, ...]
    fn: Callable[..., float]
    why: str
    inverse: Callable[..., float] | None = None
    inverse_index: int = 0


def _get(cfg: dict[str, Any], path: Path) -> Any:
    node: Any = cfg
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _set(cfg: dict[str, Any], path: Path, value: float) -> None:
    node = cfg
    for key in path[:-1]:
        if node.get(key) is None:  # absent, or a YAML block left empty (``layout:`` with only comments)
            node[key] = {}
        node = node[key]
    node[path[-1]] = value


def _dotted(path: Path) -> str:
    return ".".join(path)


def _relations(cfg: dict[str, Any]) -> list[_Relation]:
    components = cfg.get("components")
    if not isinstance(components, dict):
        return []  # Workflow reports the missing/invalid components block itself
    c = ("components",)
    relations: list[_Relation] = []
    if {"reservoir", "injection_well", "production_well_lower", "production_well_upper"} <= set(components):
        depth = (*c, "reservoir", "reservoir_depth")
        upper_length = (*c, "production_well_upper", "well_length")
        relations += [
            _Relation(
                (*c, "injection_well", "well_length"),
                (_Source(depth),),
                lambda d: d,
                "the injection well reaches the reservoir",
                inverse=lambda length: length,
            ),
            _Relation(
                (*c, "production_well_lower", "wellhead_depth"),
                (_Source(upper_length),),
                lambda u: u,
                "the lower production segment starts where the upper one ends",
                inverse=lambda wd: wd,
            ),
            _Relation(
                (*c, "production_well_lower", "well_length"),
                (_Source(depth), _Source(upper_length)),
                lambda d, u: d - u,
                "the two production segments together reach the reservoir",
                inverse=lambda lower, u: lower + u,
            ),
            _Relation(
                (*c, "reservoir", "well_eff_diameter"),
                (
                    _Source((*c, "injection_well", "diameter")),
                    _Source((*c, "production_well_lower", "diameter")),
                ),
                lambda inj, prod: 0.5 * (inj + prod),
                "the reservoir impedance uses the mean of the injection and production well diameters",
            ),
            _Relation(
                (*c, "reservoir", "hydro_static_pressure"),
                (
                    _Source((*c, "reservoir", "brine_density"), default=1000.0),
                    _Source((*c, "reservoir", "gravity"), default=GRAVITY),
                    _Source(depth),
                ),
                lambda rho, g, d: rho * g * d,
                "hydrostatic pressure at the reservoir is brine_density x gravity x reservoir_depth",
            ),
        ]
    loop_prefixes: list[Path] = []
    if {"injection_well", "horizontal_well", "production_well"} <= set(components):
        loop_prefixes.append(c)
    loop_prefixes += [
        (*c, name)
        for name, component in components.items()
        if isinstance(component, dict) and component.get("type") == "grouped_subsurface"
    ]
    for prefix in loop_prefixes:
        depth = (*prefix, "injection_well", "well_length")
        loop = (*prefix, "horizontal_well", "well_length")
        relations += [
            _Relation(
                (*prefix, "production_well", "well_length"),
                (_Source(depth),),
                lambda d: d,
                "both vertical wells reach the loop's depth",
                inverse=lambda length: length,
            ),
            _Relation(
                (*prefix, "horizontal_well", "wellhead_depth"),
                (_Source(depth),),
                lambda d: d,
                "the horizontal loop lies at the vertical wells' depth",
                inverse=lambda wd: wd,
            ),
            _Relation(
                ("layout", "well_spacing"),
                (_Source(loop),),
                lambda length: length,
                "the wellheads are a loop length apart at the surface",
                inverse=lambda spacing: spacing,
            ),
        ]
    return relations


def resolve_linked_quantities(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``config`` with every linked quantity filled in and checked.

    See the module docstring for the relations.

    Raises:
        ConfigError: The config gives linked values that disagree, e.g. a
            sweep changed the reservoir depth but left the injection well's
            length at its old value. The message names every value involved
            and the relation; give the quantity once and let the others be
            derived.
    """
    cfg = copy.deepcopy(config)
    relations = _relations(cfg)

    def values(rel: _Relation) -> list[float | None]:
        return [float(v) if (v := _get(cfg, s.path)) is not None else s.default for s in rel.sources]

    changed = True
    while changed:
        changed = False
        for rel in relations:
            src = values(rel)
            target = _get(cfg, rel.target)
            if target is None and None not in src:
                _set(cfg, rel.target, rel.fn(*src))
                changed = True
            elif target is not None and rel.inverse is not None:
                missing = [i for i, v in enumerate(src) if v is None]
                if missing == [rel.inverse_index]:
                    others = [v for i, v in enumerate(src) if i != rel.inverse_index]
                    _set(cfg, rel.sources[rel.inverse_index].path, rel.inverse(float(target), *others))
                    changed = True

    for rel in relations:
        src = values(rel)
        target = _get(cfg, rel.target)
        if target is None or None in src:
            continue
        expected = rel.fn(*src)
        if not math.isclose(float(target), expected, rel_tol=_REL_TOL):
            given = ", ".join(f"{_dotted(s.path)}={v:g}" for s, v in zip(rel.sources, src, strict=True))
            raise ConfigError(
                f"{_dotted(rel.target)} is {float(target):g} but {rel.why}, which gives {expected:g} "
                f"(from {given}). These values are linked: give the quantity once and leave "
                f"{_dotted(rel.target)} out so it is derived.",
            )
    return cfg


def expunge_linked_quantities(config: dict[str, Any]) -> None:
    """Remove every derived linked value from ``config`` in place, keeping each quantity's single source.

    ``Workflow.to_dict()`` writes every copy of a linked quantity, so a copy
    of it can't have one value edited without the others disagreeing (an
    error). Call this on such a copy first; afterwards set the source value
    (e.g. ``reservoir.reservoir_depth``) and the rest are derived again.
    """
    for rel in _relations(config):
        node: Any = config
        for key in rel.target[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict):
            node.pop(rel.target[-1], None)
