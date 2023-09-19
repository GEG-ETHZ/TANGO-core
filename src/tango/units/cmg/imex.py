from tango.units.cmg.base import *

class ImexUnit(CMGBaseUnit):
    """Unit for CMG IMEX - black-oil reservoir simulator"""
    def __init__(self, id: str, specs: dict) -> None:
        super().__init__(id, specs)
        self.simulator = 'imex'
        self.exe = 'mx'

    # def execute(self) -> None:
    #     pass