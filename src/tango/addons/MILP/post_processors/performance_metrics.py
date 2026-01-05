"""Performance metrics module for energy system optimization.

Provides Hotmaps-compatible cost breakdown and performance indicators.
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass
from opt_inputs.tech_params import Technology, Storage, CO2_PRICE, INTEREST_RATE


@dataclass
class CostBreakdown:
    """Cost breakdown for a single technology (Hotmaps compatible)."""
    name: str
    fuel_cost: float           # Fuel/energy carrier cost
    co2_cost: float            # CO2 emission cost
    operational_cost: float    # Hotmaps: OPEX_fix*Cap + OPEX_var*gen (combined)
    coldstart_cost: float      # Coldstart cost
    ramping_cost: float        # Ramping cost
    investment_cost: float     # Annual investment cost
    thermal_generation: float  # Total thermal generation [MWh]
    electricity_revenue: float = 0.0  # CHP electricity sales revenue
    
    @property
    def total_cost(self) -> float:
        """Total cost for this technology."""
        return (self.fuel_cost + self.co2_cost + self.operational_cost + 
                self.coldstart_cost + self.ramping_cost + self.investment_cost)
    
    @property
    def lcoh(self) -> float:
        """Levelized Cost of Heat (EUR/MWh) for this technology.
        
        Hotmaps formula: LCOH = (Total Cost - Electricity Revenue) / Thermal Generation
        """
        if self.thermal_generation > 0:
            return (self.total_cost - self.electricity_revenue) / self.thermal_generation
        return 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for display."""
        result = {
            "Fuel Costs": self.fuel_cost,
            "CO2 Costs": self.co2_cost,
            "Operational Cost": self.operational_cost,
            "Coldstart Costs": self.coldstart_cost,
            "Ramping Costs": self.ramping_cost,
            "Investment Cost": self.investment_cost,
        }
        # Add electricity revenue if present (CHP technologies)
        if self.electricity_revenue > 0:
            result["Revenue From Electricity"] = self.electricity_revenue
        result["Thermal Generation [MWh]"] = self.thermal_generation
        result["Total Cost"] = self.total_cost
        result["LCOH [EUR/MWh]"] = self.lcoh
        return result


@dataclass 
class StorageMetrics:
    """Storage performance metrics."""
    name: str
    charged: float          # Total energy charged [MWh]
    discharged: float       # Total energy discharged [MWh]
    soc_min: float          # Minimum SOC [MWh]
    soc_max: float          # Maximum SOC [MWh]
    turnover_rate: float    # Turnover = discharged / capacity
    fixed_cost: float       # Fixed O&M cost
    investment_cost: float  # Annual investment cost
    
    @property
    def total_cost(self) -> float:
        """Total cost for storage."""
        return self.fixed_cost + self.investment_cost
    
    @property
    def lcoh(self) -> float:
        """LCOH for storage = total_cost / discharged energy."""
        if self.discharged > 0:
            return self.total_cost / self.discharged
        return 0.0


