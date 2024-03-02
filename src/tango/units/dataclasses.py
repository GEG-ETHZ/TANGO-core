from tango.core.config import *

from dataclasses import dataclass, field
import inspect

from typing import Optional, List

@dataclass
class CommonSpecs:
    fluid_name: str
    mass_flow_rate: float  # kg/s
    rock_density: float # kg/m3
    rock_cp: float # specific heat capacity (J/(kg*K))
    rock_k: float
    surface_temperature: float  # K
    surface_pressure: float  # Pa
    thermal_gradient: float  # degC/m
    well_pattern: str
    well_spacing: float
    well_pattern_dimens: list
    start_date: str
    num_tsteps: int
    dt: float  # time step years
    # ddd: float = 0.90  # The pump efficiency (-)

    def __post_init__(self):
        if self.well_pattern not in WELL_PATTERN_OPTIONS:
            raise ValueError(f"Well_pattern: {self.well_pattern} is not supported")
    @classmethod
    def from_dict(cls, env): # ignore extra arguments passed to a dataclass
        return cls(**{
            k: v for k, v in env.items()
            if k in inspect.signature(cls).parameters
        })


@dataclass
class WellSpecs(CommonSpecs):
    """General well specs"""
    well_length: float = None  # well length (m)
    diameter: float = None # (m)
    epsilon: float = 55.e-6  # roughness of the well (m)
    probability_of_success: float = 0.95
    eta_pump: float = 0.90  # The pump efficiency (-)

    # well_length_list: List[float] = field(default_factory=list)
    # well_diameter_list: List[float] = field(default_factory=list)
    # well_length_list: Optional[List[float]] = None
    # well_diameter_list: Optional[List[float]] = None

    def __post_init__(self):
        required_fields = ['well_length', 'diameter']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")


@dataclass
class WellSpecsNative(WellSpecs):
    """The well specs based on Adams et al. (2015)."""
    vertical_deviation: float = None    # vertical deviation angle defined in degrees
    num_cells: int = 100    # number of cells that is used for discretization
    gravity_scale_factor: float = 1.0    # the scale factor used for changing the direction of gravity
    wellhead_depth: float = 0. # wellhead measured depth (m)
    brine_density: float = 1000.0  # the brine density used to calculate the reservoir pressure (kg/m3)


@dataclass
class WellSpecsMOOSE(WellSpecs):
    """MOOSE well specs"""
    yaml_file_path: str = "/Users/morteza/Documents/projects/TANGO/examples/testcase20.yml"
    template_file_path: str = "/Users/morteza/Documents/projects/TANGO/examples/AGS_Mahmoud_template.i"
    output_directory: str = "/Users/morteza/Documents/projects/moskito2"
    output_file_name: str = "AGS_Mahmoud.i"
    moose_executable_path: str = '/Users/morteza/Documents/projects/moskito2/moskito-opt'
    moose_input_path: str = '/Users/morteza/Documents/projects/moskito2/AGS_Mahmoud.i'
    post_processor_path: str = '/Users/morteza/Documents/projects/TANGO/src/tango/gg_out.csv'
    pressure_bc_file: str = 'pc.csv'
    flowrate_bc_file: str = 'qc.csv'
    temperature_bc_file: str = 'tc.csv'


@dataclass
class SurfaceSpecsCPGNative(CommonSpecs):
    pipe_diameter: float = None  # (m)
    approach_temperature: float = None  # The temperature difference between condensing and the surface temperature (K)
    condensation_pressure_offset: float = None  # (Pa)
    temperature_range: float = 0. # diff between inlet and exit fluid temperature.
    eta_pump: float = 0.90    # The pump efficiency (-)
    total_pipe_length: float = None # (m)
    epsilon: float = 55.e-6  # roughness of surface pipe (m)
    eta_turbine: float = 0.78 # The isentropic efficiency of the turbine (-)
    cooling_tower_design: str = 'CLOSED' # cooling tower design
    cooling_mode: str = 'WET' # WET or DRY
    def __post_init__(self):
        required_fields = ['pipe_diameter', 'approach_temperature', 'condensation_pressure_offset']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")


