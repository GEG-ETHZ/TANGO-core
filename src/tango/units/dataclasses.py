from tango.core.config import *

from dataclasses import dataclass, field
import numpy as np
import inspect
from typing import List
from typing import List, Dict, Union, Optional

@dataclass
class BcIteration:
    check_fracing: str  # 'yes' or 'no'
    controlled_power_generation: str = 'No'

@dataclass
class MassRate:
    function: str
    type: str  # 'manual' or 'automatic'
    value: float = 50.

@dataclass
class BcColumns:
    pressure_column_index: int
    temperature_column_index: int
    flowrate_column_index: int

@dataclass
class CommonSpecs:
    num_pp: int # number of power plants
    fluid_name: str
    mass_flow_rate: float  # kg/s
    rock_density: float # kg/m3
    rock_cp: float # specific heat capacity (J/(kg*K))
    rock_k: float # thermal conductivity (W/m/K)
    surface_temperature: float  # K
    surface_pressure: float  # Pa
    thermal_gradient: float  # degC/m
    well_pattern: str
    well_spacing: float # (m)
    well_pattern_dimens: list
    start_date: str
    time_list: List[float] = field(default_factory=list)
    dt_list: List[float] = field(default_factory=list)
    bc_iteration_checkpoint: str = 'production_well_bottom'
    injection_condition_back_calculation: str = 'no'
    flow_rate_from_csv: str = 'no'
    flow_rate_file: str = None
    bc_iteration: Optional[BcIteration] = None
    mass_rate: Optional[MassRate] = None
    target_extraction_pressure: float = 2000000
    injection_pressure: float = 2000000
    output_table: str = 'no'
    power_plant_table: str = 'no'
    table_to_csv: str = 'no'
    bypass_file_generation: str = 'no'
    min_thermal_power: float = 0.005 # (MW)

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
    well_length: float = None  # (m)
    diameter: float = None # (m)
    epsilon: float = 55.e-6  # roughness of the well (m)
    probability_of_success: float = 0.95
    eta_pump: float = 0.90  # The pump efficiency (-)
    well_length_seq: list = None
    well_diameter_seq: list = None

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
    yaml_file_path: str = "/examples/MOOSE_Tespy examples/testcase20.yml"
    template_file_path: str = "/Users/morteza/Documents/projects/TANGO/examples/AGS_Mahmoud_template.i"
    output_directory: str = "/Users/morteza/Documents/projects/moskito2"
    output_file_name: str = "AGS_Mahmoud.i"
    moose_executable_path: str = '/Users/morteza/Documents/projects/moskito2/moskito-opt'
    moose_input_path: str = '/Users/morteza/Documents/projects/moskito2/AGS_Mahmoud.i'
    post_processor_path: str = '/Users/morteza/Documents/projects/TANGO/src/tango/gg_out.csv'
    pressure_bc_file: str = 'pc.csv'
    flowrate_bc_file: str = 'qc.csv'
    temperature_bc_file: str = 'tc.csv'
    bc_columns: Optional[BcColumns] = None


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

# should be removed - we don't use DWSIM anymore!
@dataclass
class SurfaceSpecsCPGDWSIM(SurfaceSpecsCPGNative):
    local_script_path = "/Users/morteza/Documents/projects/TANGO/src/tango/interfaces/tango_dwsim_interface.py"
    remote_username = "morteza"
    remote_ip = "10.211.55.3"
    remote_script_path = "/Users/morteza/Desktop/new.py"
    PP_csv_file = "/Users/morteza/Desktop/data.csv"

@dataclass
class ReservoirSpecs(CommonSpecs):
    """General well specs"""
    reservoir_depth: float = None # (m)
    porosity: float = None    # the rock porosity in the reservoir (dimensionless)
    permeability: float = None # the rock permeability in the reservoir (in m2)
    brine_density: float = 1000.0  # the brine density used to calculate the reservoir pressure (kg/m3)
    initial_pressure: float = None # (Pa)
    initial_temperature: float = None # (K)
    hydro_static_pressure: float = None # (Pa)
    over_pressure_percentage: float = None


@dataclass
class ReservoirSpecsNative(ReservoirSpecs):
    """Specifications for reservoir unit based on Adams et. al (2015)"""
    inlet_state: str = None
    outlet_state: str = None
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
    yaml_file_path: str = "/Users/morteza/Documents/projects/TANGO/examples/testcase17.yml"
    template_file_path: str = "/examples/MOOSE input files/pf.i"
    output_directory: str = '/Users/morteza/Documents/projects/moose/modules/porous_flow'
    output_file_name: str = "pf_copy.i"
    moose_executable_path: str = '/Users/morteza/Documents/projects/moose/modules/porous_flow/porous_flow-opt'
    moose_input_path: str = '/Users/morteza/Documents/projects/moose/modules/porous_flow/pf.i'
    post_processor_path: str = '/Users/morteza/Documents/projects/moose/modules/porous_flow/pf_out.csv'
    pressure_bc_file: str = 'pcres.csv'
    flowrate_bc_file: str = 'qcres.csv'
    temperature_bc_file: str = 'tcres.csv'

    def __post_init__(self):
        required_fields = ['reservoir_depth', 'porosity', 'permeability']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")


