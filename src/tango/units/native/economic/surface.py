import numpy as np

import yaml
from tespy.components import Sink, Source, Turbine, SimpleHeatExchanger, Compressor, Valve, DropletSeparator, Merge, HeatExchanger, CycleCloser
from tespy.connections import Connection
from tespy.networks import Network
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

    def execute(self, evaluated_funcs) -> float:
        """
        Calculates the total cost of surface piping.

        This method calculates the total surface piping costs based on the type of configuration:
        - If `type` is `default`, it calculates the surface piping cost using the formula.
        - If `type` is `custom`, it directly returns the value from `function_def`.

        Formula for default:
            Cost = X_PC * X_IC * PPI * (2205 * D^2 + 134) * L

        Returns:
            float: Total surface piping cost.

        Example:
            >>> cost = self.execute()
        """
        surface_pipe_cost_type = self._specs.costs['surface_pipes']['type']

        if surface_pipe_cost_type == 'default':
            if self._surface_unit is None:
                return 0
            L = self._compute_surface_pipe_total_length()
            D = self._surface_unit.specs.pipe_diameter
            return self._X_PC * self._X_IC * self._PPI * (2205. * D ** 2 + 134.) * L

        elif surface_pipe_cost_type == 'custom':
            if (self._specs.costs['surface_pipes']['function_def']['type'] == 'Constant'):
                return self._specs.costs['surface_pipes']['function_def']['value']
            elif (self._specs.costs['surface_pipes']['function_def']['type'] == 'mathematical_expression'):
                return evaluated_funcs[self._specs.costs['surface_pipes']['function']]
            else:
                raise ValueError(f"Unsupported custom function type: {self._specs.costs['surface_pipes']['function_def']['type']}")

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
        if (self._surface_unit.__class__.__name__ != 'SurfaceUnitFlexiblePP'):
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
        if power_plant_type == 'flexible_pp':
            self._process_surface_state = self._process_surface_state_flexible_pp
            self.execute = self._execute_flexible_pp
        elif power_plant_type == 'CPG':
            self._process_surface_state = self._process_surface_state_CPG
            self.execute = self._execute_CPG
        elif power_plant_type == 'ORC':
            self.execute = self._execute_ORC
            self._process_surface_state = self._process_surface_state_ORC
        else:
            raise ValueError(f"Surface power plant type: {power_plant_type} is not supported.")

    def _process_surface_state_flexible_pp(self) -> None:
        pass

    def _execute_flexible_pp(self, state, evaluated_funcs, average_fp_result) -> float:

        self._state = state
        self._process_surface_state()
        self.flexible_power_plant_cost = PowerPlantCost(self._state.power_plant, self._specs, evaluated_funcs, self._state.prod_pump_w_list)
        costs = self.flexible_power_plant_cost.compute_total_cost_with_averaged_results(average_fp_result)
        self._W_net_thermal = 0.0
        self._W_net_total = self.flexible_power_plant_cost.net_P
        self._W_net_thermal = self.flexible_power_plant_cost.thermal_power

        if self._surface_unit is None:
            return 0.0

        return costs

    def _process_surface_state_CPG(self) -> None:
        """
        Processes the surface state for closed-loop power generation (CPG) systems.

        Logic:
        - Computes the total heat and power quantities across multiple components (e.g., condenser, cooler).
        - Aggregates power and thermal energy outputs.

        Example:
            >>> self._process_surface_state_CPG()
        """
        # Compute heat quantities
        self._Q_condenser_total = self._state.q_condenser
        self._Q_cooler_total = self._state.q_cooler
        self._Q_preheater_total = self._state.q_preheater
        self._Q_boiler_total = self._state.q_boiler
        self._Q_desuperheater_total = self._state.q_desuperheater

        # Compute work quantities
        self._W_pump_total = self._state.w_pump
        self._W_turbine_total = self._state.w_turbine
        self._W_cooler_total = self._state.w_cooler
        self._W_condenser_total =self._state.w_condenser

        # Compute net work and thermal power
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
        self._Q_condenser_total = self._state.q_condenser
        self._Q_cooler_total = self._state.q_cooler
        self._Q_preheater_total = self._state.q_preheater
        self._Q_boiler_total = self._state.q_boiler
        self._Q_desuperheater_total = self._state.q_desuperheater
        self._Q_recuperator_total = self._state.q_recuperator

        self._W_pump_ORC = self._state.w_pump
        self._W_pump_prod = self._state.w_downhole_pump
        self._W_turbine_total = self._state.w_turbine
        self._W_net_total = (self._state.w_net + self._state.w_downhole_pump)
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

    def _execute_CPG(self, state, evaluated_funcs) -> float:
        """
        Executes cost calculations for Closed-loop Power Generation (CPG) systems.

        This method calculates the total power plant costs based on the type of configuration:
        - If `type` is `default`, it calculates the power plant cost using the detailed formula.
        - If `type` is `custom`, it directly returns the value from `function_def`.

        Args:
            state: The current surface state.

        Returns:
            float: Total surface plant cost (TPC).

        Formula for default:
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

        if power_plant_cost_type == 'default':
            if self._surface_unit is None:
                return 0.0

            # Constants for cost components
            X_SE = 1.39  # secondary equipment cost
            X_CL = 0.58  # construction labor cost
            X_CM = 0.11  # construction material cost
            X_ST = 0.00  # sales tax
            X_F = 0.04  # equipment freight

            C_turbine_generator = self._specs.num_pp * self._compute_turbine_generator_cost()
            C_pump_inj = self._specs.num_pp * self._compute_pump_inj_cost(self._W_pump_total)
            C_cooling_condensing_tower = self._specs.num_pp * self._compute_cooling_condensing_tower_cost()
            C_plant_PEC = C_turbine_generator + C_pump_inj + C_cooling_condensing_tower  # primary equipment cost (PEC)
            C_plant_TEC = X_SE * C_plant_PEC  # total equipment cost (TEC)
            C_plant_BEC = C_plant_TEC * (1.0 + X_CL + X_CM + X_ST + X_F)  # bare erected cost (BEC)

            return self._X_PC * self._X_IC * C_plant_BEC  # total surface plant cost (TPC)

        elif power_plant_cost_type == 'custom_entire_pp':
            if (self._specs.costs['power_plant']['function_def']['type'] == 'Constant'):
                return self._specs.costs['power_plant']['function_def']['value']
            elif (self._specs.costs['power_plant']['function_def']['type'] == 'mathematical_expression'):
                return evaluated_funcs[self._specs.costs['power_plant']['function']]
            else:
                raise ValueError(f"Unsupported custom function type: {self._specs.costs['power_plant']['function_def']['type']}")
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

    def _execute_ORC(self, state, evaluated_funcs) -> float:
        """
        Executes cost calculations for Organic Rankine Cycle (ORC) systems.

        This method calculates the total ORC costs based on the type of configuration:
        - If `type` is `default`, it calculates the ORC cost using the detailed formula.
        - If `type` is `custom`, it directly returns the value from `function_def`.

        Args:
            state: The current surface state.

        Returns:
            float: Total surface plant cost (TPC).

        Formula for default:
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

        if ORC_cost_type == 'default':
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
            C_plant_PEC = self._specs.num_pp * (
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

        elif ORC_cost_type == 'custom_entire_pp':
            if (self._specs.costs['power_plant']['function_def']['type'] == 'Constant'):
                return self._specs.costs['power_plant']['function_def']['value']
            elif (self._specs.costs['power_plant']['function_def']['type'] == 'mathematical_expression'):
                return evaluated_funcs[self._specs.costs['power_plant']['function']]
            else:
                raise ValueError(f"Unsupported custom function type: {self._specs.costs['power_plant']['function_def']['type']}")

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
        return self._specs.num_pp * self._W_net_total

class PowerPlantCost:
    def __init__(self, power_plant, specs, evaluated_funcs, prod_pump_w_list):
        """
        A class to compute various cost aspects of a power plant, including turbines, pumps,
        heat exchangers, and cooling systems. It calculates total costs based on
        predefined formulas or user-defined cost breakdowns.

        Attributes:
            power_plant (PowerPlant): The power plant object for which costs will be computed.
            cost_specs (object): Specifications containing cost-related data and multipliers.
            evaluated_funcs (dict): A dictionary of evaluated functions used for cost computation.
            _turbine_cost_multiplier (float): Multiplier for turbine cost based on fluid type.
            _pump_material_cost_multiplier (float): Multiplier for pump cost based on fluid type.
            _Q_preheater_total (float): Total heat transfer for the preheater (default: 0).
            _Q_boiler_total (float): Total heat transfer for the boiler (default: 0).
            _Q_recuperator_total (float): Total heat transfer for the recuperator (default: 0).
            _dT_LMTD_preheater (float): Log mean temperature difference for the preheater (default: 1).
            _dT_LMTD_boiler (float): Log mean temperature difference for the boiler (default: 1).
            _dT_LMTD_recuperator (float): Log mean temperature difference for the recuperator (default: 1).
            _PPI_PE (float): Producer Price Index for process equipment.
            _PPI_pump (float): Producer Price Index for pumps.
            _PPI_TG (float): Producer Price Index for turbine generators.
            _PPI_HX (float): Producer Price Index for heat exchangers.
            _X_IC (float): Installation cost multiplier.
            _X_PC (float): Project contingency multiplier.

        Args:
            power_plant (PowerPlant): The PowerPlant object for which costs will be computed.
            specs (object): Specifications containing cost data, price indices, and multipliers.
            evaluated_funcs (dict): A dictionary of evaluated cost functions.
        """
        self.prod_pump_w_list = prod_pump_w_list
        self.power_plant = power_plant
        self.cost_specs = specs
        self.evaluated_funcs = evaluated_funcs
        self._turbine_cost_multiplier = self._get_turbine_cost_multiplier()
        self._pump_material_cost_multiplier = self._get_pump_material_cost_multiplier()

        self._Q_preheater_total = 0
        self._Q_boiler_total = 0
        self._Q_recuperator_total = 0

        self._dT_LMTD_preheater = 1
        self._dT_LMTD_boiler = 1
        self._dT_LMTD_recuperator = 1

        self._PPI_PE = self.cost_specs.PPI_PE
        self._PPI_pump = self.cost_specs.PPI_pump
        self._PPI_TG = self.cost_specs.PPI_TG
        self._PPI_HX = self.cost_specs.PPI_HX
        self._X_IC, self._X_PC = self.cost_specs.multipliers

    def _get_turbine_cost_multiplier(self) -> float:
        """
        Retrieves the turbine cost multiplier based on fluid type.

        Returns:
            float: Turbine cost multiplier.

        Example:
            >>> multiplier = self._get_turbine_cost_multiplier()
        """
        return 1.0 if self.cost_specs.fluid_name != 'CO2' else 1.2

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
        return 2.09 if self.cost_specs.fluid_name != 'H2O' else 1.0

    def _compute_total_turbine_work(self):
        """
        Computes the total turbine work based on the power plant configuration.

        This method iterates through all turbine components within the power plant,
        retrieves their power values, and sums them to compute the total turbine work.

        Returns:
            float: Total turbine work in watts (W).

        Notes:
            - Turbine power is assumed to be available via the `P.val` attribute of each turbine node.
            - The method prints the power of each turbine and the total turbine power for debugging purposes.

        Prints:
            - Individual turbine power values and the total computed turbine power.

        Raises:
            AttributeError: If the turbine object does not have the required `P.val` attribute.
        """
        total_work = 0.0
        for node_name, node in self.power_plant.nodes.items():
            if isinstance(node, Turbine):
                turbine_work = node.P.val
                # print(f"{node.label} Power: {turbine_work} W")
                total_work += turbine_work
        # print(f"Total Turbine Power: {total_work} W")

        return total_work

    def compute_cooler_condenser_power(self):
        """
        Computes the parasitic power consumption of coolers and condensers in the power plant.

        This method iterates through all cooler and condenser components within the power plant,
        calculates their respective heat loads, and determines the parasitic power consumption
        based on predefined coefficients for cooling tower modes ('WET' or 'DRY').

        Returns:
            tuple: A tuple containing:
                - float: Total cooling power consumption in watts (W).
                - float: Total condensing power consumption in watts (W).

        Notes:
            - Coolers and condensers are identified by their `Subtype` in the power plant configuration.
            - Supported cooling tower modes: 'WET' and 'DRY'.
            - The method raises a ValueError if an invalid `cooling_tower_mode` is encountered.
            - Heat loads are assumed to be given as positive values in TESPy, hence negated here.

        Prints:
            - Heat loads of each cooler and condenser.
            - Calculated cooling and condensing power consumption.

        Raises:
            ValueError: If an invalid `cooling_tower_mode` is specified in the component configuration.
        """
        w_cooler = w_condenser = 0.0
        q_cooler = q_condenser = 0.0
        self.thermal_power = 0.0

        for node_name, node in self.power_plant.nodes.items():
            if isinstance(node, SimpleHeatExchanger):
                component_config = self.power_plant.config.get(node_name, {})
                subtype = component_config.get('Subtype', '').lower()

                if subtype in ['cooler', 'condenser']:
                    tower_mode = component_config.get('cooling_tower_mode', '').upper()
                    if tower_mode not in ['WET', 'DRY']:
                        raise ValueError(f"Invalid cooling_tower_mode '{tower_mode}' in component_config for {node_name}")

                    self._surface_cooling_tower_mode = tower_mode

                    if self._surface_cooling_tower_mode == 'WET':
                        self._coeffs_cooling_power = [1.2, 0.0, -3.79e-3, 1.95e-2]
                        self._coeffs_condensing_power = [1.65, -6.24e-6, -5.03e-3, 0.0]
                    elif self._surface_cooling_tower_mode == 'DRY':
                        self._coeffs_cooling_power = [7.65e-1, 0.0, 0.0, 1.28e-1]
                        self._coeffs_condensing_power = [0.619, 0.0, 0.0, 0.0]

                    if subtype == 'cooler':
                        q_cooler = -node.Q.val
                        f_cooling = self._get_parasitic_power_fraction_cooling()
                        power = q_cooler * f_cooling
                        w_cooler += power
                        # print(f"{node.label} (Cooler) - Heat Load: {q_cooler:.2f} W, Parasitic Power: {power:.2f} W")

                    elif subtype == 'condenser':
                        q_condenser = -node.Q.val
                        f_condensing = self._get_parasitic_power_fraction_condensing()
                        power = q_condenser * f_condensing
                        w_condenser += power
                        # print(f"{node.label} (Condenser) - Heat Load: {q_condenser:.2f} W, Parasitic Power: {power:.2f} W")

                elif (subtype == 'dh_component'):
                    self.thermal_power += -node.Q.val

        return w_cooler, w_condenser

    def _get_parasitic_power_fraction_cooling(self):
        """
        Computes the parasitic power fraction for cooling.

        Returns:
            float: Cooling parasitic power fraction.
        """
        return self._BAC_regression_model(coeffs=self._coeffs_cooling_power)

    def _get_parasitic_power_fraction_condensing(self):
        """
        Computes the parasitic power fraction for condensing.

        Returns:
            float: Condensing parasitic power fraction.
        """
        return self._BAC_regression_model(coeffs=self._coeffs_condensing_power)

    def _compute_total_pump_work(self):
        """
        Computes the total pump work for all pumps in the power plant.

        This method iterates through all compressor components in the power plant (pumps are modeled
        as compressors in TESPy), retrieves their power values, and sums them to calculate
        the total pump work.

        Returns:
            float: Total pump work in watts (W).

        Notes:
            - Pumps are modeled as `Compressor` objects in TESPy.
            - The power consumption of each pump is assumed to be accessible via the `P.val` attribute.
            - The method prints individual pump power values and the total computed pump power
              for debugging purposes.

        Prints:
            - Individual pump power values and the total computed pump power.

        Raises:
            AttributeError: If a pump object does not contain the required `P.val` attribute.
        """
        total_work = 0.0
        for node_name, node in self.power_plant.nodes.items():
            if isinstance(node, Compressor):
                pump_work = node.P.val
                # print(f"{node.label} Power: {pump_work} W")
                total_work += pump_work
        # print(f"Total Pump Power: {total_work} W")

        return total_work

    def compute_net_power(self):
        """
        Computes the net power output of the power plant.

        This method calculates the net power by subtracting the total parasitic power
        (including pump, cooling, and condensing power) from the total turbine work.

        Formula:
            Net Power = Total Turbine Work - (Total Pump Work + Cooling Power + Condensing Power)

        Returns:
            float: The net power output of the power plant in watts (W).

        Notes:
            - The total turbine work is obtained using `_compute_total_turbine_work()`.
            - The total pump work is calculated with `_compute_total_pump_work()`.
            - Cooling and condensing power are computed using `compute_cooler_condenser_power()`.
            - Debugging details including individual power components are printed.

        Prints:
            - The computed net power output.
            - Detailed breakdown of turbine, pump, cooling, and condensing power.

        Raises:
            ValueError: If any component lacks the required attributes for computation.
        """
        cooling_power, condensing_power = self.compute_cooler_condenser_power()
        turbine_power = self._compute_total_turbine_work()
        pump_power = self._compute_total_pump_work()

        if (len(self.prod_pump_w_list) != 0):
            prod_pump_w = sum(self.prod_pump_w_list) / len(self.prod_pump_w_list)
        else:
            prod_pump_w = 0

        net_power = turbine_power + pump_power - (cooling_power + condensing_power) + prod_pump_w
        # print(f"Net Power Output: {net_power:.2f} W")
        # print(f"Components - Turbine Power: {turbine_power:.2f} W, "
        #       f"Pump Power: {pump_power:.2f} W, "
        #       f"Cooling Power: {cooling_power:.2f} W, "
        #       f"Condensing Power: {condensing_power:.2f} W")

        return net_power

    def _compute_turbine_generator_costs(self) -> float:
        """
        Computes the total cost of all turbine generators in the power plant.

        The cost is calculated using the following formula:

            Cost = 0.67 * PPI * (S_T_fluid * 2830 * (W_turbine / 1e3)^0.745 + 3680 * (W_turbine / 1e3)^0.617)

        where:
            - PPI: Producer Price Index for turbine generators.
            - S_T_fluid: Turbine cost multiplier based on fluid type.
            - W_turbine: Power output of the turbine in watts.

        The method checks if the cost breakdown is user-defined. If so, it retrieves
        the predefined turbine cost; otherwise, it calculates the cost using the above formula.

        Returns:
            float: Total turbine generator cost in USD.

        Notes:
            - If a user-defined cost breakdown is available, it overrides calculated values.
            - Costs are aggregated across all turbine components in the power plant.
            - The power output of each turbine is assumed to be accessible via `P.val`.

        Prints:
            - Individual turbine costs and total turbine generator cost for debugging purposes.

        Raises:
            KeyError: If required cost specifications are missing in the configuration.
        """
        cost_type = self.cost_specs.costs['power_plant']['type']
        total_cost = 0.0

        for node_name, node in self.power_plant.nodes.items():
            if isinstance(node, Turbine):
                breakdown_exists = 'breakdown' in self.cost_specs.costs['power_plant']
                node_exists = breakdown_exists and node.label in self.cost_specs.costs['power_plant']['breakdown']
                if cost_type == 'custom_cost_breakdown' and node_exists:
                    turbine_cost = self.cost_specs.costs['power_plant']['breakdown'][node.label]['function_def']['value']
                    # print(f"{node.label} Cost: ${turbine_cost:,.2f}")
                    total_cost += turbine_cost
                else:
                    PPI = self._PPI_TG
                    S_T_fluid = self._turbine_cost_multiplier
                    W_turbine = node.P.val  # Work of the specific turbine
                    turbine_cost = 0.67 * PPI * (S_T_fluid * 2830 * (W_turbine / 1.e3) ** 0.745 +
                                                 3680 * (W_turbine / 1.e3) ** 0.617)
                    # print(f"Turbine {node.label} Cost: ${turbine_cost:,.2f}")
                    total_cost += turbine_cost

        # print(f"Total Turbine Generator Cost: ${total_cost:,.2f}")

        return total_cost

    def _compute_pump_inj_cost(self) -> float:
        """
        Computes the total cost of all injection pumps in the power plant.

        The cost is calculated using the following formula:

            Cost = PPI * S_pump * 1750 * (1.34 * -1 * (W_pump / 1e3))^0.7

        where:
            - PPI: Producer Price Index for pumps.
            - S_pump: Pump material cost multiplier.
            - W_pump: Power input of the pump in watts.

        The method first checks if a user-defined cost breakdown is provided; if so,
        the cost is retrieved from the specifications. Otherwise, the cost is computed
        using the above formula for each pump.

        Returns:
            float: Total injection pump cost in USD.

        Notes:
            - Pumps are modeled as `Compressor` objects in TESPy.
            - If a user-defined cost breakdown is available, it takes precedence over the calculated values.
            - The power input of each pump is assumed to be accessible via `P.val`.

        Prints:
            - Individual pump costs and the total pump cost for debugging purposes.

        Raises:
            KeyError: If required cost specifications are missing in the configuration.
        """
        cost_type = self.cost_specs.costs['power_plant']['type']
        total_cost = 0.0

        for node_name, node in self.power_plant.nodes.items():
            if isinstance(node, Compressor):
                breakdown_exists = 'breakdown' in self.cost_specs.costs['power_plant']
                node_exists = breakdown_exists and node.label in self.cost_specs.costs['power_plant']['breakdown']
                if cost_type == 'custom_cost_breakdown' and node_exists:
                    pump_cost = self.cost_specs.costs['power_plant']['breakdown'][node.label]['function_def']['value']
                    # print(f"{node.label} Cost: ${pump_cost:,.2f}")
                    total_cost += pump_cost
                else:
                    PPI = self._PPI_pump
                    S_pump = self._pump_material_cost_multiplier
                    W_pump = node.P.val
                    pump_cost = PPI * S_pump * 1750 * (-1.34 * W_pump / 1.e3) ** 0.7
                    # print(f"{node.label} Cost: ${pump_cost:,.2f}")
                    total_cost += pump_cost

        # print(f"Total Pump Cost: ${total_cost:,.2f}")

        return total_cost

    def _compute_heat_exchanger_cost(self) -> float:
        """
        Computes the total cost of all heat exchangers in the power plant.

        The cost is calculated using the following formula:

            Cost = PPI_HX * (239 * A_HX + 13400)

        where:
            - PPI_HX: Producer Price Index for heat exchangers.
            - A_HX: Total heat exchanger surface area, calculated as the sum of:
                - A_preheater = Q_preheater / (U * dT_LMTD_preheater)
                - A_boiler = Q_boiler / (U * dT_LMTD_boiler)
                - A_recuperator = Q_recuperator / (U * dT_LMTD_recuperator)

        The method first checks if a user-defined cost breakdown is provided; if so,
        the cost is retrieved from the specifications. Otherwise, the cost is computed
        using the formula based on component heat transfer areas.

        Returns:
            float: Total heat exchanger cost in USD.

        Notes:
            - If a user-defined cost breakdown is available, it takes precedence over calculated values.
            - The heat transfer coefficient (U) is assumed to be 500 W/m²-K.
            - The log mean temperature difference (dT_LMTD) is calculated for each type of heat exchanger.

        Prints:
            - Individual heat exchanger areas and the total computed cost for debugging purposes.

        Raises:
            ValueError: If temperature differences for LMTD calculations are invalid.
        """
        cost_type = self.cost_specs.costs['power_plant']['type']
        U = 500.
        A_preheater = 0
        A_boiler = 0
        A_recuperator = 0
        total_cost = 0.0

        for node_name, node in self.power_plant.nodes.items():
            if isinstance(node, HeatExchanger):
                breakdown_exists = 'breakdown' in self.cost_specs.costs['power_plant']
                node_exists = breakdown_exists and node.label in self.cost_specs.costs['power_plant']['breakdown']
                if cost_type == 'custom_cost_breakdown' and node_exists:
                    hest_exchanger_cost = self.cost_specs.costs['power_plant']['breakdown'][node.label]['function_def']['value']
                    # print(f"Pump {node.label} Cost: ${hest_exchanger_cost:,.2f}")
                    total_cost += hest_exchanger_cost
                else:
                    component_config = self.power_plant.config.get(node_name, {})
                    subtype = component_config.get('Subtype', '').lower()

                    T_in1 = node.inl[0].T.val + 273.15
                    T_in2 = node.inl[1].T.val + 273.15
                    T_out1 = node.outl[0].T.val + 273.15
                    T_out2 = node.outl[1].T.val + 273.15

                    dT1 = T_in1 - T_out2
                    dT2 = -(T_in2 - T_out1)
                    dT_LMTD = (dT1 - dT2) / np.log(dT1 / dT2) if dT1 != dT2 else dT1

                    if subtype == 'preheater':
                        self._dT_LMTD_preheater = dT_LMTD
                        self._Q_preheater_total = -node.Q.val
                        A_preheater += self._Q_preheater_total / (U * self._dT_LMTD_preheater)

                    elif subtype == 'boiler':
                        self._dT_LMTD_boiler = dT_LMTD
                        self._Q_boiler_total = -node.Q.val
                        A_boiler += self._Q_boiler_total / (U * self._dT_LMTD_boiler)

                    elif subtype == 'recuperator':
                        self._dT_LMTD_recuperator = dT_LMTD
                        self._Q_recuperator_total = node.Q.val
                        A_recuperator += self._Q_recuperator_total / (U * self._dT_LMTD_recuperator)

        A_HX = A_preheater + A_boiler + A_recuperator

        if (A_HX == 0):
            A_HX = -13400.0/239.0

        return self._PPI_HX * (239. * A_HX + 13400.) + total_cost

    def _compute_cooler_condenser_cost(self) -> float:
        """
        Computes the total cost of all coolers and condensers in the power plant.

        The cost is calculated based on the following methodology:

            If user-defined cost breakdown is available, costs are retrieved from the
            provided specifications. Otherwise, the costs are computed using a regression model
            based on the heat load and cooling tower mode.

        Formula used for cost calculation:

            C_Ref_BAC = PPI * Q_Ref_BAC * TDC * (F_cooling * (C_cooling / 1e3) + (1 - F_cooling) * (C_condensing / 1e3))

            set_cost = C_Ref_BAC * (abs(Q_cooler + Q_condenser) / Q_Ref_BAC) ** 0.8

        where:
            - PPI: Producer Price Index for process equipment.
            - Q_Ref_BAC: Reference cooling capacity (1.0e6 kW).
            - TDC: Tower design coefficient based on fluid type and design.
            - C_cooling, C_condensing: Regression model coefficients.
            - F_cooling: Fraction of cooling in total heat load.

        Returns:
            float: Total cooler and condenser cost in USD.

        Notes:
            - Coolers and condensers are identified by their `Subtype` in the power plant configuration.
            - Cooling tower mode (`cooling_tower_mode`) can be 'WET' or 'DRY'.
            - User-defined cost breakdowns take precedence over calculated costs.
            - If the breakdown is not available, default coefficients are used for the cost model.

        Prints:
            - Individual cooler and condenser heat loads and their respective costs.
            - Total computed cost for debugging purposes.

        Raises:
            ValueError: If an invalid `cooling_tower_mode` or design type is specified.
        """
        cost_type = self.cost_specs.costs['power_plant']['type']
        total_cost_inp = 0.0
        total_cost = 0.0
        PPI = self._PPI_PE
        Q_Ref_BAC = 1.0e6
        sets = {}

        for node_name, node in self.power_plant.nodes.items():
            if isinstance(node, SimpleHeatExchanger):
                breakdown_exists = 'breakdown' in self.cost_specs.costs['power_plant']
                node_exists = breakdown_exists and node.label in self.cost_specs.costs['power_plant']['breakdown']
                if cost_type == 'custom_cost_breakdown' and node_exists:
                    cc_cost = self.cost_specs.costs['power_plant']['breakdown'][node.label]['function_def']['value']
                    # print(f" {node.label} Cost: ${cc_cost:,.2f}")
                    total_cost_inp += cc_cost
                else:
                    component_config = self.power_plant.config.get(node_name, {})
                    subtype = component_config.get('Subtype', '').lower()

                    if subtype in ['cooler', 'condenser']:
                        self._surface_cooling_tower_mode = component_config.get('cooling_tower_mode', 'WET').upper()
                        if self._surface_cooling_tower_mode not in ['WET', 'DRY']:
                            raise ValueError(f"Invalid cooling_tower_mode: {self._surface_cooling_tower_mode} for {node_name}")

                        design = component_config.get('design', 'CLOSED').upper()
                        if design not in ['CLOSED', 'OPEN']:
                            raise ValueError(f"Invalid design: {design} for {node_name}")

                        if self._surface_cooling_tower_mode == 'WET':
                            self._coeffs_cooling = [5.58e3, 0., -1.77e1, 1.96e2]
                            self._coeffs_condensing = [4.08e3, -1.54e-2, -1.24e1, 0.]
                        elif self._surface_cooling_tower_mode == 'DRY':
                            self._coeffs_cooling = [7.31e3, 0., 0., 1.23e3]
                            self._coeffs_condensing = [1.91e3, 0., 0., 0.]

                        TDC = self._get_tower_design_coefficient(fluid=self.cost_specs.fluid_name, design=design)

                        set_number = component_config.get('set_number', None)
                        if set_number is not None:
                            if set_number not in sets:
                                sets[set_number] = {'cooler': None, 'condenser': None, 'TDC': TDC}
                            if subtype == 'cooler':
                                sets[set_number]['cooler'] = node
                            elif subtype == 'condenser':
                                sets[set_number]['condenser'] = node

        for set_number, components in sets.items():
            Q_cooler = Q_condenser = 0.0

            if components['cooler'] is not None:
                Q_cooler = components['cooler'].Q.val
                # print(f"Set {set_number}: Cooler Q = {Q_cooler}")

            if components['condenser'] is not None:
                Q_condenser = components['condenser'].Q.val
                # print(f"Set {set_number}: Condenser Q = {Q_condenser}")

            TDC = components['TDC']
            C_cooling = self._BAC_regression_model(coeffs=self._coeffs_cooling)  # $/kW
            C_condensing = self._BAC_regression_model(coeffs=self._coeffs_condensing)
            F_cooling = abs(Q_cooler) / (abs(Q_cooler) + abs(Q_condenser) + 1e-10)
            C_Ref_BAC = PPI * Q_Ref_BAC * TDC * (F_cooling * (C_cooling / 1e3) + (1 - F_cooling) * (C_condensing / 1e3))
            set_cost = C_Ref_BAC * (abs(Q_cooler + Q_condenser) / Q_Ref_BAC) ** 0.8
            # print(f"Set {set_number}: Cost = {set_cost}")
            total_cost += set_cost

        # print(f"Total Cooler-Condenser Cost: {total_cost + total_cost_inp}")

        return total_cost + total_cost_inp

    def _BAC_regression_model(self, coeffs: list) -> float:
        """
        Baltimore Aircoil (BAC) regression model for cooling and condensing costs.

        Args:
            coeffs (list): Coefficients for the regression model.

        Returns:
            float: Cost estimate based on the regression model.

        Formula:
            Cost = a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach + dT_range)
        """
        a, b, c, d = coeffs
        T_ambient = self.power_plant.pp_specs.surface_temperature
        dT_approach = self.power_plant.pp_specs.approach_temperature
        dT_range = self.power_plant.pp_specs.temperature_range

        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach + dT_range)

    def _get_tower_design_coefficient(self, fluid: str, design: str) -> float:
        """
        Retrieves the cooling tower design coefficient based on fluid type and design.

        Args:
            fluid (str): The type of fluid (e.g., 'H2O', 'CO2').
            design (str): The design of the cooling tower (e.g., 'CLOSED', 'OPEN').

        Returns:
            float: Cooling tower design coefficient.

        Raises:
            ValueError: If the design or fluid type is unsupported.
        """
        if fluid == 'H2O':
            if design == 'CLOSED':
                return 1.0
            elif design == 'OPEN':
                return 0.252
            else:
                raise ValueError(f"Unsupported design '{design}' for fluid 'H2O'.")

        elif fluid == 'CO2':
            if design == 'CLOSED':
                return 1.2
            elif design == 'OPEN':
                raise ValueError(f"Design 'OPEN' is not supported for fluid '{fluid}'.")
            else:
                raise ValueError(f"Unsupported design '{design}' for fluid '{fluid}'.")

        else:
            raise ValueError(f"Unsupported fluid type '{fluid}'.")

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

    def compute_total_cost(self):
        """
        Computes the total cost of the power plant by aggregating individual component costs.

        The method calculates the total cost using predefined formulas or user-defined cost breakdowns.
        If cost breakdowns are provided, values are retrieved directly from the specifications; otherwise,
        the costs are computed using component-specific methods.

        The total cost is calculated based on the following formula:

            Total Cost (BEC) = TEC * (1 + X_CL + X_CM + X_ST + X_F)

        Where:
            - TEC: Total Equipment Cost = X_SE * total component costs.
            - X_SE: Secondary equipment cost multiplier (1.39).
            - X_CL: Construction labor cost multiplier (0.58).
            - X_CM: Construction material cost multiplier (0.11).
            - X_ST: Sales tax multiplier (0.00).
            - X_F: Equipment freight multiplier (0.04).
            - BEC: Bare Erected Cost.

        The method supports different cost computation methods based on the `cost_type`:

        1. **Default Predefined / User-Defined Breakdown:**
            - Computes cost by summing up individual component costs (turbine, pump, heat exchanger, cooler/condenser).
        2. **User-Defined Entire Power Plant:**
            - Fetches total cost from a user-defined function if specified.

        Returns:
            float: The total power plant cost in USD.

        Notes:
            - If a user-defined cost breakdown is provided, it takes precedence over computed costs.
            - Component costs include turbines, pumps, heat exchangers, and coolers/condensers.
            - If an unsupported cost type is specified, a `ValueError` is raised.

        Prints:
            - Power plant cost details when using the user-defined function.

        Raises:
            ValueError: If an unsupported cost type is specified.
        """
        cost_type = self.cost_specs.costs['power_plant']['type']

        if ((cost_type == 'default') or (cost_type == 'custom_cost_breakdown')):

            X_SE = 1.39  # secondary equipment cost
            X_CL = 0.58  # construction labor cost
            X_CM = 0.11  # construction material cost
            X_ST = 0.00  # sales tax
            X_F = 0.04  # equipment freight

            total_cost = 0.0
            total_cost += self.cost_specs.num_pp * self._compute_turbine_generator_costs()
            total_cost += self.cost_specs.num_pp * self._compute_pump_inj_cost()
            total_cost += self.cost_specs.num_pp * self._compute_heat_exchanger_cost()
            total_cost += self.cost_specs.num_pp * self._compute_cooler_condenser_cost()

            if (len(self.prod_pump_w_list) != 0):
                pump_P_ave = sum(self.prod_pump_w_list) / len(self.prod_pump_w_list)
                if pump_P_ave < 0:
                    total_cost += self.cost_specs.num_pp * self._compute_pump_prod_lineshaft_cost(sum(self.prod_pump_w_list) / len(self.prod_pump_w_list))

            total_cost_TEC = X_SE * total_cost
            total_cost_BEC = total_cost_TEC * (1.0 + X_CL + X_CM + X_ST + X_F)

            return self._X_PC * self._X_IC * total_cost_BEC

        elif cost_type == 'custom_entire_pp':
            if (self.cost_specs.costs['power_plant']['function_def']['type'] == 'Constant'):
                return self.cost_specs.costs['power_plant']['function_def']['value']
            elif (self.cost_specs.costs['power_plant']['function_def']['type'] == 'mathematical_expression'):
                return self.evaluated_funcs[self.cost_specs.costs['power_plant']['function']]
            else:
                raise ValueError(f"Unsupported custom function type: {self.cost_specs.costs['power_plant']['function_def']['type']}")

        else:
            raise ValueError(f"Unsupported power plant cost type: {cost_type}")

    def create_power_plant_with_averaged_results(self, average_fp_result):
        """
        Creates a new power plant instance with attributes set to their average values.

        The method deep copies the original power plant to avoid direct modifications and updates the attributes
        of various components (turbines, compressors, heat exchangers) based on the averaged results provided.

        Args:
            average_fp_result (dict): The averaged results from `calculate_and_set_average`.

        Returns:
            PowerPlant: A new PowerPlant object with updated attributes.

        Notes:
            - The function updates the power values for turbines and compressors.
            - It also updates the heat transfer values and inlet/outlet conditions for heat exchangers, coolers, and condensers.
            - The function ensures that the original power plant remains unmodified by using a deep copy.

        Raises:
            KeyError: If a required key is missing in `average_fp_result`.
        """
        from copy import deepcopy
        power_plant_new = deepcopy(self.power_plant)

        for node_name, node in power_plant_new.nodes.items():
            if isinstance(node, Turbine):
                node.P.val = average_fp_result.get(f'{node.label}_power_real', [0])[0]

            if isinstance(node, Compressor):
                node.P.val = average_fp_result.get(f'{node.label}_power_real', [0])[0]

            if isinstance(node, SimpleHeatExchanger):
                node.Q.val = average_fp_result.get(f'{node.label}_heat_transfer_real', [0])[0]

                if hasattr(node, 'inl') and len(node.inl) > 0:
                    node.inl[0].p.val = average_fp_result.get(f'{node.label}_inlet1_pressure', [0])[0]
                    node.inl[0].T.val = average_fp_result.get(f'{node.label}_inlet1_temperature', [0])[0]
                    node.inl[0].h.val = average_fp_result.get(f'{node.label}_inlet1_enthalpy', [0])[0]
                    node.inl[0].x.val = average_fp_result.get(f'{node.label}_inlet1_vapor_mass_fraction', [0])[0]
                if hasattr(node, 'outl') and len(node.outl) > 0:
                    node.outl[0].p.val = average_fp_result.get(f'{node.label}_outlet1_pressure', [0])[0]
                    node.outl[0].T.val = average_fp_result.get(f'{node.label}_outlet1_temperature', [0])[0]
                    node.outl[0].h.val = average_fp_result.get(f'{node.label}_outlet1_enthalpy', [0])[0]
                    node.outl[0].x.val = average_fp_result.get(f'{node.label}_outlet1_vapor_mass_fraction', [0])[0]

        return power_plant_new

    def compute_total_cost_with_averaged_results(self, average_fp_result):
        """
        Computes the total cost using averaged results by setting them directly to the power plant.

        This method creates a new power plant instance with attributes set to their average values and then
        calculates the total cost using the `PowerPlantCost` class.

        Args:
            average_fp_result (dict): The averaged results from `calculate_and_set_average`.

        Returns:
            float: The total cost of the power plant.

        Notes:
            - The function first creates a new power plant instance with averaged attributes.
            - It then calculates the net power and total cost using the `PowerPlantCost` class.

        Raises:
            KeyError: If a required key is missing in `average_fp_result`.
        """

        power_plant_new = self.create_power_plant_with_averaged_results(average_fp_result)
        flexible_power_plant_cost = PowerPlantCost(power_plant_new, self.cost_specs, self.evaluated_funcs, self.prod_pump_w_list)
        self.net_P = flexible_power_plant_cost.compute_net_power()
        self.thermal_power = flexible_power_plant_cost.thermal_power

        return flexible_power_plant_cost.compute_total_cost()