@dataclass
class SurfaceSpecsCPGDWSIM(SurfaceSpecsCPGNative):
    local_script_path = "/Users/morteza/Documents/projects/TANGO/src/tango/interfaces/tango_dwsim_interface.py"
    remote_username = "morteza"
    remote_ip = "10.211.55.3"
    remote_script_path = "/Users/morteza/Desktop/new.py"
    PP_csv_file = "/Users/morteza/Desktop/data.csv"


@dataclass
class SurfaceSpecsCPGTESPy(SurfaceSpecsCPGNative):
    yaml_file_path = '/Users/morteza/Documents/projects/TANGO/examples/testcase20.yml'

@dataclass
class SurfaceSpecsORCTESPy(SurfaceSpecsCPGNative):
    pass

@dataclass
class SurfaceSpecsSingleFlashTESPy(SurfaceSpecsCPGNative):
    pass

@dataclass
class SurfaceSpecsDoubleFlashTESPy(SurfaceSpecsCPGNative):
    pass

@dataclass
class ReservoirSpecs(CommonSpecs):
    """General well specs"""
    reservoir_depth: float = None
    porosity: float = None    # the rock porosity in the reservoir (dimensionless)
    permeability: float = None # the rock permeability in the reservoir (in m2)
    brine_density: float = 1000.0  # the brine density used to calculate the reservoir pressure (kg/m3)
    initial_pressure: float = None
    initial_temperature: float = None


@dataclass
class ReservoirSpecsNative(ReservoirSpecs):
    """Specifications for reservoir unit based on Adams et. al (2015)"""
    thickness: float = None     # the reservoir thickness (in m)
    area: float = None
    net_to_gross_ratio: float = 1.0
    well_eff_diameter: float = 0.41 # effective (average) wellbore diameter (inj and prod) (m)
    def __post_init__(self):
        required_fields = ['reservoir_depth', 'thickness', 'porosity', 'permeability']
        # required_fields = ['porosity', 'permeability']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")

@dataclass
class ReservoirSpecsPorousflow(ReservoirSpecs):
    """MOOSE well specs"""
    # moose_executable_path: str = '/Users/morteza/Documents/projects/moskito2/porous-flow-opt'
    # moose_executable_path: str = '/Users/morteza/Documents/projects/moose/modules/porous_flow/porous_flow-opt'
    # moose_input_path: str = '/Users/morteza/Documents/projects/moose/modules/porous_flow/pf.i'
    # post_processor_path: str = '/Users/morteza/Documents/projects/TANGO/src/tango/pf_out.csv'
    # pressure_bc_file: str = 'pc.csv'
    # flowrate_bc_file: str = 'qc.csv'
    # temperature_bc_file: str = 'tc.csv'
    yaml_file_path: str = "/Users/morteza/Documents/projects/TANGO/examples/testcase20.yml"
    template_file_path: str = "/Users/morteza/Documents/projects/TANGO/examples/AGS_Mahmoud_template.i"
    output_directory: str = "/Users/morteza/Documents/projects/moskito2"
    output_file_name: str = "AGS_Mahmoud.i"
    moose_executable_path: str = '/Users/morteza/Documents/projects/moskito2/moskito-opt'
    moose_input_path: str = '/Users/morteza/Documents/projects/moskito2/AGS_Mahmoud.i'
    post_processor_path: str = '/Users/morteza/Documents/projects/TANGO/src/tango/gg_out.csv'
    pressure_bc_file: str = 'pc.csv'
    flowrate_bc_file: str = 'qc.csv'
    temperature_bc_file: str = 'tc.csv'
    def __post_init__(self):
        required_fields = ['reservoir_depth', 'porosity', 'permeability']
        # required_fields = ['porosity', 'permeability']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")
