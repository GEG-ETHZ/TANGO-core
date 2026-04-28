from tango.units.cmg.base import *

class CoFlowUnit(CMGBaseUnit):
    """Unit for CoFlow - surface+subsurface integrated simulator"""
    def __init__(self, unit_id: str, specs: dict) -> None:
        super().__init__(unit_id, specs)
        self.simulator = 'coflow'
        raise NotImplementedError(f"CoFlow option is currently not supported.")

    # def execute(self) -> None:
    #     pass
