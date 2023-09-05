class EconModelWells:

    def __init__(self,
                 specs: dict,
                 model_dict: dict):
        self._specs = specs
        self._PPI = self._specs.PPI
        self._X_IC, self._X_PC = specs.multipliers
        self._set_model_objects(model_dict)
        self._initialize_production_well_length()


    def _set_model_objects(self, model_dict) -> None:
        well_model_names = ['injection_well', 'production_well', 'production_well_pump', 'horizontal_well']
        for name in well_model_names:
            if name in model_dict.keys():
                if name == 'horizontal_well':
                    setattr(self, name, model_dict[name])
                else:
                    setattr(self, name, model_dict[name][0])
            else:
                setattr(self, name, None)

    def _initialize_production_well_length(self) -> None:
        if getattr(self, 'production_well_pump', None) != None:
            self.production_well.update_well_length(pump_well_length=self.production_well_pump.get_well_length())


    def _compute_num_wells(self) -> list: # per pattern
        NX, NY = self._specs.well_pattern_dimens
        if self._specs.well_pattern in ['DOUBLET', 'AGS']:
            num_total_inj = 1
            num_total_prd = 1
        elif self._specs.well_pattern == '5SPOT':
            num_total_inj = (NX+1) * (NY+1)
            num_total_prd = NX * NY
        elif self._specs.well_pattern == 'INVERTED_5SPOT':
            num_total_inj = NX * NY
            num_total_prd = (NX+1) * (NY+1)
        else:
            raise ValueErrortedError(f"well_pattern: {self._specs.well_pattern} is not supported")

        num_total_hrz = 0
        if self.horizontal_well != None:
            num_total_hrz = len(self.horizontal_well)

        return num_total_inj, num_total_prd, num_total_hrz


    def _compute_dC_CO2_well(self, d: float, L: float, fluid_name: str) -> float:
        if fluid_name != "CO2":
            return 0
        return self._X_IC * self._X_PC * self._PPI * (265. * d * L + 133. * L)


    def _compute_wells_cost_by_type(self, well_type: str, num_wells: int) -> float:
        if well_type == 'injection_well' and self._specs.project_maturity == 'BROWN_FIELD':
            return 0
        well_model = getattr(self, well_type, None)
        if well_model == None:
            return 0.
        if well_type == 'horizontal_well':
            self._specs.horizontal_well_cost_multiplier = 1.0
            val = 0.
            for h_well_model in well_model:
                val += self.compute_individual_well_cost(L=h_well_model.get_well_length(),
                                                         d=h_well_model.get_diameter(),
                                                         pos=h_well_model.get_probability_of_success(),
                                                         fluid_name=self._specs.fluid_name)
            return num_wells * self._specs.horizontal_well_cost_multiplier * val
        else:
            return num_wells * self.compute_individual_well_cost(L=well_model.get_well_length(),
                                                                 d=well_model.get_diameter(),
                                                                 pos=well_model.get_probability_of_success(),
                                                                 fluid_name=self._specs.fluid_name)


    def compute_individual_well_cost(self, L: float=None, d: float=0., pos: float=0., fluid_name: str = "H2O") -> float:
        if L == None:
            if self.injection_well != None:
                L = self.injection_well.get_well_length()
            else:
                if self.production_well == None:
                    raise RuntimeError(f"well_length cannot be obtained.")
                L = self.production_well.get_well_length()
                if self.production_well_pump != None:
                    L += self.production_well_pump.get_well_length()
        C_well = self._X_IC * self._X_PC * self._PPI * (0.105 * L ** 2 + 1776. * d * L + 275300.) # well cost (base line)
        dC_CO2_well = self._compute_dC_CO2_well(d, L, fluid_name) # adjustment for CO2
        return (C_well + dC_CO2_well) / pos


    def execute(self) -> float:
        num_total_inj, num_total_prod, num_total_hrz = self._compute_num_wells()
        C_inj = self._compute_wells_cost_by_type(well_type='injection_well', num_wells=num_total_inj)
        C_prd = self._compute_wells_cost_by_type(well_type='production_well', num_wells=num_total_prod)
        C_hrz = self._compute_wells_cost_by_type(well_type='horizontal_well', num_wells=num_total_hrz)
        return C_inj + C_prd + C_hrz
