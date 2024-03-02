import numpy as np


class EconUnitSurfacePipes:

    def __init__(self,
                 specs: dict,
                 unit: object):
        self._specs = specs
        self._PPI = self._specs.PPI
        self._X_IC, self._X_PC = self._specs.multipliers
        self._surface_unit = unit

    def _compute_surface_pipe_total_length(self) -> float:
        L_single_pair = self._specs.well_spacing  # single inj-prod pair
        if self._specs.well_pattern in ['DOUBLET', 'AGS']:
            return L_single_pair
        elif '5SPOT' in self._specs.well_pattern:
            return self._specs.num_patterns * 4 * L_single_pair
        else:
            raise ValueErrortedError(f"well_pattern: {self._specs.well_pattern} is not supported")

    def execute(self) -> float:
        if self._surface_unit == None:
            return 0
        L = self._compute_surface_pipe_total_length()
        D = self._surface_unit.specs.pipe_diameter
        return self._X_PC * self._X_IC * self._PPI * (2205. * D ** 2 + 134.) * L


class EconUnitSurfacePowerPlant:

    def __init__(self,
                 specs: dict,
                 unit: object):
        self._specs = specs
        self._PPI_PE = self._specs.PPI_PE
        self._PPI_pump = self._specs.PPI_pump
        self._PPI_TG = self._specs.PPI_TG
        self._PPI_HX = self._specs.PPI_HX
        self._X_IC, self._X_PC = self._specs.multipliers
        self._surface_unit = unit
        self._initialize_constants()
        self._initialize_units()
        print('execute', self.execute)


    def _get_turbine_cost_multiplier(self) -> float:
        return 1.0 if self._specs.fluid_name != 'CO2' else 1.2


    def _get_pump_material_cost_multiplier(self) -> float:
        """
            stailes steel for non-water fluids, such as CO2 (=2.09)
            otherwise Iron (suitable for non-corrosive liquids, such as water or glycol) (=1.0)
        """
        return 2.09 if self._specs.fluid_name != 'H2O' else 1.0


    def _get_tower_design_coefficient(self) -> float:
        if self._specs.fluid_name == 'H2O':
            return 1.0
        design = self._surface_unit.specs.cooling_tower_design.upper()
        if design == 'CLOSED':
            if self._specs.fluid_name == 'CO2':
                return 1.2
            else:
                return 1.0
        elif design == 'OPEN':
            if self._specs.fluid_name == 'H2O':
                return 0.252
            else:
                raise ValueError(
                    f"Surface cooling tower design: {design} with fluid: {self._specs.fluid_name} is not supported")
        else:
            raise ValueError(f"Surface cooling tower design: {design} is not supported")


    def _initialize_constants(self) -> None:
        if self._surface_unit == None:
            return

        self._surface_pipe_diameter = self._surface_unit.specs.pipe_diameter
        self._surface_ambient_temperature = self._surface_unit.specs.surface_temperature
        self._surface_approach_temperature = self._surface_unit.specs.approach_temperature
        self._surface_temperature_range = self._surface_unit.specs.temperature_range
        self._surface_cooling_tower_mode = self._surface_unit.specs.cooling_mode

        # coefficients for BAC regression units
        if self._surface_cooling_tower_mode == 'WET':
            self._coeffs_cooling = [5.58e3, 0., -1.77e1, 1.96e2]
            self._coeffs_condensing = [4.08e3, -1.54e-2, -1.24e1, 0.]
        else:  # 'DRY':
            self._coeffs_cooling = [7.31e3, 0., 0., 1.23e3]
            self._coeffs_condensing = [1.91e3, 0., 0., 0.]

        self._turbine_cost_multiplier = self._get_turbine_cost_multiplier()
        self._pump_material_cost_multiplier = self._get_pump_material_cost_multiplier()
        self._tower_design_coefficient = self._get_tower_design_coefficient()


    def _initialize_units(self) -> None:
        if self._surface_unit == None:
            return
        power_plant_type = str(self._surface_unit.__module__).split('.')[-1]
        if power_plant_type == 'CPG':
            self._process_surface_state = self._process_surface_state_CPG
            self.execute = self._execute_CPG
        elif power_plant_type == 'ORC':
            self.execute = self._execute_ORC
            self._process_surface_state = self._process_surface_state_ORC
        elif power_plant_type == 'tespy_ORC':
            self.execute = self._execute_ORC_tespy
            self._process_surface_state = self._process_surface_state_ORC
        elif power_plant_type == 'tespy_SF':
            self.execute = self._execute_DF_tespy
            self._process_surface_state = self._process_surface_state_DF_tespy
        elif power_plant_type == 'tespy_DF':
            self.execute = self._execute_DF_tespy
            self._process_surface_state = self._process_surface_state_DF_tespy
        else:
            raise ValueError(f"Surface power plant time: {power_plant_type} is not supported.")


    def _process_surface_state_CPG(self) -> None:

        mult = self._specs.num_patterns

        self._Q_condenser_total = mult * self._state.q_condenser
        self._Q_cooler_total = mult * self._state.q_cooler
        self._Q_preheater_total = mult * self._state.q_preheater
        self._Q_boiler_total = mult * self._state.q_boiler
        self._Q_desuperheater_total = mult * self._state.q_desuperheater

        self._W_pump_total = mult * self._state.w_pump
        self._W_turbine_total = mult * self._state.w_turbine
        self._W_cooler_total = mult * self._state.w_cooler
        self._W_condenser_total = mult * self._state.w_condenser
        self._W_net_total = self._W_pump_total + self._W_turbine_total + self._W_cooler_total + self._W_condenser_total

    def _process_surface_state_ORC_tespy(self) -> None:

        mult = self._specs.num_patterns

        self._Q_condenser_total = mult * self._state.q_condenser
        self._Q_cooler_total = mult * self._state.q_cooler
        self._Q_preheater_total = mult * self._state.q_preheater
        self._Q_boiler_total = mult * self._state.q_boiler
        self._Q_desuperheater_total = mult * self._state.q_desuperheater

        self._W_pump_total = mult * self._state.w_pump
        self._W_turbine_total = mult * self._state.w_turbine
        self._W_cooler_total = mult * self._state.w_cooler
        self._W_condenser_total = mult * self._state.w_condenser
        self._W_net_total = self._W_pump_total + self._W_turbine_total + self._W_cooler_total + self._W_condenser_total

    def _process_surface_state_DF_tespy(self) -> None:

        mult = self._specs.num_patterns

        self._Q_condenser_total = mult * self._state.q_condenser
        # self._Q_cooler_total = mult * self._state.q_cooler
        # self._Q_preheater_total = mult * self._state.q_preheater
        # self._Q_boiler_total = mult * self._state.q_boiler
        # self._Q_desuperheater_total = mult * self._state.q_desuperheater

        self._W_pump_total = mult * self._state.w_pump
        self._W_turbine_total = mult * self._state.w_turbine
        # self._W_cooler_total = mult * self._state.w_cooler
        self._W_condenser_total = mult * self._state.w_condenser
        self._W_net_total = self._W_pump_total + self._W_turbine_total + self._W_condenser_total
        self._W_net_total = self._W_pump_total + self._W_turbine_total + self._W_condenser_total



    def _process_surface_state_ORC(self) -> None:

        mult = self._specs.num_patterns

        self._Q_condenser_total = mult * self._state.q_condenser
        self._Q_cooler_total = mult * self._state.q_cooler
        self._Q_preheater_total = mult * self._state.q_preheater
        self._Q_boiler_total = mult * self._state.q_boiler
        self._Q_desuperheater_total = mult * self._state.q_desuperheater
        self._Q_recuperator_total = mult * self._state.q_recuperator

        self._W_pump_ORC = mult * self._state.w_pump
        self._W_pump_prod = mult * self._state.w_downhole_pump
        self._W_turbine_total = mult * self._state.w_turbine
        self._W_net_total = mult * (self._state.w_net + self._state.w_downhole_pump)

        self._dT_range_CT = self._state.dT_range_CT
        self._dT_LMTD_preheater = self._state.dT_LMTD_preheater
        self._dT_LMTD_boiler = self._state.dT_LMTD_boiler
        self._dT_LMTD_recuperator = self._state.dT_LMTD_recuperator


    def _compute_turbine_generator_cost(self) -> float:
        PPI = self._PPI_TG
        S_T_fluid = self._turbine_cost_multiplier
        W_turbine = self._W_turbine_total
        print('W_turbine', W_turbine)
        print('t_return', 0.67 * PPI * (S_T_fluid * 2830 * (W_turbine / 1.e3) ** 0.745 + 3680 * (W_turbine / 1.e3) ** 0.617))
        return 0.67 * PPI * (S_T_fluid * 2830 * (W_turbine / 1.e3) ** 0.745 + 3680 * (W_turbine / 1.e3) ** 0.617)


    def _compute_pump_inj_cost(self, W_pump: float) -> float:
        PPI = self._PPI_pump
        S_pump = self._pump_material_cost_multiplier
        return PPI * S_pump * 1750 * (1.34 * -1 * (W_pump / 1e3)) ** 0.7


    def _BAC_regression_model(self, coeffs: list) -> float:
        """
        Baltimore Aircoil Specific (BAC) regression model for cooling and condensing costs
        """
        a, b, c, d = coeffs
        T_ambient = self._surface_ambient_temperature
        dT_approach = self._surface_approach_temperature
        dT_range = self._surface_temperature_range
        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach + dT_range)


    def _get_C_cooling(self):
        return self._BAC_regression_model(coeffs=self._coeffs_cooling)


    def _get_C_condensing(self):
        return self._BAC_regression_model(coeffs=self._coeffs_condensing)


    def _compute_cooling_condensing_tower_cost(self) -> float:

        TDC = self._tower_design_coefficient
        PPI = self._PPI_PE

        Q_cooler = self._Q_desuperheater_total
        Q_condenser = self._Q_condenser_total

        C_cooling = self._get_C_cooling()  # specific cooling tower cost ($/kW)
        C_condensing = self._get_C_condensing()  # specific condensing tower cost ($/kW)

        Q_Ref_BAC = 1.0e6  # nominal heat load (=1.0 MWth)
        F_cooling = abs(Q_cooler) / (abs(Q_cooler) + abs(Q_condenser) + 1e-10)
        C_Ref_BAC = PPI * Q_Ref_BAC * TDC * (F_cooling * (C_cooling / 1e3) + (1 - F_cooling) * (C_condensing / 1e3))
        return C_Ref_BAC * (abs(Q_cooler + Q_condenser) / Q_Ref_BAC) ** 0.8

    def _compute_condensing_tower_cost(self) -> float:

        TDC = self._tower_design_coefficient
        PPI = self._PPI_PE

        Q_cooler = 0.0
        Q_condenser = self._Q_condenser_total

        C_cooling = 0.0
        C_condensing = self._get_C_condensing()  # specific condensing tower cost ($/kW)

        Q_Ref_BAC = 1.0e6  # nominal heat load (=1.0 MWth)
        F_cooling = abs(Q_cooler) / (abs(Q_cooler) + abs(Q_condenser) + 1e-10)
        C_Ref_BAC = PPI * Q_Ref_BAC * TDC * (F_cooling * (C_cooling / 1e3) + (1 - F_cooling) * (C_condensing / 1e3))
        return C_Ref_BAC * (abs(Q_cooler + Q_condenser) / Q_Ref_BAC) ** 0.8

    def _execute_CPG(self, state) -> float:

        if self._surface_unit == None:
            return 0.

        X_SE = 1.39  # secondary equipment cost (control system, pumps, valuves, buildings, etc.)
        X_CL = 0.58  # construction labor cost
        X_CM = 0.11  # construction material cost
        X_ST = 0.00  # sales tax
        X_F = 0.04  # equipment freight

        self._state = state

        self._process_surface_state()

        C_turbine_generator = self._compute_turbine_generator_cost()

        C_pump_inj = self._compute_pump_inj_cost(self._W_pump_total)

        C_cooling_condensing_tower = self._compute_cooling_condensing_tower_cost()

        C_plant_PEC = C_turbine_generator + C_pump_inj + C_cooling_condensing_tower  # primary equipment cost (PEC)

        C_plant_TEC = X_SE * C_plant_PEC  # total equipment cost (TEC)

        C_plant_BEC = C_plant_TEC * (1. + X_CL + X_CM + X_ST + X_F)  # bare erected cost (BEC)

        return self._X_PC * self._X_IC * C_plant_BEC  # total surface plant cost (TPC)

    def _execute_ORC_tespy(self, state) -> float:

        if self._surface_unit == None:
            return 0.

        X_SE = 1.39  # secondary equipment cost (control system, pumps, valuves, buildings, etc.)
        X_CL = 0.58  # construction labor cost
        X_CM = 0.11  # construction material cost
        X_ST = 0.00  # sales tax
        X_F = 0.04  # equipment freight

        self._state = state

        self._process_surface_state()

        C_turbine_generator = self._compute_turbine_generator_cost()

        C_pump_inj = self._compute_pump_inj_cost(self._W_pump_total)

        C_cooling_condensing_tower = self._compute_cooling_condensing_tower_cost()

        C_plant_PEC = C_turbine_generator + C_pump_inj + C_cooling_condensing_tower  # primary equipment cost (PEC)

        C_plant_TEC = X_SE * C_plant_PEC  # total equipment cost (TEC)

        C_plant_BEC = C_plant_TEC * (1. + X_CL + X_CM + X_ST + X_F)  # bare erected cost (BEC)

        return self._X_PC * self._X_IC * C_plant_BEC  # total surface plant cost (TPC)

    def _execute_DF_tespy(self, state) -> float:

        if self._surface_unit == None:
            return 0.

        X_SE = 1.39  # secondary equipment cost (control system, pumps, valuves, buildings, etc.)
        X_CL = 0.58  # construction labor cost
        X_CM = 0.11  # construction material cost
        X_ST = 0.00  # sales tax
        X_F = 0.04  # equipment freight

        self._state = state

        self._process_surface_state()

        C_turbine_generator = self._compute_turbine_generator_cost()

        C_pump_inj = self._compute_pump_inj_cost(self._W_pump_total)

        C_cooling_condensing_tower = self._compute_condensing_tower_cost()

        C_pump_prod = 0.0

        C_flash_separator = self._state.flash_separator_cost

        C_expansion_valve = self._state.expansion_valve_cost

        C_plant_PEC = C_turbine_generator + C_pump_inj + C_cooling_condensing_tower + C_pump_prod + C_flash_separator + C_expansion_valve  # primary equipment cost (PEC)
        # C_plant_PEC = C_pump_inj + C_cooling_condensing_tower + C_pump_prod + C_flash_separator + C_expansion_valve  # primary equipment cost (PEC)

        C_plant_TEC = X_SE * C_plant_PEC  # total equipment cost (TEC)

        C_plant_BEC = C_plant_TEC * (1. + X_CL + X_CM + X_ST + X_F)  # bare erected cost (BEC)

        print('components', C_turbine_generator, C_pump_inj, C_cooling_condensing_tower, C_pump_prod, C_flash_separator, C_expansion_valve)

        return self._X_PC * self._X_IC * C_plant_BEC  # total surface plant cost (TPC)


    def _compute_heat_exchanger_cost(self) -> float:
        U = 500. # W/m**2-K
        if np.isnan(self._dT_LMTD_preheater) or self._dT_LMTD_preheater == 0:
            A_preheater = 0
        else:
            A_preheater = self._Q_preheater_total / U / self._dT_LMTD_preheater
        A_boiler = self._Q_boiler_total / U / self._dT_LMTD_boiler
        A_HX = A_preheater + A_boiler
        return self._PPI_HX * (239. * A_HX + 13400.)


    def _compute_recuperator_cost(self) -> float:
        if np.isnan(self._dT_LMTD_recuperator) or self._dT_LMTD_recuperator == 0:
            return 0.
        else:
            U = 500.  # W/m**2-K
            return self._PPI_HX * (239. * self._Q_recuperator_total / U / self._dT_LMTD_recuperator + 13400.)


    def _compute_pump_prod_lineshaft_cost(self, W_pump) -> float:
        PPI = self._PPI_pump
        S_pump = self._pump_material_cost_multiplier
        return PPI * S_pump * 1750 * (1.34 * -1 * (W_pump / 1e3)) ** 0.7 + 5750. * (1.34 * -1. * (W_pump / 1.e3)) ** 0.2


    def _execute_ORC(self, state) -> float:

        if self._surface_unit == None:
            return 0.

        X_SE = 1.39  # secondary equipment cost (control system, pumps, valuves, buildings, etc.)
        X_CL = 0.58  # construction labor cost
        X_CM = 0.11  # construction material cost
        X_ST = 0.00  # sales tax
        X_F = 0.04  # equipment freight

        self._state = state

        self._process_surface_state()

        C_turbine_generator = self._compute_turbine_generator_cost()

        C_pump_inj = self._compute_pump_inj_cost(self._W_pump_ORC)

        C_pump_prod = self._compute_pump_prod_lineshaft_cost(self._W_pump_prod)

        C_cooling_condensing_tower = self._compute_cooling_condensing_tower_cost()

        C_heat_exchanger = self._compute_heat_exchanger_cost()

        C_recuperator = self._compute_recuperator_cost()

        C_plant_PEC = C_turbine_generator + C_pump_inj + C_pump_prod \
                      + C_cooling_condensing_tower + C_heat_exchanger + C_recuperator # primary equipment cost (PEC)

        C_plant_TEC = X_SE * C_plant_PEC  # total equipment cost (TEC)

        C_plant_BEC = C_plant_TEC * (1. + X_CL + X_CM + X_ST + X_F)  # bare erected cost (BEC)

        return self._X_PC * self._X_IC * C_plant_BEC  # total surface plant cost (TPC)


    def get_net_W_total(self) -> float:
        return self._W_net_total
