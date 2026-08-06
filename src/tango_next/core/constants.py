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
MPA_TO_PA    = 1e6
PA_TO_KPA    = 1e-3
PA_TO_BAR    = 1e-5
BAR_TO_PA    = 1e5
W_TO_KW      = 1e-3
W_TO_MW      = 1e-6

Temperature offsets (additive, not multiplicative)
----------------------------------------------------
C_TO_K_OFFSET = 273.15   (degC + C_TO_K_OFFSET -> K)
K_TO_C_OFFSET = -273.15  (K + K_TO_C_OFFSET -> degC)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

GRAVITY: float = 9.81
"""Gravitational acceleration (m/s²) — default value only; per-component
`gravity` fields (well/reservoir components) can override this, since
gravity genuinely varies regionally by up to ~0.5%.

TODO: matches src/tango/'s rounded GRAVITY_ACCELERATION (2026-08, for
parity comparison purposes) rather than the more precise NIST/ISO 80000-3
standard value (9.80665) this used to be. Revisit switching the *default*
back to 9.80665 once old-tango parity is no longer the active concern —
component-level overrides make this a one-line change whenever that
happens."""

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

MPA_TO_PA: float = 1e6
"""Multiply MPa to get Pa."""

PA_TO_KPA: float = 1e-3
"""Multiply Pa to get kPa."""

PA_TO_BAR: float = 1e-5
"""Multiply Pa to get bar."""

BAR_TO_PA: float = 1e5
"""Multiply bar to get Pa."""

W_TO_KW: float = 1e-3
"""Multiply W to get kW."""

W_TO_MW: float = 1e-6
"""Multiply W to get MW."""

C_TO_K_OFFSET: float = 273.15
"""Add to a temperature in degC to get K."""

K_TO_C_OFFSET: float = -273.15
"""Add to a temperature in K to get degC."""

EULER_CONSTANT: float = 0.5772156649015329
"""The Euler-Mascheroni constant γ, to float64 precision. Used by
``fluid_utils.heat_loss_adams_2015``'s Adams-2015 β correlation for
``t_d > 2.8`` — the correlation's coefficient is exactly ``2γ``, which the
source paper rounds to 1.16 with no stated justification (``2 × 0.57721566...
≈ 1.15442``, closer to 1.15 than 1.16). We use the actual constant instead
of either rounding."""
EULER_CONSTANT_X2: float = EULER_CONSTANT * 2.0
"""``2γ`` — see ``EULER_CONSTANT``."""
