"""
Technology parameters for energy system optimization.
Defines cost and capacity parameters for each technology.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Union
import numpy as np


# Global constants
CO2_PRICE = 25.0  # EUR/tCO2
INTEREST_RATE = 0.05  # Interest rate for annuity calculation


@dataclass
class Technology:
    """Parameters for a single technology."""
    name: str
    installed_capacity: float  # MW
    min_generation: float      # Minimum output when ON (MW)
    max_generation: float      # Maximum output (MW) - nominal
    SpCC: float               # Specific Capital Cost (EUR/MW)
    OPEX_fix: float           # Fixed O&M (EUR/MW/year)
    OPEX_var: float           # Variable O&M (EUR/MWh)
    coldstart_cost: float              # Cold start cost (EUR/start)
    energy_carrier_price: Union[float, np.ndarray]  # EUR/MWh (constant or 8760 array)
    emission_factor: float              # CO2 emissions (tCO2/MWh_fuel)
    efficiency: Optional[float] = None  # Thermal efficiency (only for fuel-based)
    ramp_cost: float = 0.0              # Ramping cost (EUR/MWh ramp) - Hotmaps c_ramp_j
    excess_heat_source_price: float = 0.0  # Hotmaps: cost of excess heat source (EUR/MWh)
    lifetime: int = 25                   # Operation lifetime (years)
    max_generation_profile: Optional[np.ndarray] = None  # Hourly max gen limit (for Solar Thermal)
    # CHP-specific parameters
    chp_type: Optional[str] = None       # "backpressure" or "extraction" (None = not CHP)
    efficiency_el: Optional[float] = None  # Electrical efficiency (for CHP)
    ratio_pmax: Optional[float] = None     # Heat/Power ratio at max power (steam extraction)
    ratio_pmax_fw: Optional[float] = None  # Heat/Power ratio at full heat (steam extraction)
    sale_electricity_price: Union[float, np.ndarray, None] = None  # EUR/MWh electricity sale price
    # Piecewise linear performance (for geothermal etc.)
    piecewise_file: Optional[str] = None  # Path to CSV with piecewise breakpoints
    
    def get_energy_price(self, hour: int = None) -> float:
        """Get energy carrier price (constant or hour-specific)."""
        if isinstance(self.energy_carrier_price, np.ndarray):
            return self.energy_carrier_price[hour] if hour is not None else self.energy_carrier_price.mean()
        return self.energy_carrier_price
    
    @property
    def annual_capex(self) -> float:
        """Annual capital cost (EUR/year)."""
        return self.installed_capacity * self.SpCC
    
    @property
    def annual_fix_opex(self) -> float:
        """Annual fixed O&M cost (EUR/year)."""
        return self.installed_capacity * self.OPEX_fix
    
    @property
    def fuel_cost_per_mwh(self) -> float:
        """Fuel cost per MWh output (EUR/MWh)."""
        if self.efficiency is None:
            return self.energy_carrier_price
        return self.energy_carrier_price / self.efficiency
    
    @property
    def emission_per_mwh(self) -> float:
        """CO2 emissions per MWh output (tCO2/MWh)."""
        if self.efficiency is None:
            return self.emission_factor
        return self.emission_factor / self.efficiency


# Electricity price profile with seasonal variation
# Higher prices in winter (Nov-Feb), lower in summer (Jun-Aug)
from pre_processors.profile_generator import Profile
import numpy as np

import os

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
ELEC_PRICE_PROFILE = Profile.from_csv(os.path.join(_DATA_DIR, "Wien_2016_electricity_price_profile.csv"), column=1)

# Default technologies
GEOTHERMAL = Technology(
    name="Geothermal",
    installed_capacity=9.38,
    min_generation=0.0,
    max_generation=9.38,
    SpCC=2391474.27,
    OPEX_fix=2000.0,
    OPEX_var=1.1,
    coldstart_cost=1000.0,
    energy_carrier_price=ELEC_PRICE_PROFILE.values,  # Time-varying electricity price
    emission_factor=0.243,
    efficiency=0.9,  # Hotmaps uses 0.9, with 0.1 multiplier for geothermal cost
    lifetime=25
)

NATURAL_GAS = Technology(
    name="Natural Gas",
    installed_capacity=31.0,
    min_generation=0.0,
    max_generation=31.0,
    SpCC=60000.0,
    OPEX_fix=2000.0,
    OPEX_var=1.1,
    coldstart_cost=1000.0,
    energy_carrier_price=100.0,   # EUR/MWh_gas
    emission_factor=0.202,         # tCO2/MWh_gas
    efficiency=0.9,              # 90% thermal efficiency
    lifetime=25
)

# Boiler: Simple fuel-to-heat technology (similar to Natural Gas but different fuel)
BOILER = Technology(
    name="Boiler",
    installed_capacity=10.0,
    min_generation=0.0,
    max_generation=10.0,
    SpCC=50000.0,             # EUR/MW - lower than CHP
    OPEX_fix=1500.0,          # EUR/MW/year
    OPEX_var=0.5,             # EUR/MWh
    coldstart_cost=500.0,     # EUR/start
    energy_carrier_price=80.0,  # EUR/MWh_fuel (biomass/oil)
    emission_factor=0.18,       # tCO2/MWh_fuel
    efficiency=0.92,            # 92% thermal efficiency
    lifetime=20
)

# Waste Heat: Free heat source with zero fuel cost
WASTE_HEAT = Technology(
    name="Waste Heat",
    installed_capacity=5.0,
    min_generation=0.0,
    max_generation=5.0,
    SpCC=30000.0,             # EUR/MW - heat exchanger costs
    OPEX_fix=500.0,           # EUR/MW/year - low maintenance
    OPEX_var=0.2,             # EUR/MWh - minimal
    coldstart_cost=100.0,     # EUR/start
    energy_carrier_price=0.0,   # FREE - no fuel cost
    emission_factor=0.0,        # No direct emissions
    efficiency=0.95,            # Heat recovery efficiency
    lifetime=25
)

# Waste Treatment: Heat from waste incineration (limited by waste availability)
WASTE_TREATMENT = Technology(
    name="Waste Treatment",
    installed_capacity=5.0,
    min_generation=0.0,
    max_generation=5.0,
    SpCC=200000.0,            # EUR/MW - higher investment
    OPEX_fix=5000.0,          # EUR/MW/year - higher maintenance
    OPEX_var=2.0,             # EUR/MWh
    coldstart_cost=2000.0,    # EUR/start - complex startup
    energy_carrier_price=5.0,   # EUR/MWh waste - tipping fee income
    emission_factor=0.0,        # Biogenic, no net CO2
    efficiency=0.8,             # Waste-to-heat efficiency
    lifetime=30
)

# Solar Thermal: Radiation-dependent generation
# Note: max_generation is dynamically limited by radiation profile in optimizer
# max_gen_per_hour = installed_capacity * radiation[h] / 1000 (W/m² to kW/m²/MW)
SOLAR_THERMAL = Technology(
    name="Solar Thermal",
    installed_capacity=10.0,   # MW peak (at 1000 W/m²)
    min_generation=0.0,
    max_generation=10.0,       # Nominal capacity (actual varies with radiation)
    SpCC=400000.0,            # EUR/MW - collector field costs
    OPEX_fix=2000.0,          # EUR/MW/year
    OPEX_var=0.1,             # EUR/MWh - minimal
    coldstart_cost=0.0,       # EUR/start - no coldstart penalty
    energy_carrier_price=0.0,   # FREE - solar radiation
    emission_factor=0.0,        # Zero emissions
    efficiency=0.5,             # Solar collector efficiency
    lifetime=25
)

# CHP Backpressure: Fixed heat-to-power ratio
# P_el = P_th * (efficiency_el / efficiency_th)
CHP_BACKPRESSURE = Technology(
    name="CHP Backpressure",
    installed_capacity=5.0,    # MW_th thermal capacity
    min_generation=0.0,
    max_generation=5.0,
    SpCC=150000.0,            # EUR/MW_th
    OPEX_fix=3000.0,          # EUR/MW/year
    OPEX_var=1.5,             # EUR/MWh
    coldstart_cost=1500.0,    # EUR/start
    energy_carrier_price=100.0,  # EUR/MWh gas
    emission_factor=0.202,       # tCO2/MWh gas
    efficiency=0.45,             # Thermal efficiency
    efficiency_el=0.35,          # Electrical efficiency
    lifetime=25,
    chp_type="backpressure",
    sale_electricity_price=50.0  # EUR/MWh electricity sale price
)

# CHP Steam Extraction: Variable heat-to-power ratio with operating envelope
# Uses ratioPMax and ratioPMaxFW for envelope constraints
CHP_STEAM_EXTRACTION = Technology(
    name="CHP Steam Extraction",
    installed_capacity=5.0,    # MW_th thermal capacity
    min_generation=0.0,
    max_generation=5.0,
    SpCC=200000.0,            # EUR/MW_th - higher than backpressure
    OPEX_fix=4000.0,          # EUR/MW/year
    OPEX_var=2.0,             # EUR/MWh
    coldstart_cost=2000.0,    # EUR/start
    energy_carrier_price=100.0,  # EUR/MWh gas
    emission_factor=0.202,       # tCO2/MWh gas
    efficiency=0.45,             # Thermal efficiency (at full heat)
    efficiency_el=0.40,          # Electrical efficiency (at max power)
    lifetime=25,
    chp_type="extraction",
    ratio_pmax=0.549,            # P_th/P_el at max power = 450/820
    ratio_pmax_fw=0.643,         # P_th/P_el at full heat = 450/700
    sale_electricity_price=50.0  # EUR/MWh electricity sale price
)


@dataclass
class Storage:
    """Heat storage parameters."""
    name: str
    capacity: float                     # Storage Capacity [MWh]
    hourly_losses: float               # Hourly Storage Losses [%] (e.g., 0.01 = 1%)
    max_discharge_rate: float          # Maximum unloading power [MW]
    max_charge_rate: float             # Maximum loading power [MW]
    discharge_efficiency: float        # Unloading efficiency (e.g., 0.95)
    charge_efficiency: float           # Loading efficiency (e.g., 0.95)
    investment_cost_per_capacity: float  # EUR/MWh capacity
    lifetime: int = 25                   # Operation lifetime (years)


# =============================================================================
# HEAT PUMP TECHNOLOGIES
# =============================================================================
# Heat pumps consume electricity and use environmental heat sources.
# COP (Coefficient of Performance) = Heat_output / Electricity_input
# 
# For temperature-dependent COP calculation:
#   COP(t) = COP_nominal + (T_source(t) - T_source_nom) * cop_sensitivity_source
#                        + (T_return(t) - T_return_nom) * cop_sensitivity_return
#                        + (T_flow(t) - T_flow_nom) * cop_sensitivity_flow
#
# Heat pump categories (matching HotmapsDispatch):
# - Heat Pump Air: Uses ambient air as heat source
# - Heat Pump River Water: Uses river/lake water as heat source
# - Heat Pump Wastewater: Uses wastewater as heat source  
# - Heat Pump Industrial Wasteheat: Uses industrial waste heat as heat source

# Heat Pump Air: Air-source heat pump
# Lower COP due to cold winter air temperatures, but widely applicable
HEAT_PUMP_AIR = Technology(
    name="Heat Pump Air",
    installed_capacity=5.0,         # MW thermal output
    min_generation=0.5,             # MW - compressor minimum
    max_generation=5.0,             # MW
    SpCC=800000.0,                  # EUR/MW - higher than boilers
    OPEX_fix=3000.0,                # EUR/MW/year
    OPEX_var=0.5,                   # EUR/MWh
    coldstart_cost=200.0,           # EUR/start
    energy_carrier_price=ELEC_PRICE_PROFILE.values,  # Electricity consumption
    emission_factor=0.243,          # Electricity grid emission factor (tCO2/MWh_el)
    efficiency=3.0,                 # Nominal COP at standard conditions (7°C air, 35°C flow)
    lifetime=20
)

# Heat Pump River Water: Water-source heat pump using river/lake
# Higher and more stable COP than air-source
HEAT_PUMP_RIVER = Technology(
    name="Heat Pump River",
    installed_capacity=5.0,         # MW thermal output
    min_generation=0.5,             # MW
    max_generation=5.0,             # MW
    SpCC=900000.0,                  # EUR/MW - water intake infrastructure
    OPEX_fix=3500.0,                # EUR/MW/year
    OPEX_var=0.6,                   # EUR/MWh
    coldstart_cost=300.0,           # EUR/start
    energy_carrier_price=ELEC_PRICE_PROFILE.values,  # Electricity consumption
    emission_factor=0.243,          # Electricity grid emission factor (tCO2/MWh_el)
    efficiency=4.0,                 # Nominal COP at standard conditions (10°C water, 35°C flow)
    lifetime=20
)

# Heat Pump Wastewater: Uses wastewater as heat source
# High and very stable COP (wastewater temp ~10-22°C year-round)
HEAT_PUMP_WASTEWATER = Technology(
    name="Heat Pump Wastewater",
    installed_capacity=5.0,         # MW thermal output
    min_generation=0.5,             # MW
    max_generation=5.0,             # MW
    SpCC=950000.0,                  # EUR/MW - wastewater access infrastructure
    OPEX_fix=4000.0,                # EUR/MW/year
    OPEX_var=0.7,                   # EUR/MWh
    coldstart_cost=300.0,           # EUR/start
    energy_carrier_price=ELEC_PRICE_PROFILE.values,  # Electricity consumption
    emission_factor=0.243,          # Electricity grid emission factor (tCO2/MWh_el)
    efficiency=4.5,                 # Nominal COP at standard conditions (15°C wastewater, 35°C flow)
    lifetime=20
)

# Heat Pump Industrial Wasteheat: Uses industrial excess heat
# Highest COP due to warm source temperature (40-60°C typical)
HEAT_PUMP_WASTEHEAT = Technology(
    name="Heat Pump Wasteheat",
    installed_capacity=5.0,         # MW thermal output
    min_generation=0.5,             # MW
    max_generation=5.0,             # MW
    SpCC=700000.0,                  # EUR/MW - simpler system (warm source)
    OPEX_fix=2500.0,                # EUR/MW/year
    OPEX_var=0.4,                   # EUR/MWh
    coldstart_cost=200.0,           # EUR/start
    energy_carrier_price=ELEC_PRICE_PROFILE.values,  # Electricity consumption
    emission_factor=0.243,          # Electricity grid emission factor (tCO2/MWh_el)
    efficiency=6.0,                 # High COP due to warm source (~50°C)
    lifetime=20
)


# Default heat storage
HEAT_STORAGE = Storage(
    name="Heat Storage",
    capacity=50000.0,              # 50000 MWh
    hourly_losses=0.00007,        # 0.007% per hour
    max_discharge_rate=3.0,     # 3 MW unloading
    max_charge_rate=3.0,        # 3 MW loading
    discharge_efficiency=0.95,
    charge_efficiency=0.95,
    investment_cost_per_capacity=400.0,  # EUR/MWh
    lifetime=25
)