"""Operation optimization for energy system with HiGHS solver (MILP).

This implementation matches the Hotmaps Dispatch formulation exactly.
Supports both:
1. Standard efficiency-based formulation
2. Piecewise linear geothermal performance (from CSV)
3. Investment optimization (opt_mode="investment") or dispatch only (opt_mode="dispatch")
"""

import highspy
import numpy as np
import pandas as pd
import os
from typing import List, Optional, Dict
from opt_inputs.tech_params import Technology, Storage, CO2_PRICE, GEOTHERMAL, NATURAL_GAS, HEAT_STORAGE
from pre_processors.profile_generator import Profile
from post_processors.performance_metrics import PerformanceMetrics

HOURS_PER_YEAR = 8760
INTEREST_RATE = 0.05  # Default interest rate for annuity calculation


def calculate_annuity_factor(lifetime: int, interest_rate: float = INTEREST_RATE) -> float:
    """Calculate annuity factor for investment cost.
    
    annuity = ir * (1 + ir)^lifetime / ((1 + ir)^lifetime - 1)
    """
    if interest_rate <= 0:
        return 1.0 / lifetime
    r = interest_rate
    n = lifetime
    return r * (1 + r)**n / ((1 + r)**n - 1)


def load_piecewise_data(csv_path: str) -> Optional[Dict]:
    """Load piecewise linear performance data from CSV.
    
    CSV format:
        h_generation,e_consumption,e_production
        0.0,0.0,0.0
        1.0,0.08,0.02
        ...
    
    Args:
        csv_path: Path to CSV file (relative to data/ directory or absolute)
        
    Returns:
        Dictionary with breakpoints and ranges, or None if file not found
    """
    # Try multiple paths
    paths_to_try = [
        csv_path,
        os.path.join(os.path.dirname(__file__), '..', 'data', csv_path),
        os.path.join(os.path.dirname(__file__), '..', csv_path),
    ]
    
    for path in paths_to_try:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                
                # Extract columns
                h_gen = df['h_generation'].values
                e_cons = df['e_consumption'].values
                e_prod = df['e_production'].values
                
                # Sort by h_generation
                sorted_idx = np.argsort(h_gen)
                h_gen = h_gen[sorted_idx]
                e_cons = e_cons[sorted_idx]
                e_prod = e_prod[sorted_idx]
                
                print(f"[Piecewise] Loaded from {path}")
                print(f"  Breakpoints: {len(h_gen)}")
                print(f"  h_generation: [{h_gen.min():.3f}, {h_gen.max():.3f}]")
                print(f"  e_consumption: [{e_cons.min():.4f}, {e_cons.max():.4f}]")
                print(f"  e_production: [{e_prod.min():.4f}, {e_prod.max():.4f}]")
                
                return {
                    'breakpoints_h': h_gen.tolist(),
                    'breakpoints_e_cons': e_cons.tolist(),
                    'breakpoints_e_prod': e_prod.tolist(),
                    'h_min': h_gen.min(),
                    'h_max': h_gen.max(),
                    'n_segments': len(h_gen) - 1
                }
            except Exception as e:
                print(f"[Piecewise] Error loading {path}: {e}")
                return None
    
    print(f"[Piecewise] File not found: {csv_path}")
    return None


