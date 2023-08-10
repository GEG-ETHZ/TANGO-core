#TODO: add horizontal well cost
class EconModelWells:

    def __init__(self,
                 specs: dict,
                 injection_well: object,
                 production_well: object):
        self.specs = specs
        self.PPI = self.specs.PPI
        self.X_IC, self.X_PC = specs.multipliers
        self.injection_well = injection_well
        self.production_well = production_well


    def get_num_wells(self) -> list: # per pattern
        NX, NY = self.specs.well_pattern_dimens
        if self.specs.well_pattern == 'DOUBLET':
            num_total_inj = 1
            num_total_prd = 1
        elif self.specs.well_pattern == '5SPOT':
            num_total_inj = (NX+1) * (NY+1)
            num_total_prd = NX * NY
        elif self.specs.well_pattern == 'INVERTED_5SPOT':
            num_total_inj = NX * NY
            num_total_prd = (NX+1) * (NY+1)
        else:
            raise NotImplementedError(f"well_pattern: {self.specs.well_pattern} is not supported")
        return num_total_inj, num_total_prd


    def get_dC_CO2_well(self, d: float, L: float, fluid_name: str) -> float:
        if fluid_name != "CO2":
            return 0
        return self.X_IC * self.X_PC * self.PPI * (265. * d * L + 133. * L)


    def get_individual_well_cost(self, L: float, d: float, pos: float, fluid_name: str = "H2O") -> float:
        C_well = self.X_IC * self.X_PC * self.PPI * (0.105 * L ** 2 + 1776. * d * L + 275300.) # well cost (base line)
        dC_CO2_well = self.get_dC_CO2_well(d, L, fluid_name) # adjustment for CO2
        return (C_well + dC_CO2_well) / pos


    def get_wells_cost_by_type(self, well_type: str, num_wells: int) -> float:
        well_model = getattr(self, well_type, None) # get well model object
        if well_model == None:
            return 0
        if well_type == 'injection_well' and self.specs.project_maturity == 'BROWN_FIELD':
            return 0
        return num_wells * self.get_individual_well_cost(L=well_model.get_well_length(),
                                                         d=well_model.get_diameter(),
                                                         pos=well_model.get_probability_of_success(),
                                                         fluid_name=self.specs.fluid_name)


    def execute(self) -> float:
        num_total_inj, num_total_prod = self.get_num_wells()
        C_inj = self.get_wells_cost_by_type(well_type='injection_well', num_wells=num_total_inj)
        C_prd = self.get_wells_cost_by_type(well_type='production_well', num_wells=num_total_prod)
        return C_inj + C_prd
