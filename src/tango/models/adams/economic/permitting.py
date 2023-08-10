class EconModelPermitting:

    def __init__(self,
                 specs: dict,
                 well_econ_model: object):
        self._specs = specs
        self._PPI_permitting = self._specs.PPI_permitting
        self._PPI_OnGs = self._specs.PPI_OnGs
        self._X_IC, self._X_PC = self._specs.multipliers
        self._well_econ_model = well_econ_model


    def _compute_dCO2_permitting(self) -> float:
        if self._specs.fluid_name != 'CO2':
            return 0
        X_IC, X_PC = self._X_IC, self._X_PC
        PPI = self._PPI_permitting
        AMA = self._specs.active_monitoring_area
        return X_IC * X_PC * PPI * 45000. * (1. / 1.e6) * AMA


    def _compute_dCO2_monitoring(self) -> float:
        if self._specs.fluid_name != 'CO2':
            return 0
        X_IC, X_PC = self._X_IC, self._X_PC
        PPI = self._PPI_OnGs
        AMA = self._specs.active_monitoring_area
        C_surface_monitoring = X_IC * X_PC * PPI * 138000. * (1. / 1.e6) * AMA
        C_monitoring_well = self._specs.num_patterns * self._well_econ_model.compute_individual_well_cost(L=self._specs.reservoir_depth,
                                                                                                          d=self._specs.monitoring_well_diameter,
                                                                                                          pos=self._specs.monitoring_well_probability_of_success)
        return C_surface_monitoring + C_monitoring_well

    def execute(self) -> float:

        if self._specs.project_maturity == 'BROWN_FIELD':
            return 0

        C_permitting = self._X_IC * self._X_PC * self._PPI_permitting * 665700.
        dC_CO2_permitting = self._compute_dCO2_permitting()
        dC_CO2_monitoring = self._compute_dCO2_monitoring()

        return C_permitting + dC_CO2_permitting + dC_CO2_monitoring