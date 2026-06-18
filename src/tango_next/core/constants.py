"""Physical constants and SI prefix scalars for tango_next.

Unit conversions should be expressed as named constants imported from here,
not as magic numbers inline.  For example::

    p_megapascals = p_pascals * PA_TO_MPA
    p_kilopascals = p_megapascals * MEGA_TO_KILO

SI prefix multipliers
---------------------
KILO  = 1e3    (k)
MEGA  = 1e6    (M)
GIGA  = 1e9    (G)
MILLI = 1e-3   (m)
MICRO = 1e-6   (μ)

Derived ratio scalars (convenient shorthand)
--------------------------------------------
MEGA_TO_KILO = 1e3   (e.g. MPa → kPa)
PA_TO_MPA    = 1e-6
PA_TO_KPA    = 1e-3
W_TO_KW      = 1e-3
W_TO_MW      = 1e-6
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

GRAVITY: float = 9.80665
"""Standard gravitational acceleration (m/s²).  NIST / ISO 80000-3."""

YEAR_TO_SECOND: float = 31_536_000.0
"""Seconds per (365-day) year.  Matches src/tango/core/constants.py exactly,
for parity in dimensionless-time calculations (e.g. wellbore heat-loss models)."""

# ---------------------------------------------------------------------------
# SI prefix multipliers
# ---------------------------------------------------------------------------

KILO: float = 1e3
MEGA: float = 1e6
GIGA: float = 1e9
MILLI: float = 1e-3
MICRO: float = 1e-6

# ---------------------------------------------------------------------------
# Derived unit-conversion scalars
# ---------------------------------------------------------------------------

MEGA_TO_KILO: float = 1e3
"""Multiply a value in mega-units to get kilo-units (e.g. MPa → kPa)."""

PA_TO_MPA: float = 1e-6
"""Multiply Pa to get MPa."""

PA_TO_KPA: float = 1e-3
"""Multiply Pa to get kPa."""

W_TO_KW: float = 1e-3
"""Multiply W to get kW."""

W_TO_MW: float = 1e-6
"""Multiply W to get MW."""