class PerformanceMetrics:
    """Calculate Hotmaps-compatible performance metrics from optimization results."""
    
    def __init__(self, technologies: List[Technology], 
                 storage: Optional[Storage] = None,
                 interest_rate: float = INTEREST_RATE):
        self.technologies = {t.name: t for t in technologies}
        self.storage = storage
        self.interest_rate = interest_rate
    
    def _annuity_factor(self, lifetime: int) -> float:
        """Calculate annuity factor alpha = (q^n * r) / (q^n - 1)"""
        if lifetime <= 0:
            return 1.0
        q = 1 + self.interest_rate
        return (q ** lifetime * self.interest_rate) / (q ** lifetime - 1)
    
    def calculate_tech_costs(self, results: dict, 
                             coldstarts: Dict[str, int],
                             ramp_totals: Optional[Dict[str, float]] = None) -> Dict[str, CostBreakdown]:
        """Calculate detailed cost breakdown for each technology.
        
        Args:
            results: Optimization results with 'generation' and 'electricity_generation' keys
            coldstarts: Dict of coldstart counts per technology
            ramp_totals: Dict of total ramping [MWh] per technology (optional)
        
        Returns:
            Dict of CostBreakdown for each technology
        """
        breakdowns = {}
        elec_gen = results.get("electricity_generation", {})
        
        for name, gen_profile in results["generation"].items():
            tech = self.technologies[name]
            total_gen = float(gen_profile.sum())
            
            # Fuel cost: Hotmaps formula = sum(energy_price[h] * generation[h] / efficiency[h])
            # Handle both scalar and array-based efficiency (heat pumps have hourly COP)
            if tech.efficiency is not None:
                # Check if efficiency is array-based (heat pumps with hourly COP)
                if isinstance(tech.efficiency, np.ndarray):
                    # Hourly efficiency: fuel_input[h] = gen[h] / efficiency[h]
                    # Avoid division by zero
                    safe_efficiency = np.where(tech.efficiency > 0, tech.efficiency, 1.0)
                    fuel_input_profile = gen_profile / safe_efficiency
                    fuel_input = float(np.sum(fuel_input_profile))
                    
                    # Fuel cost with hourly prices and hourly efficiency
                    if isinstance(tech.energy_carrier_price, np.ndarray):
                        fuel_cost = float(np.sum(tech.energy_carrier_price * fuel_input_profile))
                    else:
                        fuel_cost = tech.energy_carrier_price * fuel_input
                    
                    co2_cost = tech.emission_factor * CO2_PRICE * fuel_input
                else:
                    # Scalar efficiency (standard technologies)
                    fuel_input = total_gen / tech.efficiency
                    
                    if isinstance(tech.energy_carrier_price, np.ndarray):
                        fuel_cost = float(np.sum(tech.energy_carrier_price * gen_profile)) / tech.efficiency
                    else:
                        fuel_cost = tech.energy_carrier_price * total_gen / tech.efficiency
                    
                    co2_cost = tech.emission_factor * CO2_PRICE * fuel_input
            else:
                # For technologies without efficiency, use price directly
                if isinstance(tech.energy_carrier_price, np.ndarray):
                    fuel_cost = float(np.sum(tech.energy_carrier_price * gen_profile))
                else:
                    fuel_cost = tech.energy_carrier_price * total_gen
                co2_cost = tech.emission_factor * CO2_PRICE * total_gen
            
            # Operational Cost: Hotmaps formula = OPEX_fix * Cap + OPEX_var * generation
            operational_cost = (tech.OPEX_fix * tech.installed_capacity + 
                               tech.OPEX_var * total_gen)
            
            # Coldstart cost
            cs_count = coldstarts.get(name, 0)
            coldstart_cost = tech.coldstart_cost * cs_count
            
            # Ramping cost
            ramp_cost = getattr(tech, 'ramp_cost', 0.0)
            ramp_total = ramp_totals.get(name, 0.0) if ramp_totals else 0.0
            ramping_cost = ramp_cost * ramp_total
            
            # Investment cost (annualized using technology's lifetime)
            alpha = self._annuity_factor(tech.lifetime)
            investment_cost = tech.SpCC * tech.installed_capacity * alpha
            
            # Electricity revenue for CHP technologies
            electricity_revenue = 0.0
            if name in elec_gen:
                elec_profile = elec_gen[name]
                # Revenue = sum(electricity[h] * sale_price[h])
                if isinstance(tech.sale_electricity_price, np.ndarray):
                    electricity_revenue = float(np.sum(elec_profile * tech.sale_electricity_price))
                elif tech.sale_electricity_price:
                    electricity_revenue = float(np.sum(elec_profile) * tech.sale_electricity_price)
            
            breakdowns[name] = CostBreakdown(
                name=name,
                fuel_cost=fuel_cost,
                co2_cost=co2_cost,
                operational_cost=operational_cost,
                coldstart_cost=coldstart_cost,
                ramping_cost=ramping_cost,
                investment_cost=investment_cost,
                thermal_generation=total_gen,
                electricity_revenue=electricity_revenue
            )
        
        return breakdowns
    
    def calculate_storage_metrics(self, results: dict) -> Optional[StorageMetrics]:
        """Calculate storage performance metrics."""
        if self.storage is None or "storage" not in results:
            return None
        
        flow = results["storage"]["flow"]
        soc = results["storage"]["soc"]
        
        charged = float(np.maximum(flow, 0).sum())
        discharged = float(np.maximum(-flow, 0).sum())
        
        # Fixed cost
        fixed_cost = 0.0  # Storage OPEX_fix if defined
        
        # Investment cost (annualized using storage lifetime)
        alpha = self._annuity_factor(self.storage.lifetime)
        investment_cost = self.storage.investment_cost_per_capacity * self.storage.capacity * alpha
        
        return StorageMetrics(
            name=self.storage.name,
            charged=charged,
            discharged=discharged,
            soc_min=float(soc.min()),
            soc_max=float(soc.max()),
            turnover_rate=discharged / self.storage.capacity if self.storage.capacity > 0 else 0,
            fixed_cost=fixed_cost,
            investment_cost=investment_cost
        )
    
    def calculate_system_totals(self, tech_costs: Dict[str, CostBreakdown],
                                 storage_metrics: Optional[StorageMetrics] = None,
                                 total_demand: Optional[float] = None) -> dict:
        """Calculate system-wide totals (Hotmaps style).
        
        Args:
            tech_costs: Dict of CostBreakdown per technology
            storage_metrics: Optional storage metrics
            total_demand: Total heat demand [MWh] for system LCOH calculation
        """
        
        totals = {
            "Total Fuel Costs": sum(c.fuel_cost for c in tech_costs.values()),
            "Total CO2 Costs": sum(c.co2_cost for c in tech_costs.values()),
            "Total Operational Costs": sum(c.operational_cost for c in tech_costs.values()),
            "Total Coldstart Costs": sum(c.coldstart_cost for c in tech_costs.values()),
            "Total Ramping Costs": sum(c.ramping_cost for c in tech_costs.values()),
            "Total Investment Costs": sum(c.investment_cost for c in tech_costs.values()),
            "Total Thermal Generation [MWh]": sum(c.thermal_generation for c in tech_costs.values()),
            "Total Revenue From Electricity": sum(c.electricity_revenue for c in tech_costs.values()),
        }
        
        if storage_metrics:
            totals["Storage Investment Cost"] = storage_metrics.investment_cost
            totals["Total Investment Costs"] += storage_metrics.investment_cost
        
        totals["Total System Cost"] = (
            totals["Total Fuel Costs"] + 
            totals["Total CO2 Costs"] + 
            totals["Total Operational Costs"] +
            totals["Total Coldstart Costs"] +
            totals["Total Ramping Costs"] +
            totals["Total Investment Costs"]
        )
        
        # LCOH: Hotmaps formula = (Total Cost - Total Revenue) / Total Heat Demand
        # Use total_demand if provided, otherwise use total generation
        denominator = total_demand if total_demand else totals["Total Thermal Generation [MWh]"]
        if denominator > 0:
            totals["LCOH [EUR/MWh]"] = (totals["Total System Cost"] - totals["Total Revenue From Electricity"]) / denominator
        
        return totals
    
    def print_report(self, results: dict, coldstarts: Dict[str, int],
                     ramp_totals: Optional[Dict[str, float]] = None):
        """Print Hotmaps-style performance report."""
        
        tech_costs = self.calculate_tech_costs(results, coldstarts, ramp_totals)
        storage_metrics = self.calculate_storage_metrics(results)
        totals = self.calculate_system_totals(tech_costs, storage_metrics)
        
        print("\n" + "=" * 70)
        print("PERFORMANCE METRICS (Hotmaps Compatible)")
        print("=" * 70)
        
        # Per-technology breakdown
        for name, breakdown in tech_costs.items():
            print(f"\n--- {name} ---")
            for key, value in breakdown.to_dict().items():
                print(f"  {key}: €{value:,.2f}" if "MWh" not in key else f"  {key}: {value:,.0f}")
        
        # Storage metrics
        if storage_metrics:
            print(f"\n--- {storage_metrics.name} ---")
            print(f"  Charged: {storage_metrics.charged:,.0f} MWh")
            print(f"  Discharged: {storage_metrics.discharged:,.0f} MWh")
            print(f"  SOC Range: {storage_metrics.soc_min:,.0f} - {storage_metrics.soc_max:,.0f} MWh")
            print(f"  Turnover Rate: {storage_metrics.turnover_rate:.4f}")
            print(f"  Investment Cost: €{storage_metrics.investment_cost:,.2f}")
            print(f"  LCOH [EUR/MWh]: {storage_metrics.lcoh:,.0f}")
        
        # System totals
        print("\n" + "-" * 70)
        print("SYSTEM TOTALS")
        print("-" * 70)
        for key, value in totals.items():
            if "MWh" in key:
                print(f"  {key}: {value:,.0f}")
            else:
                print(f"  {key}: €{value:,.2f}")
        
        print("=" * 70)
        
        return tech_costs, storage_metrics, totals
