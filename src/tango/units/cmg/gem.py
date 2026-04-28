from tango.units.cmg.base import *

class GemUnit(CMGBaseUnit):
    """Unit for GEM IMEX - compositional reservoir simulator"""
    def __init__(self, unit_id: str, specs: dict) -> None:
        super().__init__(unit_id, specs)
        self.simulator = 'gem'
        self.exe = 'gm'
           # def execute(self) -> None:
    #     pass