@dataclass
class ThermaGraphSpecs:
    states_file: str
    connections_file: str
    active: str = 'no'
    execute: str = 'yes'
    per_timestep: str = 'no'
    fluid_name: str = 'H2O'
    auto_save_svg: str = 'no'  # 'yes' to auto-save SVG, 'no' to show UI
    svg_filename: str = 'output'     # SVG filename to use if auto_save_svg is yes

    @classmethod
    def from_dict(cls, env): # ignore extra arguments passed to a dataclass
        return cls(**{
            k: v for k, v in env.items()
            if k in inspect.signature(cls).parameters
        })

@dataclass
class AnalyzerSpecs:
    results_file: str
    active: str = 'no'
    execute: str = 'no'

    @classmethod
    def from_dict(cls, env): # ignore extra arguments passed to a dataclass
        return cls(**{
            k: v for k, v in env.items()
            if k in inspect.signature(cls).parameters
        })

@dataclass
class OptimizationSpecs:
    variables: Dict[str, Dict[str, Union[float, str]]]  # Variable names with bounds and type (e.g., continuous or integer)
    targets: List[str]
    target_type: List[str] # 'maximize' or 'minimize'
    method: str
    parallel_processing: str
    n_generation: int
    n_processes: int
    pop_size: int
    constraints: Dict[str, Dict[str, Union[float, str]]] = field(default_factory=dict)  # Constraints on parameters not optimized
    final_selection: str = 'ASF'
    weights: List[float] = field(default_factory=lambda: [0.5])
    crossover_probability: float = 0.9
    distribution_index: int = 15
    polynomial_mutation: int = 20
    plot_name: str = 'opt_result'

    def __post_init__(self):
        # Ensure all required fields are present
        for var, specs in self.variables.items():
            if 'lower_bound' not in specs or 'upper_bound' not in specs or 'type' not in specs:
                raise RuntimeError(f"Variable {var} must have 'lower_bound', 'upper_bound', and 'type'.")

    @classmethod
    def from_dict(cls, env): # ignore extra arguments passed to a dataclass
        return cls(**{
            k: v for k, v in env.items()
            if k in inspect.signature(cls).parameters
        })

@dataclass
class DistrictHeatingSpecs:
    operation_year: int
    feeding_time: float = 20.0
    efficiency_thermal: float = 1.0
    efficiency_electric: float = 0.0
    coldstart_cost: float = 1000.0
    renewable_factor: float = 1.0
    must_run: float = 0.0
    max_available_potential: float = 0.0
    max_power_output: float = 0
    excess_heat_source_price: float = 0
    ramping_cost: float = 0
    type: str = "Geo Thermal" # "CHP-BP", "boiler", "Heat Pump Air", "CHP-ST", "heat boiler wood pellets"
    COP_source_temperature_sensitivity: float = 0
    COP_flow_temperature_sensitivity: float = 0
    COP_return_temperature_sensitivity: float = 0
    min_shutoff_source_temperature: float = 0
    fade_out_temperature: float = 0
    source_temperature: float = 0
    nominal_inlet_temperature: float = 0
    nominal_return_temperature: float = 0
    refrigerants: str = " "
    max_power_heatpump_compressor: float = 0
    min_output_power_factor: float = 0
    electricity_price: str = " "
    sale_electricity_price: str = " "
    output_file: str = "fff.xlsx"
    run_district_heating_simulator: str = 'no'
    run_milp_optimizer: str = 'no'  # Whether to run MILP instead of HotmapsDispatch

    @classmethod
    def from_dict(cls, env): # ignore extra arguments passed to a dataclass
        return cls(**{
            k: v for k, v in env.items()
            if k in inspect.signature(cls).parameters
        })


@dataclass
class MILPSpecs:
    """Specifications for the MILP addon - Mixed Integer Linear Programming optimizer."""
    active: str = 'no'  # 'yes' or 'no' - whether addon is active
    execute: str = 'no'  # 'yes' or 'no' - whether to run optimization
    scenario_file: str = ''  # Path to base scenario JSON file
    output_dir: str = ''  # Output directory for results
    solver: str = 'highs'  # MILP solver: 'highs', 'gurobi', 'cbc'
    add_geothermal: str = 'yes'  # Whether to add geothermal from TANGO results
    generate_plots: str = 'yes'  # Whether to generate visualization plots

    @classmethod
    def from_dict(cls, env):
        """Create MILPSpecs from dictionary, ignoring extra arguments."""
        return cls(**{
            k: v for k, v in env.items()
            if k in inspect.signature(cls).parameters
        })
