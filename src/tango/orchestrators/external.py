from tango.core.abstracts.orchestrator import *


class SystemExternal(UnitManager):

    def __init__(self, specs):
        super().__init__(specs)

    def pmp(self) -> None:
        """update unknown variables to balance the system"""
        self.unit.surface.w_downhole_pump = self.unit.injection_well.w_downhole_pump
