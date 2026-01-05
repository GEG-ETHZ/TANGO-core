"""Operation optimization for energy system with HiGHS solver (MILP).

This implementation matches the Hotmaps Dispatch formulation exactly.
"""

import highspy
import numpy as np
from typing import List, Optional
from opt_inputs.tech_params import Technology, Storage, CO2_PRICE, GEOTHERMAL, NATURAL_GAS, HEAT_STORAGE
from pre_processors.profile_generator import Profile
from post_processors.performance_metrics import PerformanceMetrics

HOURS_PER_YEAR = 8760


class OperationOptimizer:
    """Optimize hourly operation of energy technologies (MILP with Hotmaps-compatible formulation)."""
    
    def __init__(self, demand: Profile, technologies: List[Technology], storage: Optional[Storage] = None):
        self.demand = demand
        self.technologies = technologies
        self.storage = storage
        self.n_hours = HOURS_PER_YEAR
        self.n_techs = len(technologies)
        self.model = highspy.Highs()
        self.model.setOptionValue("output_flag", True)
        self.model.setOptionValue("time_limit", 300.0)
        
        # Variable offsets (set in add_variables)
        self._gen_offset = {}      # x_th_jt: thermal generation [MW]
        self._active_offset = {}   # Active_jt: binary on/off
        self._coldstart_offset = 0 # coldstart_jt: binary startup indicator
        self._ramp_offset = 0      # ramp_jt: positive ramping [MW]
        self._flow_offset = 0      # x_load_hs_t: storage flow (±)
        self._soc_offset = 0       # store_level_hs_t: storage SOC
        self._el_offset = 0        # x_el_jt: CHP electricity generation [MW]
        
        # Identify CHP technologies
        self._chp_techs = []       # List of (idx, tech) for CHP technologies
    
    # ==================== INDEX HELPERS ====================
    def _gen_idx(self, tech_idx: int, hour: int) -> int:
        return tech_idx * self.n_hours + hour
    
    def _active_idx(self, tech_idx: int, hour: int) -> int:
        return self._active_offset_base + tech_idx * self.n_hours + hour
    
    def _coldstart_idx(self, tech_idx: int, hour: int) -> int:
        return self._coldstart_offset + tech_idx * self.n_hours + hour
    
    def _ramp_idx(self, tech_idx: int, hour: int) -> int:
        return self._ramp_offset + tech_idx * self.n_hours + hour
    
    def _flow_idx(self, hour: int) -> int:
        return self._flow_offset + hour
    
    def _soc_idx(self, hour: int) -> int:
        return self._soc_offset + hour
    
    def _el_idx(self, chp_idx: int, hour: int) -> int:
        """Index for CHP electricity generation variable."""
        return self._el_offset + chp_idx * self.n_hours + hour
    
    # ==================== VARIABLES ====================
    def add_variables(self):
        """Add all decision variables (Hotmaps compatible)."""
        
        # 1. Generation variables: x_th_jt[tech, hour] - thermal output [MW]
        for t_idx, tech in enumerate(self.technologies):
            self._gen_offset[tech.name] = t_idx * self.n_hours
            for h in range(self.n_hours):
                self.model.addVar(0, tech.max_generation)
        
        # 2. Active (on/off) binary: Active_jt[tech, hour]
        self._active_offset_base = self.n_techs * self.n_hours
        for t_idx, tech in enumerate(self.technologies):
            for h in range(self.n_hours):
                self.model.addVar(0, 1)
                self.model.changeColIntegrality(self._active_idx(t_idx, h), highspy.HighsVarType.kInteger)
        
        # 3. Coldstart binary: coldstart_jt[tech, hour] - 1 when starting up
        self._coldstart_offset = 2 * self.n_techs * self.n_hours
        for t_idx, tech in enumerate(self.technologies):
            for h in range(self.n_hours):
                self.model.addVar(0, 1)
                self.model.changeColIntegrality(self._coldstart_idx(t_idx, h), highspy.HighsVarType.kInteger)
        
        # 4. Ramp variables: ramp_jt[tech, hour] - positive ramp amount [MW]
        self._ramp_offset = 3 * self.n_techs * self.n_hours
        for t_idx, tech in enumerate(self.technologies):
            for h in range(self.n_hours):
                self.model.addVar(0, tech.max_generation)  # Max ramp = max capacity
        
        # 5. Storage variables (if storage exists)
        next_offset = 4 * self.n_techs * self.n_hours
        if self.storage:
            self._flow_offset = next_offset
            self._soc_offset = next_offset + self.n_hours
            next_offset = self._soc_offset + self.n_hours
            
            for h in range(self.n_hours):
                # x_load_hs_t: [-max_discharge, +max_charge]
                self.model.addVar(-self.storage.max_discharge_rate, self.storage.max_charge_rate)
            
            for h in range(self.n_hours):
                # store_level_hs_t: [0, capacity]
                self.model.addVar(0, self.storage.capacity)
        
        # 6. CHP electricity generation variables: x_el_jt[chp, hour]
        # Identify CHP technologies and add their electricity output variables
        self._chp_techs = [(t_idx, tech) for t_idx, tech in enumerate(self.technologies) 
                          if tech.chp_type is not None]
        
        if self._chp_techs:
            self._el_offset = next_offset
            for chp_idx, (t_idx, tech) in enumerate(self._chp_techs):
                # Calculate max electricity based on CHP type
                if tech.chp_type == "backpressure":
                    # P_el_max = P_th_max * (η_el / η_th)
                    max_el = tech.max_generation * (tech.efficiency_el / tech.efficiency)
                else:  # extraction
                    # P_el_max = Cap_th / ratioPMax
                    max_el = tech.installed_capacity / tech.ratio_pmax
                
                for h in range(self.n_hours):
                    self.model.addVar(0, max_el)
    
    # ==================== CONSTRAINTS ====================
    
    def add_demand_constraint(self):
        """Hotmaps: sum(x_th_jt) - sum(x_load_hs_t) = demand_th_t"""
        for h in range(self.n_hours):
            indices = [self._gen_idx(t, h) for t in range(self.n_techs)]
            coeffs = [1.0] * self.n_techs
            
            if self.storage:
                indices.append(self._flow_idx(h))
                coeffs.append(-1.0)  # gen - flow = demand (flow>0 = charging)
            
            self.model.addRow(self.demand[h], self.demand[h], len(indices), indices, coeffs)
    
    def add_generation_constraints(self):
        """Hotmaps generation bounds with Active binary.
        
        Max: x_th_jt <= Cap * Active_jt (or max_gen_profile[h] for Solar)
        Min: x_th_jt >= Cap * Active_jt * min_out_factor
        """
        for t_idx, tech in enumerate(self.technologies):
            min_factor = tech.min_generation / tech.max_generation if tech.max_generation > 0 else 0
            
            for h in range(self.n_hours):
                gen_i = self._gen_idx(t_idx, h)
                active_i = self._active_idx(t_idx, h)
                
                # Determine hourly max generation
                if tech.max_generation_profile is not None:
                    # Use hourly profile (e.g., Solar Thermal with radiation)
                    max_gen_h = tech.max_generation_profile[h]
                else:
                    max_gen_h = tech.max_generation
                
                # gen <= max * Active
                self.model.addRow(-highspy.kHighsInf, 0, 2, 
                                  [gen_i, active_i], [1, -max_gen_h])
                
                # gen >= min * Active (min = max * min_factor)
                min_gen = max_gen_h * min_factor
                if min_gen > 0:
                    self.model.addRow(0, highspy.kHighsInf, 2,
                                      [gen_i, active_i], [1, -min_gen])
    
    def add_soc_constraints(self):
        """Hotmaps: store_level[t] = store_level[t-1]*(1-loss) + x_load[t-1]*efficiency
        
        At t=1: store_level[1] = store_level[8760] (cyclic)
        """
        if not self.storage:
            return
        
        s = self.storage
        
        for h in range(self.n_hours):
            soc_h = self._soc_idx(h)
            
            if h == 0:
                # Cyclic: SOC[0] = SOC[8759] (no dynamics at t=1, just link first to last)
                soc_prev = self._soc_idx(self.n_hours - 1)
                self.model.addRow(0, 0, 2, [soc_h, soc_prev], [1, -1])
            else:
                # SOC[h] = SOC[h-1]*(1-loss) + flow[h-1]*eff
                soc_prev = self._soc_idx(h - 1)
                flow_prev = self._flow_idx(h - 1)
                
                # SOC[h] - (1-loss)*SOC[h-1] - eff*flow[h-1] = 0
                indices = [soc_h, soc_prev, flow_prev]
                coeffs = [1.0, -(1 - s.hourly_losses), -s.charge_efficiency]
                self.model.addRow(0, 0, 3, indices, coeffs)
    
    def add_storage_discharge_constraint(self):
        """Hotmaps: x_load_hs_t >= -store_level_hs_t (can't discharge more than SOC)"""
        if not self.storage:
            return
        
        for h in range(self.n_hours):
            flow_i = self._flow_idx(h)
            soc_i = self._soc_idx(h)
            # flow >= -soc  =>  flow + soc >= 0
            self.model.addRow(0, highspy.kHighsInf, 2, [flow_i, soc_i], [1, 1])
    
    def add_coldstart_constraints(self):
        """Hotmaps coldstart logic:
        
        At t=1: coldstart[1] = 1 (always count as startup)
        At t>1: coldstart[t] >= Active[t] - Active[t-1]
        """
        for t_idx, tech in enumerate(self.technologies):
            for h in range(self.n_hours):
                coldstart_i = self._coldstart_idx(t_idx, h)
                active_h = self._active_idx(t_idx, h)
                
                if h == 0:
                    # Hotmaps: coldstart[1] = 1 (forced startup at beginning)
                    self.model.addRow(1, 1, 1, [coldstart_i], [1])
                else:
                    active_prev = self._active_idx(t_idx, h - 1)
                    # coldstart >= Active[h] - Active[h-1]
                    self.model.addRow(0, highspy.kHighsInf, 3,
                                      [coldstart_i, active_h, active_prev], [1, -1, 1])
    
    def add_ramp_constraints(self):
        """Hotmaps ramp tracking:
        
        At t=1: ramp[1] = 0
        At t>1: ramp[t] >= x_th[t] - x_th[t-1] (only positive ramps)
        """
        for t_idx, tech in enumerate(self.technologies):
            for h in range(self.n_hours):
                ramp_i = self._ramp_idx(t_idx, h)
                gen_h = self._gen_idx(t_idx, h)
                
                if h == 0:
                    # Hotmaps: ramp[1] = 0
                    self.model.addRow(0, 0, 1, [ramp_i], [1])
                else:
                    gen_prev = self._gen_idx(t_idx, h - 1)
                    # ramp >= gen[h] - gen[h-1]
                    self.model.addRow(0, highspy.kHighsInf, 3,
                                      [ramp_i, gen_h, gen_prev], [1, -1, 1])
    
    def add_chp_constraints(self):
        """CHP heat-to-power coupling constraints.
        
        Backpressure: P_el = P_th * (η_el / η_th)  [fixed ratio]
        
        Steam Extraction: 
            P_el >= P_th / ratioPMaxFW  [minimum electricity]
            P_el <= Cap_th / ratioPMax - sv * P_th  [maximum electricity envelope]
        """
        if not self._chp_techs:
            return
        
        for chp_idx, (t_idx, tech) in enumerate(self._chp_techs):
            for h in range(self.n_hours):
                gen_i = self._gen_idx(t_idx, h)
                el_i = self._el_idx(chp_idx, h)
                
                if tech.chp_type == "backpressure":
                    # Fixed ratio: P_el = P_th * (η_el / η_th)
                    # Rearranged: P_el - (η_el/η_th) * P_th = 0
                    ratio = tech.efficiency_el / tech.efficiency
                    self.model.addRow(0, 0, 2, [el_i, gen_i], [1, -ratio])
                    
                else:  # extraction
                    # Constraint 1: P_el >= P_th / ratioPMaxFW
                    # Rearranged: P_el - (1/ratioPMaxFW) * P_th >= 0
                    min_ratio = 1.0 / tech.ratio_pmax_fw
                    self.model.addRow(0, highspy.kHighsInf, 2, 
                                      [el_i, gen_i], [1, -min_ratio])
                    
                    # Constraint 2: P_el <= Cap_th / ratioPMax - sv * P_th
                    # Where: sv = (ratioPMaxFW - ratioPMax) / (ratioPMax * ratioPMaxFW)
                    # Rearranged: P_el + sv * P_th <= Cap_th / ratioPMax
                    sv = (tech.ratio_pmax_fw - tech.ratio_pmax) / (tech.ratio_pmax * tech.ratio_pmax_fw)
                    max_el_at_zero_heat = tech.installed_capacity / tech.ratio_pmax
                    self.model.addRow(-highspy.kHighsInf, max_el_at_zero_heat, 2,
                                      [el_i, gen_i], [1, sv])
    
    # ==================== OBJECTIVE ====================
    
    def _get_efficiency(self, tech: Technology, hour: int) -> float:
        """Get efficiency for a technology at a specific hour.
        
        Handles both scalar efficiency (most technologies) and
        array-based efficiency (heat pumps with hourly COP).
        """
        if tech.efficiency is None:
            return None
        
        if isinstance(tech.efficiency, np.ndarray):
            return tech.efficiency[hour]
        
        return tech.efficiency
    
    def _get_marginal_cost(self, tech: Technology, hour: int) -> float:
        """Hotmaps mc_jt: marginal cost formula.
        
        mc = (energy_price / efficiency) + (emission * CO2_price / efficiency) + 
             excess_heat_source_price * (1 - 1/efficiency)
        
        For geothermal: multiply by 0.1 (electricity consumption ratio)
        For heat pumps: uses hourly COP as efficiency
        """
        energy_price = tech.get_energy_price(hour)
        efficiency = self._get_efficiency(tech, hour)
        
        if efficiency is not None and efficiency > 0:
            # Hotmaps formula: (price + emission*CO2) / efficiency + excess_heat * (1 - 1/eff)
            mc = (energy_price + tech.emission_factor * CO2_PRICE) / efficiency
            # Add excess heat source price term (Hotmaps: data["excess_heat_source_price"][j] * (1 - 1/n_th))
            mc += tech.excess_heat_source_price * (1 - 1/efficiency)
        else:
            # Fallback for technologies without efficiency
            mc = energy_price + tech.emission_factor * CO2_PRICE
        
        # Geothermal uses 0.1 multiplier (electricity consumption ratio)
        if "Geothermal" in tech.name or "geothermal" in tech.name:
            mc = mc * 0.1
        
        return mc
    
    def set_objective(self):
        """Hotmaps objective: minimize c_var + c_op_fix + c_op_var + c_cold + c_ramp - rev_electricity
        
        c_var = sum(mc_jt * x_th_jt)          # Marginal/fuel cost
        c_op_fix = sum(OPEX_fix * Cap)        # Fixed O&M (Hotmaps includes this!)
        c_op_var = sum(OP_var * x_th_jt)      # Variable O&M
        c_cold = sum(c_coldstart * coldstart) # Coldstart cost
        c_ramp = sum(c_ramp * ramp)           # Ramping cost
        rev_electricity = sum(P_el * sale_price)  # CHP electricity revenue (subtracted)
        """
        self.model.changeObjectiveSense(highspy.ObjSense.kMinimize)
        
        # Calculate fixed OPEX (constant term - add as objective offset)
        # Hotmaps: c_op_fix = sum([Cap_j[j] * OP_fix_j[j] for j in j])
        c_op_fix = sum(tech.OPEX_fix * tech.installed_capacity for tech in self.technologies)
        self.model.changeObjectiveOffset(c_op_fix)
        
        for t_idx, tech in enumerate(self.technologies):
            # Get ramping cost (default 0 if not specified)
            ramp_cost = getattr(tech, 'ramp_cost', 0.0)
            
            for h in range(self.n_hours):
                # Generation cost: mc + OPEX_var
                mc = self._get_marginal_cost(tech, h)
                var_cost = mc + tech.OPEX_var
                self.model.changeColCost(self._gen_idx(t_idx, h), var_cost)
                
                # Coldstart cost
                self.model.changeColCost(self._coldstart_idx(t_idx, h), tech.coldstart_cost)
                
                # Ramping cost
                self.model.changeColCost(self._ramp_idx(t_idx, h), ramp_cost)
        
        # CHP electricity revenue (negative cost = revenue)
        for chp_idx, (t_idx, tech) in enumerate(self._chp_techs):
            for h in range(self.n_hours):
                # Get sale price (can be constant or hourly profile)
                if isinstance(tech.sale_electricity_price, np.ndarray):
                    sale_price = tech.sale_electricity_price[h]
                else:
                    sale_price = tech.sale_electricity_price if tech.sale_electricity_price else 0.0
                
                # Negative cost = revenue (minimize cost = maximize revenue)
                self.model.changeColCost(self._el_idx(chp_idx, h), -sale_price)
    
    # ==================== SOLVE ====================
    
    def solve(self) -> dict:
        """Solve and return results."""
        self.model.run()
        sol = self.model.getSolution()
        info = self.model.getInfo()
        
        # Optimizer variable cost (what the solver minimizes)
        variable_cost = info.objective_function_value
        
        # Calculate fixed costs (not in objective, but needed for Hotmaps comparison)
        fixed_cost = sum(tech.OPEX_fix * tech.installed_capacity for tech in self.technologies)
        
        results = {
            "variable_cost": variable_cost,      # Optimizer cost (fuel + var OPEX + coldstart + ramp - elec revenue)
            "fixed_cost": fixed_cost,            # Fixed O&M (OPEX_fix * capacity)
            "total_cost": variable_cost + fixed_cost,  # Total operating cost
            "generation": {},
            "on_hours": {},
            "coldstarts": {},
            "electricity_generation": {},        # CHP electricity output
            "electricity_revenue": 0.0           # Total CHP electricity revenue
        }
        
        # Convert to numpy array once for fast slicing
        col_values = np.array(sol.col_value)
        
        for t_idx, tech in enumerate(self.technologies):
            # Generation: direct slice
            gen_start = t_idx * self.n_hours
            results["generation"][tech.name] = col_values[gen_start:gen_start + self.n_hours]
            
            # Count hours ON: use array operations
            active_start = self._active_offset_base + t_idx * self.n_hours
            active_vals = col_values[active_start:active_start + self.n_hours]
            results["on_hours"][tech.name] = int(np.sum(active_vals > 0.5))
            
            # Count coldstarts: use array operations
            cs_start = self._coldstart_offset + t_idx * self.n_hours
            cs_vals = col_values[cs_start:cs_start + self.n_hours]
            results["coldstarts"][tech.name] = int(np.sum(cs_vals > 0.5))
        
        # CHP electricity results
        total_elec_revenue = 0.0
        for chp_idx, (t_idx, tech) in enumerate(self._chp_techs):
            # Use direct slice
            start_idx = self._el_offset + chp_idx * self.n_hours
            elec_gen = col_values[start_idx:start_idx + self.n_hours]
            results["electricity_generation"][tech.name] = elec_gen
            
            # Calculate electricity revenue (vectorized)
            if isinstance(tech.sale_electricity_price, np.ndarray):
                total_elec_revenue += np.sum(elec_gen * tech.sale_electricity_price)
            elif tech.sale_electricity_price:
                total_elec_revenue += np.sum(elec_gen) * tech.sale_electricity_price
        
        results["electricity_revenue"] = total_elec_revenue
        
        # Storage results
        if self.storage:
            results["storage"] = {
                "flow": col_values[self._flow_offset:self._flow_offset + self.n_hours],
                "soc": col_values[self._soc_offset:self._soc_offset + self.n_hours]
            }
        
        return results