class OperationOptimizer:
    """Optimize hourly operation of energy technologies (MILP with Hotmaps-compatible formulation).
    
    Args:
        demand: Hourly demand profile
        technologies: List of available technologies
        storage: Optional heat storage
        inv_flag: If True, optimize capacity investments; if False, use fixed capacities (dispatch only)
        max_demand: Maximum demand (for investment upper bound), defaults to peak demand * 1.5
        interest_rate: Interest rate for annuity calculation (default 0.05)
    """
    
    def __init__(self, demand: Profile, technologies: List[Technology], storage: Optional[Storage] = None,
                 inv_flag: bool = False, max_demand: Optional[float] = None, interest_rate: float = INTEREST_RATE):
        self.demand = demand
        self.technologies = technologies
        self.storage = storage
        self.inv_flag = inv_flag
        self.interest_rate = interest_rate
        self.n_hours = HOURS_PER_YEAR
        self.n_techs = len(technologies)
        self.model = highspy.Highs()
        self.model.setOptionValue("output_flag", True)
        self.model.setOptionValue("time_limit", 300.0)
        
        # Max demand for investment upper bound
        self.max_demand = max_demand if max_demand else max(demand.values) * 1.5
        
        # Variable offsets (set in add_variables)
        self._gen_offset = {}      # x_th_jt: thermal generation [MW]
        self._active_offset = {}   # Active_jt: binary on/off
        self._coldstart_offset = 0 # coldstart_jt: binary startup indicator
        self._ramp_offset = 0      # ramp_jt: positive ramping [MW]
        self._flow_offset = 0      # x_load_hs_t: storage flow (±)
        self._soc_offset = 0       # store_level_hs_t: storage SOC
        self._el_offset = 0        # x_el_jt: CHP electricity generation [MW]
        self._cap_offset = 0       # Cap_j: installed capacity (investment mode)
        
        # Piecewise linear variables (for geothermal)
        self._pw_lambda_offset = 0     # Lambda weights for piecewise interpolation
        self._pw_lambda_starts = []    # Start indices for each tech's lambdas
        self._pw_segment_starts = []   # Start indices for each tech's segment binaries
        self._el_cons_offset = 0       # Electricity consumption variable
        self._el_prod_offset = 0       # Electricity production variable
        
        # Identify technology types
        self._chp_techs = []           # List of (idx, tech) for CHP technologies
        self._pw_techs = []            # List of (idx, tech, pw_data) for piecewise techs
        self._pw_data = {}             # Piecewise data per technology
    
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
    
    def _pw_lambda_idx(self, pw_idx: int, hour: int, breakpoint: int) -> int:
        """Index for piecewise lambda variable."""
        n_bp = self._pw_n_breakpoints[pw_idx]
        return self._pw_lambda_starts[pw_idx] + hour * n_bp + breakpoint
    
    def _pw_segment_idx(self, pw_idx: int, hour: int, segment: int) -> int:
        """Index for piecewise segment binary variable."""
        n_seg = self._pw_n_breakpoints[pw_idx] - 1
        return self._pw_segment_starts[pw_idx] + hour * n_seg + segment
    
    def _el_cons_idx(self, pw_idx: int, hour: int) -> int:
        """Index for electricity consumption variable."""
        return self._el_cons_offset + pw_idx * self.n_hours + hour
    
    def _el_prod_idx(self, pw_idx: int, hour: int) -> int:
        """Index for electricity production variable."""
        return self._el_prod_offset + pw_idx * self.n_hours + hour
    
    def _cap_idx(self, tech_idx: int) -> int:
        """Index for capacity variable (investment mode)."""
        return self._cap_offset + tech_idx
    
    # ==================== VARIABLES ====================
    def add_variables(self):
        """Add all decision variables (Hotmaps compatible + piecewise)."""
        
        # Identify piecewise technologies (load data)
        for t_idx, tech in enumerate(self.technologies):
            if hasattr(tech, 'piecewise_file') and tech.piecewise_file:
                pw_data = load_piecewise_data(tech.piecewise_file)
                if pw_data:
                    self._pw_techs.append((t_idx, tech, pw_data))
                    self._pw_data[t_idx] = pw_data
        
        # Store number of breakpoints per piecewise tech
        self._pw_n_breakpoints = [pw_data['n_segments'] + 1 for _, _, pw_data in self._pw_techs]
        
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
        self._chp_techs = [(t_idx, tech) for t_idx, tech in enumerate(self.technologies) 
                          if tech.chp_type is not None]
        
        if self._chp_techs:
            self._el_offset = next_offset
            for chp_idx, (t_idx, tech) in enumerate(self._chp_techs):
                if tech.chp_type == "backpressure":
                    max_el = tech.max_generation * (tech.efficiency_el / tech.efficiency)
                else:  # extraction
                    max_el = tech.installed_capacity / tech.ratio_pmax
                
                for h in range(self.n_hours):
                    self.model.addVar(0, max_el)
            next_offset = self._el_offset + len(self._chp_techs) * self.n_hours
        
        # 7. Piecewise linear variables for geothermal
        if self._pw_techs:
            # Lambda variables (weights for convex combination)
            # Store start indices for each tech's lambdas (for correct indexing with varying breakpoints)
            self._pw_lambda_starts = []
            self._pw_lambda_offset = next_offset
            for pw_idx, (t_idx, tech, pw_data) in enumerate(self._pw_techs):
                self._pw_lambda_starts.append(next_offset)
                n_breakpoints = pw_data['n_segments'] + 1
                for h in range(self.n_hours):
                    for bp in range(n_breakpoints):
                        self.model.addVar(0, 1)  # lambda in [0, 1]
                next_offset += n_breakpoints * self.n_hours
            
            # Binary segment selection variables (for SOS2 enforcement)
            self._pw_segment_starts = []
            for pw_idx, (t_idx, tech, pw_data) in enumerate(self._pw_techs):
                self._pw_segment_starts.append(next_offset)
                n_segments = pw_data['n_segments']
                for h in range(self.n_hours):
                    for seg in range(n_segments):
                        self.model.addVar(0, 1)
                        var_idx = next_offset + h * n_segments + seg
                        self.model.changeColIntegrality(var_idx, highspy.HighsVarType.kInteger)
                next_offset += n_segments * self.n_hours
            
            # Electricity consumption variables
            self._el_cons_offset = next_offset
            for pw_idx, (t_idx, tech, pw_data) in enumerate(self._pw_techs):
                max_cons = max(pw_data['breakpoints_e_cons'])
                for h in range(self.n_hours):
                    self.model.addVar(0, max_cons)
            next_offset += len(self._pw_techs) * self.n_hours
            
            # Electricity production variables
            self._el_prod_offset = next_offset
            for pw_idx, (t_idx, tech, pw_data) in enumerate(self._pw_techs):
                max_prod = max(pw_data['breakpoints_e_prod'])
                for h in range(self.n_hours):
                    self.model.addVar(0, max_prod)
            next_offset += len(self._pw_techs) * self.n_hours
        
        # 8. Capacity variables (investment mode only)
        if self.inv_flag:
            self._cap_offset = next_offset
            for t_idx, tech in enumerate(self.technologies):
                # Cap_j: [installed_capacity, max_demand]
                # Lower bound = existing capacity (can't remove)
                # Upper bound = max demand (can invest up to this)
                lb = tech.installed_capacity
                ub = self.max_demand
                self.model.addVar(lb, ub)
            next_offset += self.n_techs
            print(f"[Investment Mode] Added {self.n_techs} capacity variables")
    
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
        
        In dispatch mode: gen <= max_generation * Active
        In investment mode: gen <= Cap_j * Active (with Cap_j as variable)
        """
        for t_idx, tech in enumerate(self.technologies):
            min_factor = tech.min_generation / tech.max_generation if tech.max_generation > 0 else 0
            
            for h in range(self.n_hours):
                gen_i = self._gen_idx(t_idx, h)
                active_i = self._active_idx(t_idx, h)
                
                # Determine hourly max generation
                if tech.max_generation_profile is not None:
                    max_gen_h = tech.max_generation_profile[h]
                else:
                    max_gen_h = tech.max_generation
                
                if self.inv_flag:
                    # Investment mode: gen <= Cap_j * Active
                    # Linearized as: gen - M * Active <= 0, where M is big-M
                    # Using: gen <= Cap_j and gen <= M * Active
                    cap_i = self._cap_idx(t_idx)
                    
                    # For radiation-dependent technologies, also apply hourly limit
                    if tech.max_generation_profile is not None:
                        # gen <= profile_ratio * Cap_j, where profile_ratio = max_gen_h / installed_cap
                        # This scales with the invested capacity
                        if tech.installed_capacity > 0:
                            profile_ratio = max_gen_h / tech.installed_capacity
                        else:
                            # For greenfield, use ratio to max possible capacity
                            profile_ratio = max_gen_h / tech.max_generation if tech.max_generation > 0 else 0
                        
                        # gen - profile_ratio * Cap_j <= 0
                        self.model.addRow(-highspy.kHighsInf, 0, 2,
                                          [gen_i, cap_i], [1, -profile_ratio])
                    else:
                        # gen <= Cap_j (capacity limit)
                        self.model.addRow(-highspy.kHighsInf, 0, 2,
                                          [gen_i, cap_i], [1, -1])
                    
                    # gen <= max_demand * Active (big-M for on/off)
                    self.model.addRow(-highspy.kHighsInf, 0, 2,
                                      [gen_i, active_i], [1, -self.max_demand])
                    
                    # gen >= min_factor * Cap_j * Active (minimum when on)
                    # Approximated as: gen >= min_factor * installed_capacity * Active
                    min_gen = tech.installed_capacity * min_factor
                    if min_gen > 0:
                        self.model.addRow(0, highspy.kHighsInf, 2,
                                          [gen_i, active_i], [1, -min_gen])
                else:
                    # Dispatch mode: gen <= max_generation * Active
                    self.model.addRow(-highspy.kHighsInf, 0, 2, 
                                      [gen_i, active_i], [1, -max_gen_h])
                    
                    # gen >= min * Active
                    min_gen = max_gen_h * min_factor
                    if min_gen > 0:
                        self.model.addRow(0, highspy.kHighsInf, 2,
                                          [gen_i, active_i], [1, -min_gen])
    
    def add_piecewise_constraints(self):
        """Add piecewise linear interpolation constraints for geothermal.
        
        Uses binary segment selection for SOS2 enforcement.
        
        For each piecewise technology:
        1. sum(lambda) = 1 (convex combination)
        2. x_th = sum(lambda * h_breakpoints)
        3. e_cons = sum(lambda * e_cons_breakpoints)
        4. e_prod = sum(lambda * e_prod_breakpoints)
        5. SOS2 via binary: at most 2 adjacent lambdas can be non-zero
        """
        if not self._pw_techs:
            return
        
        for pw_idx, (t_idx, tech, pw_data) in enumerate(self._pw_techs):
            n_bp = pw_data['n_segments'] + 1
            n_seg = pw_data['n_segments']
            h_bp = pw_data['breakpoints_h']
            e_cons_bp = pw_data['breakpoints_e_cons']
            e_prod_bp = pw_data['breakpoints_e_prod']
            
            for h in range(self.n_hours):
                gen_i = self._gen_idx(t_idx, h)
                e_cons_i = self._el_cons_idx(pw_idx, h)
                e_prod_i = self._el_prod_idx(pw_idx, h)
                
                # Constraint 1: sum(lambda) = 1
                lambda_indices = [self._pw_lambda_idx(pw_idx, h, bp) for bp in range(n_bp)]
                self.model.addRow(1, 1, n_bp, lambda_indices, [1.0] * n_bp)
                
                # Constraint 2: x_th = sum(lambda * h_breakpoints)
                indices = [gen_i] + lambda_indices
                coeffs = [1.0] + [-hb for hb in h_bp]
                self.model.addRow(0, 0, len(indices), indices, coeffs)
                
                # Constraint 3: e_cons = sum(lambda * e_cons_breakpoints)
                indices = [e_cons_i] + lambda_indices
                coeffs = [1.0] + [-ec for ec in e_cons_bp]
                self.model.addRow(0, 0, len(indices), indices, coeffs)
                
                # Constraint 4: e_prod = sum(lambda * e_prod_breakpoints)
                indices = [e_prod_i] + lambda_indices
                coeffs = [1.0] + [-ep for ep in e_prod_bp]
                self.model.addRow(0, 0, len(indices), indices, coeffs)
                
                # Constraint 5: SOS2 via binary segment selection
                # sum(segment_binary) = 1 (exactly one segment active)
                seg_indices = [self._pw_segment_idx(pw_idx, h, s) for s in range(n_seg)]
                self.model.addRow(1, 1, n_seg, seg_indices, [1.0] * n_seg)
                
                # lambda[i] <= segment[i-1] + segment[i]
                for bp in range(n_bp):
                    lambda_i = self._pw_lambda_idx(pw_idx, h, bp)
                    if bp == 0:
                        seg_i = self._pw_segment_idx(pw_idx, h, 0)
                        self.model.addRow(-highspy.kHighsInf, 0, 2,
                                          [lambda_i, seg_i], [1, -1])
                    elif bp == n_bp - 1:
                        seg_i = self._pw_segment_idx(pw_idx, h, n_seg - 1)
                        self.model.addRow(-highspy.kHighsInf, 0, 2,
                                          [lambda_i, seg_i], [1, -1])
                    else:
                        seg_prev = self._pw_segment_idx(pw_idx, h, bp - 1)
                        seg_curr = self._pw_segment_idx(pw_idx, h, bp)
                        self.model.addRow(-highspy.kHighsInf, 0, 3,
                                          [lambda_i, seg_prev, seg_curr], [1, -1, -1])
    
    def add_soc_constraints(self):
        """Hotmaps: store_level[t] = store_level[t-1]*(1-loss) + x_load[t-1]*efficiency"""
        if not self.storage:
            return
        
        s = self.storage
        
        for h in range(self.n_hours):
            soc_h = self._soc_idx(h)
            
            if h == 0:
                soc_prev = self._soc_idx(self.n_hours - 1)
                self.model.addRow(0, 0, 2, [soc_h, soc_prev], [1, -1])
            else:
                soc_prev = self._soc_idx(h - 1)
                flow_prev = self._flow_idx(h - 1)
                indices = [soc_h, soc_prev, flow_prev]
                coeffs = [1.0, -(1 - s.hourly_losses), -s.charge_efficiency]
                self.model.addRow(0, 0, 3, indices, coeffs)
    
    def add_storage_discharge_constraint(self):
        """Hotmaps: x_load_hs_t >= -store_level_hs_t"""
        if not self.storage:
            return
        
        for h in range(self.n_hours):
            flow_i = self._flow_idx(h)
            soc_i = self._soc_idx(h)
            self.model.addRow(0, highspy.kHighsInf, 2, [flow_i, soc_i], [1, 1])
    
    def add_coldstart_constraints(self):
        """Hotmaps coldstart logic."""
        for t_idx, tech in enumerate(self.technologies):
            for h in range(self.n_hours):
                coldstart_i = self._coldstart_idx(t_idx, h)
                active_h = self._active_idx(t_idx, h)
                
                if h == 0:
                    self.model.addRow(1, 1, 1, [coldstart_i], [1])
                else:
                    active_prev = self._active_idx(t_idx, h - 1)
                    self.model.addRow(0, highspy.kHighsInf, 3,
                                      [coldstart_i, active_h, active_prev], [1, -1, 1])
    
    def add_ramp_constraints(self):
        """Hotmaps ramp tracking."""
        for t_idx, tech in enumerate(self.technologies):
            for h in range(self.n_hours):
                ramp_i = self._ramp_idx(t_idx, h)
                gen_h = self._gen_idx(t_idx, h)
                
                if h == 0:
                    self.model.addRow(0, 0, 1, [ramp_i], [1])
                else:
                    gen_prev = self._gen_idx(t_idx, h - 1)
                    self.model.addRow(0, highspy.kHighsInf, 3,
                                      [ramp_i, gen_h, gen_prev], [1, -1, 1])
    
    def add_chp_constraints(self):
        """CHP heat-to-power coupling constraints.
        
        Matches HotmapsDispatch simpel_dispatch.py exactly:
        - chp_generation_restriction1: x_el <= Cap/ratioPMax - sv * x_th
        - chp_generation_restriction3: x_el >= x_th / ratioPMaxFW
        """
        if not self._chp_techs:
            return
        
        for chp_idx, (t_idx, tech) in enumerate(self._chp_techs):
            # Get capacity variable index if in investment mode
            cap_i = self._cap_idx(t_idx) if self.inv_flag else None
            
            for h in range(self.n_hours):
                gen_i = self._gen_idx(t_idx, h)
                el_i = self._el_idx(chp_idx, h)
                
                if tech.chp_type == "backpressure":
                    # Backpressure: fixed ratio x_el = x_th * (η_el / η_th)
                    ratio = tech.efficiency_el / tech.efficiency
                    self.model.addRow(0, 0, 2, [el_i, gen_i], [1, -ratio])
                else:  # extraction
                    # Extraction CHP: flexible ratio with bounds (HotmapsDispatch formulation)
                    sv = (tech.ratio_pmax_fw - tech.ratio_pmax) / (tech.ratio_pmax * tech.ratio_pmax_fw)
                    
                    # Upper bound: x_el <= Cap/ratioPMax - sv * x_th
                    if self.inv_flag and cap_i is not None:
                        # x_el + sv * x_th - Cap / ratio_pmax <= 0
                        coef_cap = -1.0 / tech.ratio_pmax
                        self.model.addRow(-highspy.kHighsInf, 0, 3,
                                          [el_i, gen_i, cap_i], [1, sv, coef_cap])
                    else:
                        max_el_at_zero_heat = tech.installed_capacity / tech.ratio_pmax
                        self.model.addRow(-highspy.kHighsInf, max_el_at_zero_heat, 2,
                                          [el_i, gen_i], [1, sv])
                    
                    # Lower bound: x_el >= x_th / ratioPMaxFW
                    min_ratio = 1.0 / tech.ratio_pmax_fw
                    self.model.addRow(0, highspy.kHighsInf, 2, 
                                      [el_i, gen_i], [1, -min_ratio])
    
    # ==================== OBJECTIVE ====================
    
    def _get_efficiency(self, tech: Technology, hour: int) -> float:
        """Get efficiency for a technology at a specific hour."""
        if tech.efficiency is None:
            return None
        
        if isinstance(tech.efficiency, np.ndarray):
            return tech.efficiency[hour]
        
        return tech.efficiency
    
    def _is_piecewise_tech(self, tech_idx: int) -> bool:
        """Check if technology uses piecewise linear formulation."""
        return tech_idx in self._pw_data
    
    def _get_pw_idx(self, tech_idx: int) -> int:
        """Get piecewise index for a technology."""
        for pw_idx, (t_idx, _, _) in enumerate(self._pw_techs):
            if t_idx == tech_idx:
                return pw_idx
        return -1
    
    def _get_marginal_cost(self, tech: Technology, hour: int) -> float:
        """Hotmaps mc_jt: marginal cost formula.
        
        Standard: mc = (energy_price + emission * CO2_price) / efficiency
        Piecewise: Cost is based on e_consumption variable (set in objective separately)
        """
        energy_price = tech.get_energy_price(hour)
        efficiency = self._get_efficiency(tech, hour)
        
        if efficiency is not None and efficiency > 0:
            mc = (energy_price + tech.emission_factor * CO2_PRICE) / efficiency
            mc += tech.excess_heat_source_price * (1 - 1/efficiency)
        else:
            mc = energy_price + tech.emission_factor * CO2_PRICE
        
        # For standard geothermal (not piecewise), apply 0.1 multiplier
        if ("Geothermal" in tech.name or "geothermal" in tech.name):
            if not hasattr(tech, 'piecewise_file') or not tech.piecewise_file:
                mc = mc * 0.1
        
        return mc
    
    def set_objective(self):
        """Hotmaps objective with piecewise support and investment costs.
        
        For piecewise techs:
        - Cost based on e_consumption * electricity_price
        - Revenue from e_production * sale_price
        
        For investment mode:
        - Adds annualized investment cost: (Cap_j - installed_capacity) * SpCC * annuity_factor
        """
        self.model.changeObjectiveSense(highspy.ObjSense.kMinimize)
        
        # Fixed OPEX (in investment mode, this depends on Cap_j variable)
        if self.inv_flag:
            # Fixed OPEX will be added as variable cost on Cap_j
            c_op_fix = 0  # Will be added via Cap_j cost coefficient
        else:
            c_op_fix = sum(tech.OPEX_fix * tech.installed_capacity for tech in self.technologies)
        self.model.changeObjectiveOffset(c_op_fix)
        
        # Investment costs (investment mode only)
        if self.inv_flag:
            for t_idx, tech in enumerate(self.technologies):
                cap_i = self._cap_idx(t_idx)
                annuity = calculate_annuity_factor(tech.lifetime, self.interest_rate)
                
                # Cost = (Cap_j - installed_capacity) * SpCC * annuity + Cap_j * OPEX_fix
                # = Cap_j * (SpCC * annuity + OPEX_fix) - installed_capacity * SpCC * annuity
                # The constant term goes to offset, variable coefficient goes to Cap_j
                inv_cost_per_mw = tech.SpCC * annuity + tech.OPEX_fix
                self.model.changeColCost(cap_i, inv_cost_per_mw)
                
                # Subtract the existing capacity investment (sunk cost) from objective offset
                # This makes new investment = (Cap_j - installed) * SpCC * annuity
                sunk_cost = tech.installed_capacity * tech.SpCC * annuity
                current_offset = self.model.getInfo().objective_offset if hasattr(self.model.getInfo(), 'objective_offset') else 0
                # Note: We don't subtract sunk cost as in Hotmaps, installed_capacity is the minimum
                
            print(f"[Investment Mode] Added investment costs to objective")
        
        # Build set of piecewise tech indices for quick lookup
        pw_tech_indices = {t_idx for t_idx, _, _ in self._pw_techs}
        
        for t_idx, tech in enumerate(self.technologies):
            ramp_cost = getattr(tech, 'ramp_cost', 0.0)
            
            for h in range(self.n_hours):
                # Coldstart and ramp costs (same for all)
                self.model.changeColCost(self._coldstart_idx(t_idx, h), tech.coldstart_cost)
                self.model.changeColCost(self._ramp_idx(t_idx, h), ramp_cost)
                
                if t_idx in pw_tech_indices:
                    # Piecewise: only OPEX_var on generation (fuel cost on e_consumption)
                    self.model.changeColCost(self._gen_idx(t_idx, h), tech.OPEX_var)
                else:
                    # Standard: mc + OPEX_var on generation
                    mc = self._get_marginal_cost(tech, h)
                    var_cost = mc + tech.OPEX_var
                    self.model.changeColCost(self._gen_idx(t_idx, h), var_cost)
        
        # Piecewise electricity consumption cost
        for pw_idx, (t_idx, tech, pw_data) in enumerate(self._pw_techs):
            for h in range(self.n_hours):
                # e_consumption cost = electricity_price + emission * CO2_price
                energy_price = tech.get_energy_price(h)
                e_cons_cost = energy_price + tech.emission_factor * CO2_PRICE
                self.model.changeColCost(self._el_cons_idx(pw_idx, h), e_cons_cost)
        
        # Piecewise electricity production revenue
        for pw_idx, (t_idx, tech, pw_data) in enumerate(self._pw_techs):
            if hasattr(tech, 'sale_electricity_price') and tech.sale_electricity_price is not None:
                for h in range(self.n_hours):
                    if isinstance(tech.sale_electricity_price, np.ndarray):
                        sale_price = tech.sale_electricity_price[h]
                    else:
                        sale_price = tech.sale_electricity_price
                    
                    # Negative cost = revenue
                    self.model.changeColCost(self._el_prod_idx(pw_idx, h), -sale_price)
        
        # CHP electricity revenue (matches HotmapsDispatch: rev_gen_electricity)
        # HotmapsDispatch: pure revenue, fuel cost charged on thermal output only
        for chp_idx, (t_idx, tech) in enumerate(self._chp_techs):
            for h in range(self.n_hours):
                if isinstance(tech.sale_electricity_price, np.ndarray):
                    sale_price = tech.sale_electricity_price[h]
                else:
                    sale_price = tech.sale_electricity_price if tech.sale_electricity_price else 0.0
                
                # Negative cost = revenue (matches HotmapsDispatch exactly)
                self.model.changeColCost(self._el_idx(chp_idx, h), -sale_price)
    
    # ==================== SOLVE ====================
    
    def solve(self) -> dict:
        """Solve and return results."""
        self.model.run()
        sol = self.model.getSolution()
        info = self.model.getInfo()
        
        col_values = np.array(sol.col_value)
        
        # Calculate costs
        objective_value = info.objective_function_value
        
        if self.inv_flag:
            # In investment mode, objective includes investment + fixed OPEX + variable costs
            # Extract capacity values
            optimized_capacities = {}
            investment_costs = {}
            total_investment_cost = 0.0
            total_fixed_opex = 0.0
            
            for t_idx, tech in enumerate(self.technologies):
                cap_i = self._cap_idx(t_idx)
                opt_cap = col_values[cap_i]
                optimized_capacities[tech.name] = opt_cap
                
                # Investment for new capacity
                new_cap = max(0, opt_cap - tech.installed_capacity)
                annuity = calculate_annuity_factor(tech.lifetime, self.interest_rate)
                inv_cost = new_cap * tech.SpCC * annuity
                investment_costs[tech.name] = inv_cost
                total_investment_cost += inv_cost
                
                # Fixed OPEX on total capacity
                total_fixed_opex += opt_cap * tech.OPEX_fix
            
            variable_cost = objective_value - total_investment_cost - total_fixed_opex
            fixed_cost = total_fixed_opex
        else:
            variable_cost = objective_value
            fixed_cost = sum(tech.OPEX_fix * tech.installed_capacity for tech in self.technologies)
            optimized_capacities = {tech.name: tech.installed_capacity for tech in self.technologies}
            investment_costs = {tech.name: 0.0 for tech in self.technologies}
            total_investment_cost = 0.0
        
        results = {
            "opt_mode": "investment" if self.inv_flag else "dispatch",
            "objective_value": objective_value,
            "variable_cost": variable_cost,
            "fixed_cost": fixed_cost,
            "investment_cost": total_investment_cost,
            "total_cost": objective_value,
            "optimized_capacities": optimized_capacities,
            "investment_costs": investment_costs,
            "generation": {},
            "on_hours": {},
            "coldstarts": {},
            "electricity_generation": {},
            "electricity_consumption": {},
            "electricity_production": {},
            "electricity_revenue": 0.0
        }
        
        for t_idx, tech in enumerate(self.technologies):
            gen_start = t_idx * self.n_hours
            results["generation"][tech.name] = col_values[gen_start:gen_start + self.n_hours]
            
            active_start = self._active_offset_base + t_idx * self.n_hours
            active_vals = col_values[active_start:active_start + self.n_hours]
            results["on_hours"][tech.name] = int(np.sum(active_vals > 0.5))
            
            cs_start = self._coldstart_offset + t_idx * self.n_hours
            cs_vals = col_values[cs_start:cs_start + self.n_hours]
            results["coldstarts"][tech.name] = int(np.sum(cs_vals > 0.5))
        
        # CHP electricity results
        total_elec_revenue = 0.0
        for chp_idx, (t_idx, tech) in enumerate(self._chp_techs):
            start_idx = self._el_offset + chp_idx * self.n_hours
            elec_gen = col_values[start_idx:start_idx + self.n_hours]
            results["electricity_generation"][tech.name] = elec_gen
            
            if isinstance(tech.sale_electricity_price, np.ndarray):
                total_elec_revenue += np.sum(elec_gen * tech.sale_electricity_price)
            elif tech.sale_electricity_price:
                total_elec_revenue += np.sum(elec_gen) * tech.sale_electricity_price
        
        # Piecewise electricity results
        for pw_idx, (t_idx, tech, pw_data) in enumerate(self._pw_techs):
            # Electricity consumption
            e_cons_start = self._el_cons_idx(pw_idx, 0)
            e_cons = col_values[e_cons_start:e_cons_start + self.n_hours]
            results["electricity_consumption"][tech.name] = e_cons
            
            # Electricity production
            e_prod_start = self._el_prod_idx(pw_idx, 0)
            e_prod = col_values[e_prod_start:e_prod_start + self.n_hours]
            results["electricity_production"][tech.name] = e_prod
            results["electricity_generation"][tech.name] = e_prod  # Also add to generation
            
            # Calculate revenue from production
            if hasattr(tech, 'sale_electricity_price') and tech.sale_electricity_price is not None:
                if isinstance(tech.sale_electricity_price, np.ndarray):
                    total_elec_revenue += np.sum(e_prod * tech.sale_electricity_price)
                else:
                    total_elec_revenue += np.sum(e_prod) * tech.sale_electricity_price
        
        results["electricity_revenue"] = total_elec_revenue
        
        # Storage results
        if self.storage:
            results["storage"] = {
                "flow": col_values[self._flow_offset:self._flow_offset + self.n_hours],
                "soc": col_values[self._soc_offset:self._soc_offset + self.n_hours]
            }
        
        return results
