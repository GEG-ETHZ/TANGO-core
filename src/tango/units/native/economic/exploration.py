class EconUnitExploration:

    def __init__(self,
                 specs: dict,
                 well_econ_unit: object):
        self._specs = specs
        self._PPI = self._specs.PPI
        self._X_IC, self._X_PC = self._specs.multipliers
        self._well_econ_unit = well_econ_unit


    def _compute_dCO2_modeling(self) -> float:
        if self._specs.fluid_name != 'CO2':
            return 0
        return self._X_IC * self._X_PC * self._PPI * 44800 * (1/1e6) * self._specs.active_monitoring_area


    def _compute_dCO2_characterization(self) -> float:
        if self._specs.fluid_name != 'CO2':
            return 0
        num_wells = self._specs.num_characterization_wells
        pos = self._well_econ_unit.production_well.get_probability_of_success()
        C_characterization_well = self._well_econ_unit.compute_individual_well_cost(d=[self._well_econ_unit.production_well.get_diameter()],
                                                                                     pos=1.0)
        return 0.2 * num_wells * C_characterization_well / pos


    def execute(self) -> float:

        if self._specs.project_maturity == 'BROWN_FIELD':
            return 0

        C_modeling = self._X_IC * self._X_PC * self._PPI * 508000
        dC_CO2_modeling = self._compute_dCO2_modeling()

        if (self._well_econ_unit.production_well != None):
            dC_CO2_characterization = self._compute_dCO2_characterization()
        else:
            dC_CO2_characterization = 0.0

        return C_modeling + dC_CO2_modeling + dC_CO2_characterization
