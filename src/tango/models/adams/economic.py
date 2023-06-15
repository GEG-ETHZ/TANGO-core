import logging

from tango.models.base import *
from tango.model import ModelState
from dataclasses import dataclass

import os
from pathlib import Path
import os
import pandas as pd
import numpy as np
from scipy.interpolate import interp1d

# utilities
# def set_PPI_table_path(fname): # producer price index (PPI) table
#     global PPI_table_path
#     PPI_table_path = fname
#     if not os.path.isabs(fname):
#         PPI_table_path = os.path.join(Path(__file__).parent.parent.parent.parent.parent, 'data', fname)
#     if not os.path.exists(PPI_table_path):
#         raise FileNotFoundError(f"{PPI_table_path} not found.")
def set_PPI_table(fname): # producer price index (PPI) table
    path = fname
    if not os.path.isabs(fname):
        path = os.path.join(Path(__file__).parent.parent.parent.parent.parent, 'data', fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found.")
    global PPI_table
    try:
        PPI_table = pd.read_excel(path, header=1)
    except:
        raise RuntimeError(f"Failed to read {path}.")


def get_table(fname): # producer price index (PPI) table
    path = fname
    if not os.path.isabs(fname):
        path = os.path.join(Path(__file__).parent.parent.parent.parent.parent, 'data', fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} not found.")
    try:
        table = pd.read_excel(path, header=1)
    except:
        raise RuntimeError(f"Failed to read {path}.")
    return table



def get_PPI_value(col_name: str, year: float):
    df = PPI_table
    val = float(interp1d(df.Year, df[col_name], bounds_error=False, kind='linear')(year))
    if np.isnan(val):
        logging.warning(f"A value {year} is outside the interpolation range in PPI_table. Extrapolating a value for {col_name}.")
        val = float(interp1d(df.Year, df[col_name], bounds_error=False, fill_value='extrapolate', kind='linear')(year))
    return val


@dataclass
class EconomicSpecsAdams(CommonSpecs):
    """Implements the common interface for classes providing economic specifications."""
    #TODO: assign default/generic values here.
    placeholder: int = 0 # test
    PPI_table: str = 'PPI_table.xlsx'
    cost_multiplier_table: str = 'cost_multiplier_table.xlsx'
    # CapitalCostSurfacePlantCPG... may not be necessary? (already included in surface?
    T_ambient_C = 15.
    dT_approach = 7.
    # cost model
    # cost_year = 2019
    success_rate = 0.95
    F_OM = 0.045
    discount_rate = 0.096
    lifetime = 25
    capacity_factor = 0.85

    pass


class EconomicStateAdams(EconomicState):
    """Economics state based on Adams et. al (2015)."""
    def __init__(self):
        EconomicState.__init__(self)


class EconomicModelAdams(EconomicModel):

    def __init__(self, specs: dict, state: EconomicState) -> None:
        self.specs = EconomicSpecsAdams(**specs)
        self.state = state
        self.results = {"time":[], "LCOE":[], "NPV":[]} #TODO: temporary.
        self.set_tables()
        # set_PPI_table(self.specs.PPI_table)
        # set_cost_multiplier_table(self.specs.PPI_table)


    def set_tables(self):
        global PPI_table, cost_mult_table
        PPI_table = get_table(self.specs.PPI_table)
        cost_mult_table = get_table(self.specs.cost_multiplier_table)


    def set_inlet_state(self, state: ModelState) -> None:
        self.inlet_state = state


    def set_models(self, model_list):
        self.models = list()
        for model in model_list:
            if self.__class__ != type(model):
                model.set_econ_specs()
                self.models.append(model)


    def execute(self) -> None:
        # raise NotImplementedError(f"execute method in {str(self.__class__)} has not yet been implemented.")
        # compute cost for each component
        cost = 0 # TODO: rename it as necessary
        for model in self.models:
            cost += model.get_cost()
            # TODO: improve each get_cost() method.
            #       e.g., return CAPEX at t=0, then return OPEX at t>0.
            #       greenfield/brown field in specs['common']?

