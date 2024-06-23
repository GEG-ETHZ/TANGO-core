class EconUnitWells:

    def __init__(self,
                 specs: dict,
                 unit_dict: dict):
        self._specs = specs
        self._PPI = self._specs.PPI
        self._X_IC, self._X_PC = specs.multipliers
        self._set_unit_objects(unit_dict)
        self._initialize_production_well_length()
        self.well_length_list = specs.well_length_list
        self.well_diameter_list = specs.well_diameter_list
        # print(self.well_diameter_list)


    def _set_unit_objects(self, unit_dict) -> None:
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
            # print(self.horizontal_well)

        return num_total_inj, num_total_prd, num_total_hrz


    # def _compute_dC_CO2_well(self, d: float, L: float, fluid_name: str) -> float:
    #     if self._specs.wellbore_solver == "native":
    #         if fluid_name != "CO2":
    #             return 0
    #         return self._X_IC * self._X_PC * self._PPI * (265. * d * L + 133. * L)
    #     elif self._specs.wellbore_solver == "external":
    #         if len(self.well_length_list) != len(self.well_diameter_list):
    #             raise ValueError("Length of well_length_list must be the same as well_diameter_list")
    #
    #         cost = 0.0
    #         for L, d in zip(self.well_length_list, self.well_diameter_list):
    #             cost += self._X_IC * self._X_PC * self._PPI * (265. * d * L + 133. * L)
    #         return cost
    #     else:
    #         raise ValueError(f"The provided wellbore_solver: {self._specs.well_cost_model} is not supported")

    def _compute_dC_CO2_well(self, d: float, L: float, fluid_name: str) -> float:
        print(fluid_name)
        if fluid_name != "CO2":
            return 0
        return self._X_IC * self._X_PC * self._PPI * (265. * d * L + 133. * L)


    def _compute_wells_cost_by_type(self, well_type: str, num_wells: int) -> float:
        if well_type == 'injection_well' and self._specs.project_maturity == 'BROWN_FIELD':
            return 0
        well_unit = getattr(self, well_type, None)

        well_cost_mapping = {
            'gengeo': 1.0,
            'ppgd': 1.0,
            'halliburton': 2500.0/1500.0,
            'st_gallen': 2889.0/1500.0,
            'bavaria': 3333.0/1500.0,
            'swiss': 2907.0/1500.0,
        }

        if self._specs.well_cost_model in well_cost_mapping:
            h_factor = well_cost_mapping[self._specs.well_cost_model]
        else:
            raise ValueError(f"The provided well_cost_model: {self._specs.well_cost_model} is not supported")

        if well_unit == None:
            return 0.
        if well_type == 'horizontal_well':
            val = 0.
            for h_well_unit in well_unit:
                val += h_factor * self.compute_individual_well_cost(L=h_well_unit.get_well_length(),
                                                         d=h_well_unit.get_diameter(),
                                                         pos=h_well_unit.get_probability_of_success(),
                                                         fluid_name=self._specs.fluid_name)
            return num_wells * val
        else:
            return num_wells * self.compute_individual_well_cost(L=well_unit.get_well_length(),
                                                                 d=well_unit.get_diameter(),
                                                                 pos=well_unit.get_probability_of_success(),
                                                                 fluid_name=self._specs.fluid_name)


    # def compute_individual_well_cost(self, L: float=None, d: float=0., pos: float=0., fluid_name: str = "H2O") -> float:
    #     if L == None:
    #         if self.injection_well != None:
    #             L = self.injection_well.get_well_length()
    #         else:
    #             if self.production_well == None:
    #                 raise RuntimeError(f"well_length cannot be obtained.")
    #             L = self.production_well.get_well_length()
    #             if self.production_well_pump != None:
    #                 L += self.production_well_pump.get_well_length()
    #
    #     well_cost_formulas = {
    #         'gengeo': lambda L, d, self: self._X_IC * self._X_PC * self._PPI * (0.105 * L ** 2 + 1776. * d * L + 275300.),
    #         'halliburton': lambda L, d, self: 1500 * L,
    #         'st_gallen': lambda L, d, self: 1500 * L,
    #         'bavaria': lambda L, d, self: 1500 * L,
    #         'swiss': lambda L, d, self: 1500 * L,
    #         'ppgd': lambda L, d, self: 969 * L,
    #     }
    #
    #     if self._specs.well_cost_model in well_cost_formulas:
    #         C_well = well_cost_formulas[self._specs.well_cost_model](L, d, self)
    #     else:
    #         raise ValueError(f"The provided well_cost_model: {self._specs.well_cost_model} is not supported")
    #
    #
    #     dC_CO2_well = self._compute_dC_CO2_well(d, L, fluid_name) # adjustment for CO2
    #     return (C_well + dC_CO2_well) / pos


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

        print('inj_list_l', self.injection_well.length_list)
        print('inj_list_d', self.injection_well.diameter_list)
        print('pro_list_l', self.production_well.length_list)
        print('pro_list_d', self.production_well.diameter_list)

        well_cost_formulas = {
            'gengeo': lambda L, d, self: self._X_IC * self._X_PC * self._PPI * (0.105 * L ** 2 + 1776. * d * L + 275300.),
            'halliburton': lambda L, d, self: 1500 * L,
            'st_gallen': lambda L, d, self: 1500 * L,
            'bavaria': lambda L, d, self: 1500 * L,
            'swiss': lambda L, d, self: 1500 * L,
            'ppgd': lambda L, d, self: 969 * L,
        }

        # print(self._specs.wellbore_solver)

        if self._specs.wellbore_solver == "native":
            if self._specs.well_cost_model in well_cost_formulas:
                C_well = well_cost_formulas[self._specs.well_cost_model](L, d, self)
            else:
                raise ValueError(f"The provided well_cost_model: {self._specs.well_cost_model} is not supported")

            dC_CO2_well = self._compute_dC_CO2_well(d, L, fluid_name) # adjustment for CO2
            return (C_well + dC_CO2_well) / pos
        elif self._specs.wellbore_solver == "external":
            if len(self.well_length_list) != len(self.well_diameter_list):
                raise ValueError("Length of well_length_list must be the same as well_diameter_list")

            total_cost = 0.0
            print((self.well_length_list, self.well_diameter_list))
            for L, d in zip(self.well_length_list, self.well_diameter_list):
                # print(L, d)
                if self._specs.well_cost_model in well_cost_formulas:
                    C_well_section = well_cost_formulas[self._specs.well_cost_model](L, d, self)
                    print('C_well_section', C_well_section)
                else:
                    raise ValueError(f"The provided well_cost_model: {self._specs.well_cost_model} is not supported")

                dC_CO2_well_section = self._compute_dC_CO2_well(d, L, fluid_name)
                print('dC_CO2_well_section', dC_CO2_well_section)
                total_cost += (C_well_section + dC_CO2_well_section)
                print('total_cost', total_cost)

            # print(C_well_section, 'inja')
            # print(C_well_section + dC_CO2_well_section)
            # print(total_cost)
            print('total_cost / pos', total_cost / pos)

            return total_cost / pos

        else:
            raise ValueError(f"The provided wellbore_solver: {self._specs.well_cost_model} is not supported")


    def execute(self) -> float:
        num_total_inj, num_total_prod, num_total_hrz = self._compute_num_wells()
        C_inj = self._compute_wells_cost_by_type(well_type='injection_well', num_wells=num_total_inj)
        C_prd = self._compute_wells_cost_by_type(well_type='production_well', num_wells=num_total_prod)
        C_hrz = self._compute_wells_cost_by_type(well_type='horizontal_well', num_wells=num_total_hrz)
        print(C_inj, C_prd, C_hrz, 'huhu')
        return C_inj + C_prd + C_hrz
        # return C_inj
