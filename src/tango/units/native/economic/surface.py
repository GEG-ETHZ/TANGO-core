import numpy as np


class EconUnitSurfacePipes:
    """
    Represents the economic unit for surface piping in geothermal systems.

    Attributes:
        _specs (dict): Economic and design specifications.
        _PPI (float): Producer Price Index (PPI) for pipe cost.
        _X_IC (float): Indirect cost multiplier.
        _X_PC (float): Project contingency multiplier.
        _surface_unit (object): Associated surface unit.
    """

    def __init__(self, specs: dict, unit: object):
        """
        Initializes the EconUnitSurfacePipes object.

        Args:
            specs (dict): Economic and design specifications.
            unit (object): Associated surface unit.
        """
        self._specs = specs
        self._PPI = self._specs.PPI
        self._X_IC, self._X_PC = self._specs.multipliers
        self._surface_unit = unit

    def _compute_surface_pipe_total_length(self) -> float:
        """
        Computes the total length of surface pipes.

        Logic:
        - Based on the well pattern and number of patterns, computes the pipe length.

        Returns:
            float: Total length of surface pipes.

        Raises:
            ValueError: If the well pattern is unsupported.

        Example:
            >>> length = self._compute_surface_pipe_total_length()
        """
        L_single_pair = self._specs.well_spacing
        if self._specs.well_pattern in ['DOUBLET', 'AGS']:
            return L_single_pair
        elif '5SPOT' in self._specs.well_pattern:
            return self._specs.num_patterns * 4 * L_single_pair
        else:
            raise ValueError(f"well_pattern: {self._specs.well_pattern} is not supported")

    def execute(self) -> float:
        """
        Calculates the total cost of surface piping.

        This method calculates the total surface piping costs based on the type of configuration:
        - If `type` is `default_predefined`, it calculates the surface piping cost using the formula.
        - If `type` is `user_defined`, it directly returns the value from `function_def`.

        Formula for default_predefined:
            Cost = X_PC * X_IC * PPI * (2205 * D^2 + 134) * L

        Returns:
            float: Total surface piping cost.

        Example:
            >>> cost = self.execute()
        """
        surface_pipe_cost_type = self._specs.costs['surface_pipes']['type']

        if surface_pipe_cost_type == 'default_predefined':
            if self._surface_unit is None:
                return 0
            L = self._compute_surface_pipe_total_length()
            D = self._surface_unit.specs.pipe_diameter
            return self._X_PC * self._X_IC * self._PPI * (2205. * D ** 2 + 134.) * L

        elif surface_pipe_cost_type == 'user_defined':
            return self._specs.costs['surface_pipes']['function_def']['value']

        else:
            raise ValueError(f"Unsupported surface piping cost type: {surface_pipe_cost_type}")



