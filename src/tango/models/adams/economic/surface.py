import numpy as np


class EconModelSurfacePipes:

    def __init__(self,
                 specs: dict,
                 surface_model: object):
        self.specs = specs
        self.PPI = self.specs.PPI
        self.X_IC, self.X_PC = self.specs.multipliers
        self.surface_model = surface_model

    def get_surface_pipe_total_length(self) -> float:
        # L_single_pair = min(self.well_spacing, self.surface_pipe_length_per_well_pair) # single inj-prod pair
        L_single_pair = self.specs.well_spacing  # single inj-prod pair
        if self.specs.well_pattern == 'DOUBLET':
            return L_single_pair
        elif '5SPOT' in self.specs.well_pattern:
            return self.specs.num_patterns * 4 * L_single_pair
        else:
            raise NotImplementedError(f"well_pattern: {self.specs.well_pattern} is not supported")

    def execute(self) -> float:
        if self.surface_model == None:
            return 0
        L = self.get_surface_pipe_total_length()
        D = self.surface_model.specs.pipe_diameter
        return self.X_PC * self.X_IC * self.PPI * (2205. * D ** 2 + 134.) * L


class EconModelSurfacePowerPlant:

    def __init__(self,
                 specs: dict,
                 surface_model: object):
        self.specs = specs
        self.PPI_PE = self.specs.PPI_PE
        self.PPI_pump = self.specs.PPI_pump
        self.PPI_TG = self.specs.PPI_TG
        self.PPI_HX = self.specs.PPI_HX
        self.X_IC, self.X_PC = self.specs.multipliers
        self.surface_model = surface_model
        self.set_constants()

    def get_turbine_cost_multiplier(self) -> float:
        if self.specs.fluid_name != 'CO2':
            return 1.0
        return 1.2

    def get_pump_material_cost_multiplier(self) -> float:
        if self.specs.fluid_name != 'H2O':
            return 2.09  # stailes steel (suitable for non-water fluids, such as CO2)
        return 1.0  # Iron (suitable for non-corrosive liquids, such as water or glycol)

    def get_tower_design_coefficient(self) -> float:
        if self.specs.fluid_name == 'H2O':
            return 1.0
        design = self.surface_model.specs.cooling_tower_design.upper()
        if design == 'CLOSED':
            if self.specs.fluid_name == 'CO2':
                return 1.2
            else:
                return 1.0
        elif design == 'OPEN':
            if self.specs.fluid_name == 'H2O':
                return 0.252
            else:
                raise ValueError(
                    f"Surface cooling tower design: {design} with fluid: {self.specs.fluid_name} is not supported")
        else:
            raise ValueError(f"Surface cooling tower design: {design} is not supported")

    def set_constants(self) -> None:
        # if self.specs.fluid_name == 'H2O': #TODO: check.
        #     return
        if self.surface_model == None:
            return

        self.surface_pipe_diameter = self.surface_model.specs.pipe_diameter
        self.surface_ambient_temperature = self.surface_model.specs.surface_temperature
        self.surface_approach_temperature = self.surface_model.specs.approach_temperature
        self.surface_temperature_range = self.surface_model.specs.temperature_range
        self.surface_cooling_tower_mode = self.surface_model.specs.cooling_mode

        # coefficients for BAC regression models
        if self.surface_cooling_tower_mode == 'WET':
            self.coeffs_cooling = [5.58e3, 0., -1.77e1, 1.96e2]
            self.coeffs_condensing = [4.08e3, -1.54e-2, -1.24e1, 0.]
        else:  # 'DRY':
            self.coeffs_cooling = [7.31e3, 0., 0., 1.23e3]
            self.coeffs_condensing = [1.91e3, 0., 0., 0.]

        self.turbine_cost_multiplier = self.get_turbine_cost_multiplier()
        self.pump_material_cost_multiplier = self.get_pump_material_cost_multiplier()
        self.tower_design_coefficient = self.get_tower_design_coefficient()

        power_plant_type = str(self.surface_model.__module__).split('.')[-1]
        if power_plant_type == 'CPG':
            self.process_surface_state = self.process_surface_state_CPG
            self.execute = self.execute_CPG
        elif power_plant_type == 'ORC':
            self.execute = self.execute_ORC
            self.process_surface_state = self.process_surface_state_ORC
        else:
            raise RuntimeError(f"Surface power plant time: {power_plant_type} is not supported.")


    def get_num_well_pairs_per_pattern(self) -> int:
        if self.specs.well_pattern == 'DOUBLET':
            return 1
        elif '5SPOT' in self.specs.well_pattern:
            return 4
        else:
            raise NotImplementedError(f"well_pattern: {self.specs.well_pattern} is not supported")

    def process_surface_state_CPG(self) -> None:

        mult = self.get_num_well_pairs_per_pattern() * self.specs.num_patterns

        self.Q_condenser_total = mult * self.state.q_condenser
        self.Q_cooler_total = mult * self.state.q_cooler
        self.Q_preheater_total = mult * self.state.q_preheater
        self.Q_boiler_total = mult * self.state.q_boiler
        self.Q_desuperheater_total = mult * self.state.q_desuperheater

        self.W_pump_total = mult * self.state.w_pump
        self.W_turbine_total = mult * self.state.w_turbine
        self.W_cooler_total = mult * self.state.w_cooler
        self.W_condenser_total = mult * self.state.w_condenser
        self.W_net_total = self.W_pump_total + self.W_turbine_total + self.W_cooler_total + self.W_condenser_total


    def process_surface_state_ORC(self) -> None:

        mult = self.get_num_well_pairs_per_pattern() * self.specs.num_patterns

        self.Q_condenser_total = mult * self.state.q_condenser
        self.Q_cooler_total = mult * self.state.q_cooler
        self.Q_preheater_total = mult * self.state.q_preheater
        self.Q_boiler_total = mult * self.state.q_boiler
        self.Q_desuperheater_total = mult * self.state.q_desuperheater
        self.Q_recuperator_total = mult * self.state.q_recuperator

        self.W_pump_ORC = mult * self.state.w_pump
        self.W_pump_prod = mult * self.state.w_downhole_pump
        self.W_turbine_total = mult * self.state.w_turbine
        self.W_net_total = mult * (self.state.w_net + self.state.w_downhole_pump)

        self.dT_range_CT = self.state.dT_range_CT
        self.dT_LMTD_preheater = self.state.dT_LMTD_preheater
        self.dT_LMTD_boiler = self.state.dT_LMTD_boiler
        self.dT_LMTD_recuperator = self.state.dT_LMTD_recuperator


    def get_turbine_generator_cost(self) -> float:
        PPI = self.PPI_TG
        S_T_fluid = self.turbine_cost_multiplier
        W_turbine = self.W_turbine_total
        return 0.67 * PPI * (S_T_fluid * 2830 * (W_turbine / 1.e3) ** 0.745 + 3680 * (W_turbine / 1.e3) ** 0.617)

    def get_pump_inj_cost(self, W_pump: float) -> float:
        PPI = self.PPI_pump
        S_pump = self.pump_material_cost_multiplier
        return PPI * S_pump * 1750 * (1.34 * -1 * (W_pump / 1e3)) ** 0.7

    def BAC_regression_model(self, coeffs: list) -> float:
        """
        Baltimore Aircoil Specific (BAC) regression model for cooling and condensing costs
        """
        a, b, c, d = coeffs
        T_ambient = self.surface_ambient_temperature
        dT_approach = self.surface_approach_temperature
        dT_range = self.surface_temperature_range
        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach + dT_range)

    def get_C_cooling(self):
        return self.BAC_regression_model(coeffs=self.coeffs_cooling)

    def get_C_condensing(self):
        return self.BAC_regression_model(coeffs=self.coeffs_condensing)

    def get_cooling_condensing_tower_cost(self) -> float:

        TDC = self.tower_design_coefficient
        PPI = self.PPI_PE

        Q_cooler = self.Q_desuperheater_total
        Q_condenser = self.Q_condenser_total
        # W_pump = self.W_pump_total
        # W_turbine = self.W_turbine_total

        C_cooling = self.get_C_cooling()  # specific cooling tower cost ($/kW)
        C_condensing = self.get_C_condensing()  # specific condensing tower cost ($/kW)

        Q_Ref_BAC = 1.0e6  # nominal heat load (=1.0 MWth)
        F_cooling = abs(Q_cooler) / (abs(Q_cooler) + abs(Q_condenser) + 1e-10)
        C_Ref_BAC = PPI * Q_Ref_BAC * TDC * (F_cooling * (C_cooling / 1e3) + (1 - F_cooling) * (C_condensing / 1e3))
        return C_Ref_BAC * (abs(Q_cooler + Q_condenser) / Q_Ref_BAC) ** 0.8

    def execute_CPG(self, state) -> float:

        if self.surface_model == None:
            return 0.

        X_SE = 1.39  # secondary equipment cost (control system, pumps, valuves, buildings, etc.)
        X_CL = 0.58  # construction labor cost
        X_CM = 0.11  # construction material cost
        X_ST = 0.00  # sales tax
        X_F = 0.04  # equipment freight

        self.state = state

        self.process_surface_state()

        C_turbine_generator = self.get_turbine_generator_cost()

        C_pump_inj = self.get_pump_inj_cost(self.W_pump_total)

        C_cooling_condensing_tower = self.get_cooling_condensing_tower_cost()

        C_plant_PEC = C_turbine_generator + C_pump_inj + C_cooling_condensing_tower  # primary equipment cost (PEC)

        C_plant_TEC = X_SE * C_plant_PEC  # total equipment cost (TEC)

        C_plant_BEC = C_plant_TEC * (1. + X_CL + X_CM + X_ST + X_F)  # bare erected cost (BEC)

        return self.X_PC * self.X_IC * C_plant_BEC  # total surface plant cost (TPC)


    def get_heat_exchanger_cost(self) -> float:
        U = 500. # W/m**2-K
        if np.isnan(self.dT_LMTD_preheater) or self.dT_LMTD_preheater == 0:
            A_preheater = 0
        else:
            A_preheater = self.Q_preheater_total / U / self.dT_LMTD_preheater
        A_boiler = self.Q_boiler_total / U / self.dT_LMTD_boiler
        A_HX = A_preheater + A_boiler
        return self.PPI_HX * (239. * A_HX + 13400.)


    def get_recuperator_cost(self) -> float:
        if np.isnan(self.dT_LMTD_recuperator) or self.dT_LMTD_recuperator == 0:
            return 0.
        else:
            return PPI_HX * (239. * Q_recuperator / U / self.dT_LMTD_recuperator + 13400.)


    def get_pump_prod_lineshaft_cost(self, W_pump) -> float:
        PPI = self.PPI_pump
        S_pump = self.pump_material_cost_multiplier
        return PPI * S_pump * 1750 * (1.34 * -1 * (W_pump / 1e3)) ** 0.7 + 5750. * (1.34 * -1. * (W_pump / 1.e3)) ** 0.2


    def execute_ORC(self, state) -> float:

        if self.surface_model == None:
            return 0.

        X_SE = 1.39  # secondary equipment cost (control system, pumps, valuves, buildings, etc.)
        X_CL = 0.58  # construction labor cost
        X_CM = 0.11  # construction material cost
        X_ST = 0.00  # sales tax
        X_F = 0.04  # equipment freight

        self.state = state

        self.process_surface_state()

        C_turbine_generator = self.get_turbine_generator_cost()

        C_pump_inj = self.get_pump_inj_cost(self.W_pump_ORC)

        C_pump_prod = self.get_pump_prod_lineshaft_cost(self.W_pump_prod)

        C_cooling_condensing_tower = self.get_cooling_condensing_tower_cost()

        C_heat_exchanger = self.get_heat_exchanger_cost()

        C_recuperator = self.get_recuperator_cost()

        C_plant_PEC = C_turbine_generator + C_pump_inj + C_pump_prod \
                      + C_cooling_condensing_tower + C_heat_exchanger + C_recuperator # primary equipment cost (PEC)

        C_plant_TEC = X_SE * C_plant_PEC  # total equipment cost (TEC)

        C_plant_BEC = C_plant_TEC * (1. + X_CL + X_CM + X_ST + X_F)  # bare erected cost (BEC)

        return self.X_PC * self.X_IC * C_plant_BEC  # total surface plant cost (TPC)