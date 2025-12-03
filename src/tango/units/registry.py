"""Registry of unit classes for object instantiation from configuration files."""
from tango.units.native.surface.flexible_pp import SurfaceUnitFlexiblePP
from tango.units.native.surface.CPG import SurfaceUnitCPGNative
from tango.units.external.DWSIM.CPG import SurfaceUnitCPGDWSIM
from tango.units.native.surface.ORC import SurfaceUnitORCNative
from tango.units.native.well.injection_well import InjectionWellUnitNative
from tango.units.external.MOOSE.well.well import WellUnitMOOSE
from tango.units.native.well.production_well import ProductionWellUnitNative
from tango.units.native.well.horizontal_well import HorizontalWellUnitNative
from tango.units.native.well.production_well_pump import ProductionWellPumpUnitNative
from tango.units.native.reservoir import ReservoirUnitNative
from tango.units.external.MOOSE.reservoir.reservoir import ReservoirUnitPorousflow
from tango.units.native.unit_reader import ReservoirFileReaderUnit
from tango.core.stream import Stream
from tango.units.cmg.imex import ImexUnit
from tango.units.cmg.gem import GemUnit
from tango.units.cmg.coflow import CoFlowUnit
from tango.units.native.economic.economic import EconomicUnitNative

# Missing/TODO units (commented out or mapped to None if not available)
# SurfaceUnitDHNative
# SurfaceUnitCPGTESPy
# SurfaceUnitORCTESPy
# SurfaceUnitSingleFlashTESPy
# SurfaceUnitDoubleFlashTESPy

UNIT_OPTIONS = {
    "surface": {
        "native_flexible": SurfaceUnitFlexiblePP,
        "native_cpg": SurfaceUnitCPGNative,
        "native_dh": "SurfaceUnitDHNative",  # TODO: Implement or find
        "moose_cpg": SurfaceUnitCPGNative,
        "dwsim_cpg": SurfaceUnitCPGDWSIM,
        "tespy_cpg": "SurfaceUnitCPGTESPy",  # TODO
        "tespy_orc": "SurfaceUnitORCTESPy",  # TODO
        "tespy_sf": "SurfaceUnitSingleFlashTESPy",  # TODO
        "tespy_df": "SurfaceUnitDoubleFlashTESPy",  # TODO
        "native_orc": SurfaceUnitORCNative,
    },
    "injection_well": {"native": InjectionWellUnitNative, "moose": WellUnitMOOSE},
    "production_well": {"native": ProductionWellUnitNative},
    "horizontal_well": {"native": HorizontalWellUnitNative},
    "production_well_pump": {"native": ProductionWellPumpUnitNative},
    "reservoir": {
        "native": ReservoirUnitNative,
        "moose": ReservoirUnitPorousflow,
        "filereader": ReservoirFileReaderUnit,
    },
    "stream": {"native": Stream},
    "cmg": {"imex": ImexUnit, "gem": GemUnit, "coflow": CoFlowUnit},
    "economic": {"native": EconomicUnitNative},
}