class EconUnitSurfacePowerPlant:
    """
    Represents the economic unit for surface power plant in geothermal systems.

    Attributes:
        _specs (dict): Economic and design specifications.
        _PPI_PE (float): PPI for power equipment.
        _PPI_pump (float): PPI for pumps.
        _PPI_TG (float): PPI for turbines and generators.
        _PPI_HX (float): PPI for heat exchangers.
        _X_IC (float): Indirect cost multiplier.
        _X_PC (float): Project contingency multiplier.
        _surface_unit (object): Associated surface unit.
    """

    def __init__(self, specs: dict, unit: object):
        """
        Initializes the EconUnitSurfacePowerPlant object.

        Args:
            specs (dict): Economic and design specifications.
            unit (object): Associated surface unit.
        """
        self._specs = specs
        self._PPI_PE = self._specs.PPI_PE
        self._PPI_pump = self._specs.PPI_pump
        self._PPI_TG = self._specs.PPI_TG
        self._PPI_HX = self._specs.PPI_HX
        self._X_IC, self._X_PC = self._specs.multipliers
        self._surface_unit = unit
        self._initialize_constants()
        self._initialize_units()

    def _get_turbine_cost_multiplier(self) -> float:
        """
        Retrieves the turbine cost multiplier based on fluid type.

        Returns:
            float: Turbine cost multiplier.

        Example:
            >>> multiplier = self._get_turbine_cost_multiplier()
        """
        return 1.0 if self._specs.fluid_name != 'CO2' else 1.2

    def _get_pump_material_cost_multiplier(self) -> float:
        """
        Retrieves the pump material cost multiplier based on fluid type.

        Logic:
        - Stainless steel for non-water fluids (multiplier = 2.09).
        - Iron for water or glycol fluids (multiplier = 1.0).

        Returns:
            float: Pump material cost multiplier.

        Example:
            >>> multiplier = self._get_pump_material_cost_multiplier()
        """
        return 2.09 if self._specs.fluid_name != 'H2O' else 1.0

    def _get_tower_design_coefficient(self) -> float:
        """
        Retrieves the cooling tower design coefficient based on fluid type and design.

        Returns:
            float: Cooling tower design coefficient.

        Raises:
            ValueError: If the design or fluid type is unsupported.

        Example:
            >>> coefficient = self._get_tower_design_coefficient()
        """
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
                raise ValueError(f"Surface cooling tower design: {design} with fluid: {self._specs.fluid_name} is not supported")
        else:
            raise ValueError(f"Surface cooling tower design: {design} is not supported")

    def _initialize_constants(self) -> None:
        """
        Initializes constants for surface power plant calculations.

        Notes:
        - Includes coefficients for cooling and condensing, turbine and pump cost multipliers, and tower design coefficients.

        Example:
            >>> self._initialize_constants()
        """
        if self._surface_unit is None:
            return

        self._surface_pipe_diameter = self._surface_unit.specs.pipe_diameter
        self._surface_ambient_temperature = self._surface_unit.specs.surface_temperature
        self._surface_approach_temperature = self._surface_unit.specs.approach_temperature
        self._surface_temperature_range = self._surface_unit.specs.temperature_range
        self._surface_cooling_tower_mode = self._surface_unit.specs.cooling_mode

        # Coefficients for BAC regression units
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
        """
        Initializes the units based on the type of surface power plant.

        Logic:
        - Identifies the power plant type from the module name.
        - Assigns appropriate methods for processing and execution based on the power plant type.

        Supported Types:
        - 'CPG': Closed-loop power generation.
        - 'DH': Direct heat.
        - 'ORC': Organic Rankine Cycle.

        Raises:
            ValueError: If the power plant type is not supported.

        Example:
            >>> self._initialize_units()
        """
        if self._surface_unit is None:
            return
        power_plant_type = str(self._surface_unit.__module__).split('.')[-1]
        if power_plant_type == 'CPG':
            self._process_surface_state = self._process_surface_state_CPG
            self.execute = self._execute_CPG
        elif power_plant_type == 'DH':
            self._process_surface_state = self._process_surface_state_DH
            self.execute = self._execute_DH
        elif power_plant_type == 'ORC':
            self.execute = self._execute_ORC
            self._process_surface_state = self._process_surface_state_ORC
        else:
            raise ValueError(f"Surface power plant type: {power_plant_type} is not supported.")


    def _process_surface_state_DH(self) -> None:
        """
        Processes the surface state for direct heat (DH) systems.

        Logic:
        - Computes the thermal power output and assigns it as the total net power.

        Example:
            >>> self._process_surface_state_DH()
        """
        mult = self._specs.num_patterns
        self._W_thermal = mult * self._state.w_turbine
        self._W_net_total = self._W_thermal


    def _execute_DH(self, state) -> float:
        """
        Executes the calculations for direct heat (DH) systems.

        This method calculates the total DH costs based on the type of configuration:
        - If `type` is `default_predefined`, it calculates the DH cost using the detailed formula.
        - If `type` is `user_defined`, it directly returns the value from `function_def`.

        Args:
            state: The current surface state object.

        Returns:
            float: The total DH system cost or user-defined value.

        Formula for default_predefined:
            .. math::
                Cost = 200 * W_{\text{net total}} / 1000
        """
        self._state = state
        self._process_surface_state()

        DH_cost_type = self._specs.costs['power_plant']['type']

        if DH_cost_type == 'default_predefined':
            if self._surface_unit is None:
                return 0.0

            return 200 * self._W_net_total / 1000

        elif DH_cost_type == 'user_defined':
            return self._specs.costs['power_plant']['function_def']['value']

        else:
            raise ValueError(f"Unsupported power plant cost type: {DH_cost_type}")


    def _process_surface_state_CPG(self) -> None:
        """
        Processes the surface state for closed-loop power generation (CPG) systems.

        Logic:
        - Computes the total heat and power quantities across multiple components (e.g., condenser, cooler).
        - Aggregates power and thermal energy outputs.

        Example:
            >>> self._process_surface_state_CPG()
        """
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
        self._W_net_total = (self._W_pump_total + self._W_turbine_total +
                             self._W_cooler_total + self._W_condenser_total)
        self._W_net_thermal = self._state.thermal_power


    def _process_surface_state_ORC(self) -> None:
        """
        Processes the surface state for Organic Rankine Cycle (ORC) systems.

        Logic:
        - Computes total heat and power quantities for the ORC system.
        - Includes additional parameters such as temperature ranges and LMTD values.

        Example:
            >>> self._process_surface_state_ORC()
        """
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
        self._W_net_thermal = self._state.thermal_power

        self._dT_range_CT = self._state.dT_range_CT
        self._dT_LMTD_preheater = self._state.dT_LMTD_preheater
        self._dT_LMTD_boiler = self._state.dT_LMTD_boiler
        self._dT_LMTD_recuperator = self._state.dT_LMTD_recuperator


    def _compute_turbine_generator_cost(self) -> float:
        """
        Computes the cost of the turbine generator.

        Formula:
            Cost = 0.67 * PPI * (S_T_fluid * 2830 * (W_turbine / 1e3)^0.745 + 3680 * (W_turbine / 1e3)^0.617)

        Returns:
            float: Turbine generator cost in USD.

        Example:
            >>> cost = self._compute_turbine_generator_cost()
        """
        PPI = self._PPI_TG
        S_T_fluid = self._turbine_cost_multiplier
        W_turbine = self._W_turbine_total
        return 0.67 * PPI * (S_T_fluid * 2830 * (W_turbine / 1.e3) ** 0.745 + 3680 * (W_turbine / 1.e3) ** 0.617)


    def _compute_pump_inj_cost(self, W_pump: float) -> float:
        """
        Computes the cost of the injection pump.

        Formula:
            Cost = PPI * S_pump * 1750 * (1.34 * -1 * (W_pump / 1e3))^0.7

        Args:
            W_pump (float): Power of the injection pump in Watts.

        Returns:
            float: Injection pump cost in USD.

        Example:
            >>> cost = self._compute_pump_inj_cost(1e6)
        """
        PPI = self._PPI_pump
        S_pump = self._pump_material_cost_multiplier
        return PPI * S_pump * 1750 * (1.34 * -1 * (W_pump / 1e3)) ** 0.7


    def _BAC_regression_model(self, coeffs: list) -> float:
        """
        Baltimore Aircoil (BAC) regression model for cooling and condensing costs.

        Args:
            coeffs (list): Coefficients for the regression model.

        Returns:
            float: Cost estimate based on the regression model.

        Formula:
            Cost = a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach + dT_range)

        Example:
            >>> cost = self._BAC_regression_model(coeffs=[5.58e3, 0., -1.77e1, 1.96e2])
        """
        a, b, c, d = coeffs
        T_ambient = self._surface_ambient_temperature
        dT_approach = self._surface_approach_temperature
        dT_range = self._surface_temperature_range
        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach + dT_range)


    def _get_C_cooling(self):
        """
        Retrieves the cooling cost based on the BAC regression model.

        Returns:
            float: Cooling cost in USD.

        Example:
            >>> cooling_cost = self._get_C_cooling()
        """
        return self._BAC_regression_model(coeffs=self._coeffs_cooling)


    def _get_C_condensing(self):
        """
        Retrieves the condensing cost based on the BAC regression model.

        Returns:
            float: Condensing cost in USD.

        Example:
            >>> condensing_cost = self._get_C_condensing()
        """
        return self._BAC_regression_model(coeffs=self._coeffs_condensing)


    def _compute_cooling_condensing_tower_cost(self) -> float:
        """
        Computes the cost of the cooling and condensing towers.

        Formula:
            C = PPI * Q_ref * TDC * [F_cooling * (C_cooling / 1e3) + (1 - F_cooling) * (C_condensing / 1e3)]
            C_total = C * [(abs(Q_cooler + Q_condenser) / Q_ref) ** 0.8]

        Returns:
            float: Total cost of the cooling and condensing towers.

        Example:
            >>> cost = self._compute_cooling_condensing_tower_cost()
        """
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


    def _execute_CPG(self, state) -> float:
        """
        Executes cost calculations for Closed-loop Power Generation (CPG) systems.

        This method calculates the total power plant costs based on the type of configuration:
        - If `type` is `default_predefined`, it calculates the power plant cost using the detailed formula.
        - If `type` is `user_defined`, it directly returns the value from `function_def`.

        Args:
            state: The current surface state.

        Returns:
            float: Total surface plant cost (TPC).

        Formula for default_predefined:
            .. math::
                TPC = X_PC * X_IC * BEC

            Where:
                BEC = TEC * (1 + X_CL + X_CM + X_ST + X_F)
                TEC = X_SE * PEC
                PEC = Sum of equipment costs.
        """
        self._state = state
        self._process_surface_state()

        power_plant_cost_type = self._specs.costs['power_plant']['type']

        if power_plant_cost_type == 'default_predefined':
            if self._surface_unit is None:
                return 0.0

            # Constants for cost components
            X_SE = 1.39  # secondary equipment cost
            X_CL = 0.58  # construction labor cost
            X_CM = 0.11  # construction material cost
            X_ST = 0.00  # sales tax
            X_F = 0.04  # equipment freight

            C_turbine_generator = self._compute_turbine_generator_cost()
            C_pump_inj = self._compute_pump_inj_cost(self._W_pump_total)
            C_cooling_condensing_tower = self._compute_cooling_condensing_tower_cost()

            C_plant_PEC = C_turbine_generator + C_pump_inj + C_cooling_condensing_tower  # primary equipment cost (PEC)
            C_plant_TEC = X_SE * C_plant_PEC  # total equipment cost (TEC)
            C_plant_BEC = C_plant_TEC * (1.0 + X_CL + X_CM + X_ST + X_F)  # bare erected cost (BEC)

            return self._X_PC * self._X_IC * C_plant_BEC  # total surface plant cost (TPC)

        elif power_plant_cost_type == 'user_defined':
            return self._specs.costs['power_plant']['function_def']['value']

        else:
            raise ValueError(f"Unsupported power plant cost type: {power_plant_cost_type}")



    def _compute_heat_exchanger_cost(self) -> float:
        """
        Computes the cost of heat exchangers.

        Formula:

            Cost = PPI_HX * (239 * A_HX + 13400)

            Where:
                A_HX = A_preheater + A_boiler
                A_preheater = Q_preheater / (U * dT_LMTD_preheater)
                A_boiler = Q_boiler / (U * dT_LMTD_boiler)

        Returns:
            float: Total cost of heat exchangers.
        """
        U = 500.  # W/m²-K (Heat transfer coefficient)
        if np.isnan(self._dT_LMTD_preheater) or self._dT_LMTD_preheater == 0:
            A_preheater = 0
        else:
            A_preheater = self._Q_preheater_total / U / self._dT_LMTD_preheater
        A_boiler = self._Q_boiler_total / U / self._dT_LMTD_boiler
        A_HX = A_preheater + A_boiler
        return self._PPI_HX * (239. * A_HX + 13400.)


    def _compute_recuperator_cost(self) -> float:
        """
        Computes the cost of the recuperator.

        Formula:

            Cost = PPI_HX * (239 * A_recuperator + 13400)

            Where:
                A_recuperator = Q_recuperator / (U * dT_LMTD_recuperator)

        Returns:
            float: Recuperator cost.
        """
        if np.isnan(self._dT_LMTD_recuperator) or self._dT_LMTD_recuperator == 0:
            return 0.0
        else:
            U = 500.  # W/m²-K
            return self._PPI_HX * (239. * self._Q_recuperator_total / U / self._dT_LMTD_recuperator + 13400.)


    def _compute_pump_prod_lineshaft_cost(self, W_pump: float) -> float:
        """
        Computes the cost of the production pump with a lineshaft.

        Formula:
            Cost = PPI * S_pump * 1750 * (1.34 * -1 * (W_pump / 1e3))^0.7
                 + 5750 * (1.34 * -1 * (W_pump / 1e3))^0.2

        Args:
            W_pump (float): Pump power in Watts.

        Returns:
            float: Production pump cost.

        Example:
            >>> cost = self._compute_pump_prod_lineshaft_cost(1e6)
        """
        PPI = self._PPI_pump
        S_pump = self._pump_material_cost_multiplier
        return PPI * S_pump * 1750 * (1.34 * -1 * (W_pump / 1e3)) ** 0.7 + 5750. * (1.34 * -1. * (W_pump / 1e3)) ** 0.2


    def _execute_ORC(self, state) -> float:
        """
        Executes cost calculations for Organic Rankine Cycle (ORC) systems.

        This method calculates the total ORC costs based on the type of configuration:
        - If `type` is `default_predefined`, it calculates the ORC cost using the detailed formula.
        - If `type` is `user_defined`, it directly returns the value from `function_def`.

        Args:
            state: The current surface state.

        Returns:
            float: Total surface plant cost (TPC).

        Formula for default_predefined:
            .. math::
                TPC = X_PC * X_IC * BEC

            Where:

                BEC = TEC * (1 + X_CL + X_CM + X_ST + X_F)
                TEC = X_SE * PEC
                PEC = Sum of equipment costs.
        """
        self._state = state
        self._process_surface_state()

        ORC_cost_type = self._specs.costs['power_plant']['type']

        if ORC_cost_type == 'default_predefined':
            if self._surface_unit is None:
                return 0.0

            # Constants for cost components
            X_SE = 1.39  # secondary equipment cost
            X_CL = 0.58  # construction labor cost
            X_CM = 0.11  # construction material cost
            X_ST = 0.00  # sales tax
            X_F = 0.04  # equipment freight

            C_turbine_generator = self._compute_turbine_generator_cost()
            C_pump_inj = self._compute_pump_inj_cost(self._W_pump_ORC)
            C_pump_prod = self._compute_pump_prod_lineshaft_cost(self._W_pump_prod)
            C_cooling_condensing_tower = self._compute_cooling_condensing_tower_cost()
            C_heat_exchanger = self._compute_heat_exchanger_cost()
            C_recuperator = self._compute_recuperator_cost()

            # Primary equipment cost (PEC)
            C_plant_PEC = (
                C_turbine_generator +
                C_pump_inj +
                C_pump_prod +
                C_cooling_condensing_tower +
                C_heat_exchanger +
                C_recuperator +
                200.0 * self._W_net_thermal / 1000.0
            )

            C_plant_TEC = X_SE * C_plant_PEC  # total equipment cost (TEC)
            C_plant_BEC = C_plant_TEC * (1.0 + X_CL + X_CM + X_ST + X_F)  # bare erected cost (BEC)

            return self._X_PC * self._X_IC * C_plant_BEC  # total surface plant cost (TPC)

        elif ORC_cost_type == 'user_defined':
            return self._specs.costs['power_plant']['function_def']['value']

        else:
            raise ValueError(f"Unsupported power plant cost type: {ORC_cost_type}")


    def get_net_W_total(self) -> float:
        """
        Retrieves the total net power output.

        Returns:
            float: Net power output in Watts.

        Example:
            >>> net_power = self.get_net_W_total()
        """
        return self._W_net_total

