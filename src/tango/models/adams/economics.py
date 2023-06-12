from tango.models.base import *
from tango.model import ModelState
from dataclasses import dataclass


@dataclass
class EconomicSpecsAdams(CommonSpecs):
    """Implements the common interface for classes providing economic specifications."""
    #TODO: assign default/generic values here.
    data_table_path: str = ""
    placeholder: int = 0
    pass


class EconomicStateAdams(EconomicState):
    """Economics state based on Adams et. al (2015)."""
    def __init__(self):
        EconomicState.__init__(self)


class EconomicModelAdams(EconomicModel):

    """Implements the common interface for classes providing economic modeling capabilities."""
    def __init__(self, specs: dict, state: EconomicState) -> None:
        self.specs = EconomicSpecsAdams(**specs)
        self.state = state


    def execute(self) -> None:
        raise NotImplementedError(f"execute method in {str(self.__class__)} has not yet been implemented.")

