class EconUnitPermitting:
    """
    Represents the economic unit for permitting and monitoring costs in well operations.

    This class calculates permitting and monitoring costs based on specifications, fluid properties,
    and project maturity, accounting for CO2-specific costs when applicable.

    Attributes:
        _specs (dict): Specifications for the economic calculations.
        _PPI_permitting (float): Permitting Producer Price Index (PPI) multiplier.
        _PPI_OnGs (float): On-ground monitoring PPI multiplier.
        _X_IC (float): Inflation correction multiplier.
        _X_PC (float): Project contingency multiplier.
        _well_econ_unit (object): Reference to the well's economic unit for cost calculations.
    """

    def __init__(self, specs: dict, well_econ_unit: object):
        """
        Initializes a new instance of the EconUnitPermitting class.

        Args:
            specs (dict): Specifications for permitting and monitoring costs.
            well_econ_unit (object): Reference to the associated well economic unit.
        """
        self._specs = specs
        self._PPI_permitting = self._specs.PPI_permitting
        self._PPI_OnGs = self._specs.PPI_OnGs
        self._X_IC, self._X_PC = self._specs.multipliers
        self._well_econ_unit = well_econ_unit

    def _compute_dCO2_permitting(self) -> float:
        r"""
        Computes the incremental permitting cost for CO2 operations.

        This method calculates the additional permitting costs specific to CO2 fluid operations
        based on the active monitoring area (AMA) and economic multipliers.

        Returns:
            float: The incremental permitting cost for CO2 operations.

        Formula:
            .. math::
                \Delta C_{\text{CO2, permitting}} = X_{IC} \cdot X_{PC} \cdot PPI_{\text{permitting}} \cdot 45000
                \cdot \frac{1}{10^6} \cdot AMA

        Where:
            - \( X_{IC} \): Inflation correction multiplier.
            - \( X_{PC} \): Project contingency multiplier.
            - \( PPI_{\text{permitting}} \): Permitting PPI multiplier.
            - \( AMA \): Active monitoring area (m²).
        """
        if self._specs.fluid_name != 'CO2':
            return 0
        X_IC, X_PC = self._X_IC, self._X_PC
        PPI = self._PPI_permitting
        AMA = self._specs.active_monitoring_area
        return X_IC * X_PC * PPI * 45000. * (1. / 1.e6) * AMA

    def _compute_dCO2_monitoring(self) -> float:
        r"""
        Computes the incremental monitoring cost for CO2 operations.

        This method calculates the additional costs for surface monitoring and monitoring wells,
        specifically for CO2 operations.

        Returns:
            float: The incremental monitoring cost for CO2 operations.

        Formula:
            .. math::

                C_{\text{surface, monitoring}} = X_{IC} \cdot X_{PC} \cdot PPI_{\text{OnGs}} \cdot 138000
                \cdot \frac{1}{10^6} \cdot AMA

            .. math::

                C_{\text{monitoring, well}} = N_{\text{patterns}} \cdot C_{\text{well, unit}}(d, pos)

            Total Monitoring Cost:
            .. math::

                \Delta C_{\text{CO2, monitoring}} = C_{\text{surface, monitoring}} + C_{\text{monitoring, well}}

        Where:
            - \( X_{IC} \): Inflation correction multiplier.
            - \( X_{PC} \): Project contingency multiplier.
            - \( PPI_{\text{OnGs}} \): On-ground PPI multiplier.
            - \( AMA \): Active monitoring area (m²).
            - \( N_{\text{patterns}} \): Number of well patterns.
            - \( C_{\text{well, unit}}(d, pos) \): Cost of an individual monitoring well based on diameter (\( d \)) and probability of success (\( pos \)).
        """
        if self._specs.fluid_name != 'CO2':
            return 0
        X_IC, X_PC = self._X_IC, self._X_PC
        PPI = self._PPI_OnGs
        AMA = self._specs.active_monitoring_area
        C_surface_monitoring = X_IC * X_PC * PPI * 138000. * (1. / 1.e6) * AMA
        C_monitoring_well = self._specs.num_patterns * self._well_econ_unit.compute_individual_well_cost(
            d=[self._specs.monitoring_well_diameter],
            pos=self._specs.monitoring_well_probability_of_success
        )
        return C_surface_monitoring + C_monitoring_well

    def execute(self) -> float:
        r"""
        Executes the economic calculations for permitting and monitoring costs.

        This method calculates the total costs based on the type of permitting cost configuration:
        - If `type` is `default_predefined`, it calculates the permitting and monitoring costs.
        - If `type` is `user_defined`, it directly returns the value from `function_def`.

        Returns:
            float: The total cost of permitting and monitoring.

        Formula for default_predefined:
            .. math::
                C_{\text{total}} = C_{\text{permitting}} + \Delta C_{\text{CO2, permitting}}
                + \Delta C_{\text{CO2, monitoring}}

            Where:
            .. math::
                C_{\text{permitting}} = X_{IC} \cdot X_{PC} \cdot PPI_{\text{permitting}} \cdot 665700

        For `user_defined`:
            The cost is directly returned from the user-defined function value:
            .. math::
                C_{\text{total}} = \text{function\_def}[\text{"value"}]
        """
        if self._specs.project_maturity == 'BROWN_FIELD':
            return 0

        permitting_cost_type = self._specs.costs['permitting']['type']

        if permitting_cost_type == 'default_predefined':
            C_permitting = self._X_IC * self._X_PC * self._PPI_permitting * 665700.
            dC_CO2_permitting = self._compute_dCO2_permitting()
            dC_CO2_monitoring = self._compute_dCO2_monitoring()
            return C_permitting + dC_CO2_permitting + dC_CO2_monitoring

        elif permitting_cost_type == 'user_defined':
            return self._specs.costs['permitting']['function_def']['value']

        else:
            raise ValueError(f"Unsupported permitting cost type: {permitting_cost_type}")
