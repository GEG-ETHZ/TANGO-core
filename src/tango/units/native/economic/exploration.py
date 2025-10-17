class EconUnitExploration:
    """
    Represents the economic unit for exploration activities in well operations.

    This class calculates exploration costs, including CO2-specific modeling and characterization costs,
    based on well specifications and economic multipliers.

    Attributes:
        _specs (dict): Specifications for exploration and related economic calculations.
        _PPI (float): Producer Price Index (PPI) multiplier for exploration.
        _X_IC (float): Inflation correction multiplier.
        _X_PC (float): Project contingency multiplier.
        _well_econ_unit (object): Reference to the well's economic unit for cost calculations.
    """

    def __init__(self, specs: dict, well_econ_unit: object):
        """
        Initializes a new instance of the EconUnitExploration class.

        Args:
            specs (dict): Specifications for exploration and modeling costs.
            well_econ_unit (object): Reference to the associated well economic unit.
        """
        self._specs = specs
        self._PPI = self._specs.PPI
        self._X_IC, self._X_PC = self._specs.multipliers
        self._well_econ_unit = well_econ_unit

    def _compute_dCO2_modeling(self) -> float:
        r"""
        Computes the incremental modeling cost for CO2 operations.

        This method calculates additional modeling costs specific to CO2 fluid operations
        based on the active monitoring area (AMA) and economic multipliers.

        Returns:
            float: The incremental modeling cost for CO2 operations.

        Formula:
            .. math::
                \Delta C_{\text{CO2, modeling}} = X_{IC} \cdot X_{PC} \cdot PPI \cdot 44800
                \cdot \frac{1}{10^6} \cdot AMA

        Where:
            - \( X_{IC} \): Inflation correction multiplier.
            - \( X_{PC} \): Project contingency multiplier.
            - \( PPI \): Producer Price Index multiplier.
            - \( AMA \): Active monitoring area (m²).
        """
        if self._specs.fluid_name != 'CO2':
            return 0

        return self._X_IC * self._X_PC * self._PPI * 44800 * (1/1e6) * self._specs.active_monitoring_area

    def _compute_dCO2_characterization(self) -> float:
        r"""
        Computes the incremental characterization cost for CO2 operations.

        This method calculates the cost of characterization wells specific to CO2 fluid operations,
        accounting for the probability of success and the number of wells required.

        Returns:
            float: The incremental characterization cost for CO2 operations.

        Formula:
            .. math::
                \Delta C_{\text{CO2, characterization}} = 0.2 \cdot N_{\text{wells}}
                \cdot \frac{C_{\text{well, unit}}}{P_{\text{success}}}

        Where:
            - \( N_{\text{wells}} \): Number of characterization wells.
            - \( C_{\text{well, unit}} \): Cost of an individual characterization well.
            - \( P_{\text{success}} \): Probability of success for production wells.
        """
        if (self._specs.fluid_name != 'CO2' or self._specs.well_pattern == 'AGS'):
            return 0
        num_wells = self._specs.num_characterization_wells
        pos = self._well_econ_unit.production_well.get_probability_of_success()
        C_characterization_well = self._well_econ_unit.compute_individual_well_cost(
            d=[self._well_econ_unit.production_well.get_diameter()],
            pos=1.0
        )

        return 0.2 * num_wells * C_characterization_well / pos

    def execute(self, evaluated_funcs) -> float:
        r"""
        Executes the economic calculations for exploration activities.

        This method calculates the total exploration costs based on the type of configuration:
        - If `type` is `default`, it calculates exploration costs.
        - If `type` is `custom`, it directly returns the value from `function_def`.

        Returns:
            float: The total cost of exploration.

        Formula for default:
            .. math::
                C_{\text{total}} = C_{\text{modeling}} + \Delta C_{\text{CO2, modeling}}
                + \Delta C_{\text{CO2, characterization}}

            Where:
                .. math::
                    C_{\text{modeling}} = X_{IC} \cdot X_{PC} \cdot PPI \cdot 508000
        """
        if self._specs.project_maturity == 'BROWN_FIELD':
            return 0

        exploration_cost_type = self._specs.costs['exploration']['type']

        if exploration_cost_type == 'default':
            C_modeling = self._X_IC * self._X_PC * self._PPI * 508000
            dC_CO2_modeling = self._compute_dCO2_modeling()

            if self._well_econ_unit.production_well is not None:
                dC_CO2_characterization = self._compute_dCO2_characterization()
            else:
                dC_CO2_characterization = 0.0

            return C_modeling + dC_CO2_modeling + dC_CO2_characterization

        elif exploration_cost_type == 'custom':
            if (self._specs.costs['exploration']['function_def']['type'] == 'Constant'):
                return self._specs.costs['exploration']['function_def']['value']
            elif (self._specs.costs['exploration']['function_def']['type'] == 'mathematical_expression'):
                return evaluated_funcs[self._specs.costs['exploration']['function']]
            else:
                raise ValueError(f"Unsupported custom function type: {self._specs.costs['exploration']['function_def']['type']}")

        else:
            raise ValueError(f"Unsupported exploration cost type: {exploration_cost_type}")
