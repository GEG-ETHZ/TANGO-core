class EconUnitWells:
    """
    Represents the economic unit for well-related costs in a geothermal or hydrocarbon project.

    This class manages the calculation of well costs, including the costs of injection,
    production, and horizontal wells. It handles well pattern configurations, CO2-specific costs,
    and project maturity considerations.

    Attributes:
        _specs (dict): Specifications for the economic unit.
        _PPI (float): Producer Price Index (PPI) multiplier.
        _X_IC (float): Inflation correction multiplier.
        _X_PC (float): Project contingency multiplier.
        injection_well (object): Injection well object.
        production_well (object): Production well object.
        production_well_pump (object): Production well pump object.
        horizontal_well (list): List of horizontal well objects.
    """

    def __init__(self, specs: dict, unit_dict: dict):
        """
        Initializes a new instance of the EconUnitWells class.

        Args:
            specs (dict): Specifications for the well-related economic calculations.
            unit_dict (dict): Dictionary containing well-related unit objects.
        """
        self._specs = specs
        self._PPI = self._specs.PPI
        self._X_IC, self._X_PC = specs.multipliers
        self._set_unit_objects(unit_dict)
        self._initialize_production_well_length()

    def _set_unit_objects(self, unit_dict) -> None:
        """
        Sets unit objects for different types of wells.

        Args:
            unit_dict (dict): Dictionary containing well unit objects.

        Process:
            - Assigns objects for injection, production, production well pumps, and horizontal wells.
            - If no object is found for a well type, sets it to `None`.
        """
        well_unit_names = ['injection_well', 'production_well', 'production_well_pump', 'horizontal_well']
        for name in well_unit_names:
            if name in unit_dict.keys():
                if name == 'horizontal_well':
                    setattr(self, name, unit_dict[name])
                else:
                    setattr(self, name, unit_dict[name][0])
            else:
                setattr(self, name, None)

    def _initialize_production_well_length(self) -> None:
        """
        Updates the production well length based on the associated production well pump length.

        Process:
            - If a production well pump exists, updates the production well's length accordingly.
        """
        if getattr(self, 'production_well_pump', None) is not None:
            self.production_well.update_well_length(
                pump_well_length=self.production_well_pump.get_well_length()
            )

    def _compute_num_wells(self) -> list:
        r"""
        Computes the number of wells for the specified well pattern.

        Returns:
            list: Number of injection, production, and horizontal wells.

        Formula:
            - For 'DOUBLET' or 'AGS':
              .. math::

                  \text{num\_total\_inj} = 1, \text{num\_total\_prd} = 1

            - For '5SPOT':
              .. math::

                  \text{num\_total\_inj} = (N_X + 1)(N_Y + 1), \text{num\_total\_prd} = N_X N_Y

            - For 'INVERTED\_5SPOT':
              .. math::

                  \text{num\_total\_inj} = N_X N_Y, \text{num\_total\_prd} = (N_X + 1)(N_Y + 1)

        Raises:
            ValueError: If the well pattern is not supported.
        """
        NX, NY = self._specs.well_pattern_dimens
        if self._specs.well_pattern in ['DOUBLET', 'AGS']:
            num_total_inj = 1
            num_total_prd = 1
        elif self._specs.well_pattern == '5SPOT':
            num_total_inj = (NX + 1) * (NY + 1)
            num_total_prd = NX * NY
        elif self._specs.well_pattern == 'INVERTED_5SPOT':
            num_total_inj = NX * NY
            num_total_prd = (NX + 1) * (NY + 1)
        else:
            raise ValueError(f"well_pattern: {self._specs.well_pattern} is not supported")

        num_total_hrz = 0
        if self.horizontal_well is not None:
            num_total_hrz = len(self.horizontal_well)

        return num_total_inj, num_total_prd, num_total_hrz

    def _compute_dC_CO2_well(self, d: float, L: float, fluid_name: str) -> float:
        r"""
        Computes the incremental cost of a well for CO2 operations.

        Args:
            d (float): Well diameter (m).
            L (float): Well length (m).
            fluid_name (str): Name of the fluid.

        Returns:
            float: Incremental CO2-specific cost.

        Formula:
            .. math::
                \Delta C_{\text{CO2, well}} = X_{IC} \cdot X_{PC} \cdot PPI \cdot (265 d L + 133 L)
        """
        if fluid_name != "CO2":
            return 0
        return self._X_IC * self._X_PC * self._PPI * (265. * d * L + 133. * L)

    def _compute_wells_cost_by_type(self, well_type: str, num_wells: int) -> float:
        """
        Computes the total cost of wells by type.

        Args:
            well_type (str): Type of the well ('injection_well', 'production_well', 'horizontal_well').
            num_wells (int): Number of wells of the specified type.

        Returns:
            float: Total cost of wells of the specified type.

        Process:
            - Uses predefined cost models (e.g., 'gengeo', 'ppgd', 'halliburton') to determine cost multipliers.
            - For horizontal wells, computes costs iteratively for each well unit.
            - For injection and production wells, computes costs directly.

        Raises:
            ValueError: If the specified cost model is not supported.

        Notes:
            - Injection wells in 'BROWN_FIELD' projects incur no cost.
        """
        if well_type == 'injection_well' and self._specs.project_maturity == 'BROWN_FIELD':
            return 0
        well_unit = getattr(self, well_type, None)

        well_cost_mapping = {
            'gengeo': 1.0,
            'ppgd': 1.0,
            'halliburton': 2500.0 / 1500.0,
            'st_gallen': 2889.0 / 1500.0,
            'bavaria': 3333.0 / 1500.0,
            'swiss': 2907.0 / 1500.0,
        }

        if self._specs.well_cost_model in well_cost_mapping:
            h_factor = well_cost_mapping[self._specs.well_cost_model]
        else:
            raise ValueError(f"The provided well_cost_model: {self._specs.well_cost_model} is not supported")

        if well_unit is None:
            return 0.0
        if well_type == 'horizontal_well':
            val = 0.0
            for h_well_unit in well_unit:
                val += h_factor * self.compute_individual_well_cost(
                    L=[h_well_unit.get_well_length()],
                    d=[h_well_unit.get_diameter()],
                    pos=h_well_unit.get_probability_of_success(),
                    fluid_name=self._specs.fluid_name
                )
            return num_wells * val
        elif well_type == 'injection_well':
            return num_wells * self.compute_individual_well_cost(
                L=self.injection_well.length_list,
                d=self.injection_well.diameter_list,
                pos=well_unit.get_probability_of_success(),
                fluid_name=self._specs.fluid_name
            )
        else:
            return num_wells * self.compute_individual_well_cost(
                L=self.production_well.length_list,
                d=self.production_well.diameter_list,
                pos=well_unit.get_probability_of_success(),
                fluid_name=self._specs.fluid_name
            )

    def compute_individual_well_cost(
        self, L: list = None, d: list = 0.0, pos: float = 0.0, fluid_name: str = "H2O"
    ) -> float:
        r"""
        Computes the cost of an individual well.

        This method calculates the cost of a well based on its length, diameter, probability of success,
        and the specified cost model. CO2-specific costs are also included if the fluid name is "CO2".

        Args:
            L (list, optional): List of well lengths (m). Defaults to `None`, in which case the length is derived
                from the injection or production well.
            d (list): List of well diameters (m). Defaults to 0.0.
            pos (float): Probability of success (0 to 1). Defaults to 0.0.
            fluid_name (str): Name of the fluid (e.g., "H2O", "CO2"). Defaults to "H2O".

        Returns:
            float: Total cost of the well (currency units).

        Raises:
            RuntimeError: If well lengths cannot be determined.
            ValueError: If the lengths of `L` and `d` do not match.
            ValueError: If the specified well cost model is not supported.

        Formula:
            Well costs are computed using the formulas defined in `well_cost_formulas`. For example:
            - For 'gengeo':

              .. math::

                  C_{\text{well}} = X_{IC} \cdot X_{PC} \cdot PPI \cdot (0.105 \cdot L^2 + 1776 \cdot d \cdot L + 275300)

            CO2-specific incremental costs are added:

            .. math::

                C_{\text{CO2}} = X_{IC} \cdot X_{PC} \cdot PPI \cdot (265 \cdot d \cdot L + 133 \cdot L)

        Process:
            - Determine well lengths `L` from the injection or production well if not explicitly provided.
            - Validate that `L` and `d` have the same length.
            - Compute costs section by section for each length and diameter.
            - Add CO2-specific costs if applicable.
            - Normalize total cost by the probability of success.
        """
        if L is None:
            if self.injection_well is not None:
                L = [self.injection_well.get_well_length()]
            else:
                if self.production_well is None:
                    raise RuntimeError("well_length cannot be obtained.")
                L = [self.production_well.get_well_length()]
                if self.production_well_pump is not None:
                    L += self.production_well_pump.get_well_length()

        well_cost_formulas = {
            'gengeo': lambda Ls, ds, self: self._X_IC * self._X_PC * self._PPI * (0.105 * Ls**2 + 1776.0 * ds * Ls + 275300.0),
            'halliburton': lambda Ls, ds, self: 1500.0 * Ls,
            'st_gallen': lambda Ls, ds, self: 1500.0 * Ls,
            'bavaria': lambda Ls, ds, self: 1500.0 * Ls,
            'swiss': lambda Ls, ds, self: 1500.0 * Ls,
            'ppgd': lambda Ls, ds, self: 969.0 * Ls,
        }

        if len(L) != len(d):
            raise ValueError("Length of well_length_list must be the same as well_diameter_list")

        total_cost = 0.0
        for Ls, ds in zip(L, d):
            if self._specs.well_cost_model in well_cost_formulas:
                C_well_section = well_cost_formulas[self._specs.well_cost_model](Ls, ds, self)
            else:
                raise ValueError(f"The provided well_cost_model: {self._specs.well_cost_model} is not supported")

            dC_CO2_well_section = self._compute_dC_CO2_well(ds, Ls, fluid_name)
            total_cost += C_well_section + dC_CO2_well_section

        return total_cost / pos

    def execute(self, evaluated_funcs) -> float:
        r"""
        Computes the total cost of all wells (injection, production, and horizontal).

        This method calculates the total well costs based on the type of configuration:
        - If `type` is `default`, it calculates the well costs.
        - If `type` is `custom`, it directly returns the value from `function_def`.

        Returns:
            float: Total cost of all wells (currency units).

        Formula for default:
            .. math::
                C_{\text{total}} = C_{\text{inj}} + C_{\text{prd}} + C_{\text{hrz}}

            Where:
                - \( C_{\text{inj}} \): Total cost of injection wells.
                - \( C_{\text{prd}} \): Total cost of production wells.
                - \( C_{\text{hrz}} \): Total cost of horizontal wells.
        """
        well_cost_type = self._specs.costs['wells']['type']

        if well_cost_type == 'default':
            num_total_inj, num_total_prod, num_total_hrz = self._compute_num_wells()
            C_inj = self._compute_wells_cost_by_type(well_type='injection_well', num_wells=num_total_inj)
            C_prd = self._compute_wells_cost_by_type(well_type='production_well', num_wells=num_total_prod)
            C_hrz = self._compute_wells_cost_by_type(well_type='horizontal_well', num_wells=num_total_hrz)
            return C_inj + C_prd + C_hrz

        elif well_cost_type == 'custom':
            if (self._specs.costs['wells']['function_def']['type'] == 'Constant'):
                return self._specs.costs['wells']['function_def']['value']
            elif (self._specs.costs['wells']['function_def']['type'] == 'mathematical_expression'):
                return evaluated_funcs[self._specs.costs['wells']['function']]
            else:
                raise ValueError(f"Unsupported custom function type: {self._specs.costs['wells']['function_def']['type']}")

        else:
            raise ValueError(f"Unsupported well cost type: {well_cost_type}")
