class EconModelExploration:

    def __init__(self,
                 specs: dict,
                 well_econ_model: object):
        self.specs = specs
        self.PPI = self.specs.PPI
        self.X_IC, self.X_PC = self.specs.multipliers
        self.well_econ_model = well_econ_model


    def get_dCO2_modeling(self) -> float:
        if self.specs.fluid_name != 'CO2':
            return 0
        return self.X_IC * self.X_PC * self.PPI * 44800 * (1/1e6) * self.specs.active_monitoring_area


    def get_dCO2_characterization(self) -> float:
        # if self.specs.fluid_name != 'CO2':
        #     return 0
        num_wells = self.specs.num_characterization_wells
        pos = self.well_econ_model.production_well.specs.probability_of_success
        C_characterization_well = self.well_econ_model.get_individual_well_cost(L=self.specs.reservoir_depth,
                                                                                d=self.well_econ_model.production_well.specs.diameter,
                                                                                pos=1.0)
        return 0.2 * num_wells * C_characterization_well / pos


    def execute(self) -> float:

        if self.specs.project_maturity == 'BROWN_FIELD':
            return 0

        C_modeling = self.X_IC * self.X_PC * self.PPI * 508000
        dC_CO2_modeling = self.get_dCO2_modeling()
        dC_CO2_characterization = self.get_dCO2_characterization()

        return C_modeling + dC_CO2_modeling + dC_CO2_characterization
