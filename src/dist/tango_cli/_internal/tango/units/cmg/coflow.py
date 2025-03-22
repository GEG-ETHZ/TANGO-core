from tango.units.cmg.base import *

class CoFlowUnit(CMGBaseUnit):
    """Unit for CoFlow - surface+subsurface integrated simulator"""
    def __init__(self, id: str, specs: dict) -> None:
        super().__init__(id, specs)
        self.simulator = 'coflow'
        raise NotImplementedError(f"CoFlow option is currently not supported.")

    # def execute(self) -> None:
    #     pass