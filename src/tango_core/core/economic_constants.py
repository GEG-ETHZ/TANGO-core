"""Hardcoded cost-model constants for ``DoubletEconomicComponent``.

Every CAPEX formula that uses these constants (``DoubletEconomicComponent``,
``components/economic/doublet.py``) multiplies by a
Producer Price Index (PPI) value and an installation/contingency multiplier
pair (X_IC, X_PC), both looked up from two real tables
(``data/PPI_Table.xlsx``, ``data/cost_multiplier_table.xlsx`` — since
removed as dead weight once their values were baked in below) at a
"cost year" derived from the simulation's ``start_date``.

``tango_core`` has no calendar/``start_date`` concept at all (``SimConfig``
only has ``num_tsteps``/``dt_years``), so there's no dynamic year to look up
against. This module hardcodes the **2019** row of both tables — as named
constants, pulled directly from the real tables before their removal
(verified via ``pandas.read_excel("data/PPI_Table.xlsx", header=1)`` and
``pandas.read_excel("data/cost_multiplier_table.xlsx")``).

This is a deliberate, documented Phase-1 simplification: no PPI-table/
interpolation machinery is ported, so cost-year sensitivity isn't
supported. If tango ever gains a calendar concept, revisit this module
to look values up dynamically instead of hardcoding one year.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# PPI values — data/PPI_Table.xlsx, Year == 2019 row
# ---------------------------------------------------------------------------

PPI_PIPE: float = 2.09238776837996
"""Pipe PPI (surface gathering pipes)."""
PPI_T_G: float = 1.40640096618358
"""Turbine-generator PPI."""
PPI_HX: float = 1.79679450486548
"""2-stream heat exchanger PPI (preheater/boiler/recuperator)."""
PPI_PUMP: float = 1.61687986934336
"""Pump PPI (injection pump)."""
PPI_PE: float = 1.79364076125576
"""Process-equipment PPI (cooler/condenser BAC regression)."""
PPI_O_AND_G: float = 2.19543973941368
"""Oil & gas well PPI (well CAPEX)."""
PPI_PERMIT: float = 1.83976992604766
"""Permitting (legal services) PPI."""
PPI_O_AND_G_S: float = 1.43740902474527
"""O&G support-activities PPI (exploration CAPEX)."""

# ---------------------------------------------------------------------------
# Installation-cost / project-contingency multipliers — data/cost_multiplier_table.xlsx
# ---------------------------------------------------------------------------

X_IC_WELLS: float = 1.05
"""Installation-cost multiplier for wells/exploration."""
X_PC_WELLS: float = 1.15
"""Project-contingency multiplier for wells/exploration."""
X_IC_SURFACE: float = 1.12
"""Installation-cost multiplier for the surface plant/pipes."""
X_PC_SURFACE: float = 1.15
"""Project-contingency multiplier for the surface plant/pipes."""

# ---------------------------------------------------------------------------
# Fixed dollar constants (permitting, exploration)
# ---------------------------------------------------------------------------

PERMITTING_BASE_COST_USD: float = 665_700.0
"""Base permitting cost (USD, before PPI/multiplier scaling), H2O/non-CO2."""
EXPLORATION_BASE_COST_USD: float = 508_000.0
"""Base exploration cost (USD, before PPI/multiplier scaling), H2O/non-CO2."""

# ---------------------------------------------------------------------------
# Surface-plant equipment-cost markup chain
# ---------------------------------------------------------------------------

TEC_MULTIPLIER: float = 1.39
"""Total Equipment Cost = TEC_MULTIPLIER * sum(primary equipment costs)."""
BEC_MARKUP: float = 1.0 + 0.58 + 0.11 + 0.00 + 0.04
"""Bare Erected Cost = TEC * BEC_MARKUP (site prep, buildings, engineering, ...)."""
