"""Explicit solution for Isolated Doublet, Five Spot and Inverted Five Spot well patterns"""

import math
from enum import StrEnum
from typing import Self


class WellPattern(StrEnum):
    """Well pattern geometries with closed-form hydraulic impedance solutions.

    Each member represents a fixed well pattern layout (Doublet, Five Spot,
    Inverted Five Spot). Members may be looked up by their string value or
    name.

    Example: ``WellPattern("DOUBLET")``, ``WellPattern("doublet")``, and
    ``WellPattern("Doublet")`` (member name) all resolve to the same
    member — lookup is case-insensitive via ``_missing_`` below.
    """

    Doublet = "DOUBLET"
    """Doublet Well Pattern: one injection well, one prodcution well

    x: injection, o: production

    x - - - - - o

    well_spacing in config.yml file is the distance between the injection production pair
    """

    FiveSpot = "5SPOT"
    """Five Spot Well Pattern: four production wells, one injection well

    x: injection, o:production

    o - - - - - o
    |           |
    -     x     -
    |           |
    o - - - - - o

    well_spacing in config.yml file is the distance between an injection production pair
    """

    InvertedFiveSpot = "INVERTED_5SPOT"
    """Inverted Five Spot Well Pattern: four injection wells, one production well

    x: injection, o:production

    x - - - - - x
    |           |
    -     o     -
    |           |
    x - - - - - x

    well_spacing in config.yml file is the distance between an injection production pair"""

    AGSDoublet = "AGS_DOUBLET"
    """Injection and production pair in an AGS system, does not have an impedance function implemented yet"""

    @classmethod  # TODO: do we want to use aliases for user input, e.g. FIVE_SPOT -> 5SPOT? To add an alias: {str(Alias): class.subclass}
    def _missing_(cls, value: object) -> Self | None:
        """Resolve a well pattern from a config-style alias string.

        Called automatically by `Enum.__call__` when `value` doesn't match
        any member's name or assigned integer value. Allows lookups such as
        `WellPattern("5SPOT")` or `WellPattern("doublet")` (case-insensitive)
        in addition to `WellPattern(0)` / `WellPattern.Doublet`.

        Args:
            value: The lookup value passed to `WellPattern(value)`. Only
                `str` values are resolved here; anything else is deferred
                to the default Enum lookup behavior.

        Returns:
            The matching `WellPattern` member if `value` is a recognized
            alias string, or `None` for non-string input, which causes the
            default Enum lookup to raise its own `ValueError`.

        Raises:
            ValueError: If `value` is a string but does not match any
                known alias.

        """
        aliases: dict[str, Self] = {}

        if not isinstance(value, str):
            return None

        upper = value.upper()

        # 1. case-insensitive match against defined enum values
        for member in cls:
            if member.value.upper() == upper:
                return member

        # 2. alias match
        if upper in aliases:
            return aliases[upper]

        # 3. nothing matched
        enum_strings = [m.value for m in cls]
        raise ValueError(
            f"{value!r} is not a valid {cls.__name__}; "
            f"expected one of {enum_strings} or an alias {list(aliases)}",
        )

    def has_impedance_formula(self) -> bool:
        """Function to allow validation of well pattern by checking if it is implemented before running starting to run the similuation. The impedance functions are defined in self.impedance()"""
        try:
            self.impedance(
                mu=1.0,
                rho=1.0,
                permeability=1.0,
                thickness=1.0,
                net_to_gross_ratio=1.0,
                well_spacing=1.0,
                well_eff_diameter=1.0,
            )
        except NotImplementedError:
            return False
        return True

    def impedance(
        self,
        mu: float,
        rho: float,
        permeability: float,
        thickness: float,
        net_to_gross_ratio: float,
        well_spacing: float,
        well_eff_diameter: float,
    ) -> float:
        """Compute the hydraulic (flow) impedance for this well pattern.

        Implements the closed-form impedance solutions for Doublet, Five
        Spot, and Inverted Five Spot patterns based on Adams et al. (2020).

        Args:
            mu: Dynamic viscosity of the reservoir fluid (Pa·s).
            rho: Density of the reservoir fluid (kg/m³).
            permeability: Reservoir rock permeability (m²).
            thickness: Gross reservoir thickness (m).
            net_to_gross_ratio: Net-to-gross ratio for effective reservoir
                thickness (dimensionless).
            well_spacing: Injector-to-producer horizontal distance, `L` (m).
            well_eff_diameter: Effective well diameter used in the
                impedance calculation, `D` (m).

        Returns:
            Flow impedance Z, relating mass flow rate to pressure drop
            (Pa·s/kg).

        Raises:
            NotImplementedError: If this member has no impedance formula
                defined yet.

        References:
            Adams et al. (2020), Geothermics.
            https://doi.org/10.1016/j.geothermics.2023.102843

        """
        L = well_spacing
        D = well_eff_diameter
        b_eff = thickness * net_to_gross_ratio

        match self:
            case WellPattern.Doublet:
                return mu * (math.log(L / (math.e * D)) + D / L) / (rho * permeability * b_eff * math.pi)

            case WellPattern.FiveSpot:
                return (mu / (4 * rho * permeability * b_eff)) * math.log((4 * L) / (math.pi * D))

            case WellPattern.InvertedFiveSpot:
                return (mu / (rho * permeability * b_eff)) * math.log((4 * L) / (math.pi * D))

            case _:
                raise NotImplementedError(
                    f"The well pattern {self.name} has no impedance function defined yet.",
                )
