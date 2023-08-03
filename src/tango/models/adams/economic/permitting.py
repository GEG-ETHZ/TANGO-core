class EconModelPermitting:

    def __init__(self,
                 specs: dict,
                 well_econ_model: object):
        self.specs = specs
        self.PPI_permitting = self.specs.PPI_permitting
        self.PPI_OnGs = self.specs.PPI_OnGs
        self.X_IC, self.X_PC = self.specs.multipliers
        self.well_econ_model = well_econ_model


    def get_dCO2_permitting(self) -> float:
        if self.specs.fluid_name != 'CO2':
            return 0
        X_IC, X_PC = self.X_IC, self.X_PC
        PPI = self.PPI_permitting
        AMA = self.specs.active_monitoring_area
        return X_IC * X_PC * PPI * 45000. * (1. / 1.e6) * AMA


    def get_dCO2_monitoring(self) -> float:
        if self.specs.fluid_name != 'CO2':
            return 0
        X_IC, X_PC = self.X_IC, self.X_PC
        PPI = self.PPI_OnGs
        AMA = self.specs.active_monitoring_area
        C_surface_monitoring = X_IC * X_PC * PPI * 138000. * (1. / 1.e6) * AMA
        C_monitoring_well = self.specs.num_patterns * self.well_econ_model.get_individual_well_cost(L=self.specs.reservoir_depth,
                                                                                                    d=self.specs.monitoring_well_diameter,
                                                                                                    pos=self.specs.monitoring_well_probability_of_success)
        return C_surface_monitoring + C_monitoring_well

    def execute(self) -> float:

        if self.specs.project_maturity == 'BROWN_FIELD':
            return 0

        C_permitting = self.X_IC * self.X_PC * self.PPI_permitting * 665700.
        dC_CO2_permitting = self.get_dCO2_permitting()
        dC_CO2_monitoring = self.get_dCO2_monitoring()

        return C_permitting + dC_CO2_permitting + dC_CO2_monitoring