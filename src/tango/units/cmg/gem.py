from tango.units.cmg.base import *

class GemUnit(CMGBaseUnit):
    """Unit for GEM IMEX - compositional reservoir simulator"""
    def __init__(self, id: str, specs: dict) -> None:
        super().__init__(id, specs)
        self.simulator = 'gem'
        self.exe = 'gm'
        raise NotImplementedError(f"GEM option is currently not supported.")

    # def execute(self) -> None:
    #     pass