from tango.units.native.surface.base import *
from tango.units.dataclasses import SurfaceSpecsSingleFlashTESPy
# from tango.units.native.surface.tespy.tespy_input_adapter import *

from tespy.components import Sink, Source, Turbine, HeatExchanger, SimpleHeatExchanger, Compressor, CycleCloser, Valve, DropletSeparator
from tespy.connections import Connection
from tespy.networks import Network
import CoolProp.CoolProp as CP
import matplotlib.pyplot as plt
from fluprodia import FluidPropertyDiagram
import numpy as np
import math


class SurfaceUnitSingleFlashTESPy(SurfaceUnitNative):
    """TESPy power plant unit"""
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsSingleFlashTESPy.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self._initialize_attributes()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float=None, T: float=None) -> None:
        # TODO: change the pressure temperature values!
        self.inlet_fluid = FluidState.withPT(self._fluid_name, 3000000, 380)
        self.mass_rate = self.specs.mass_flow_rate
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)


    def process_stream(self) -> None:
        # yaml_file_path = self.specs.yaml_file_path
        # self.pp = PowerPlant(yaml_file_path, self.inlet_fluid.P/100000.0, self.inlet_fluid.T-273.15, self.mass_rate, {'CO2': 1})
        # self.pp = OrganicRankineCycle(refrigerant='R245fa', pressure=20, temperature=110, mass_rate=30, working_fluid={'water': 1})
        # self.pp = OrganicRankineCycle(refrigerant='R245fa', pressure=self.inlet_fluid.P/100000.0, temperature=self.inlet_fluid.T-273.15, mass_rate=self.mass_rate, working_fluid={'water': 1})
        # self.pp = SingleFlash(fluid={'water': 1}, m=5, T=150, p=40)
        self.pp = SingleFlash(fluid={'water': 1}, m=10, T=self.inlet_fluid.T-273.15, p=self.inlet_fluid.P/100000.0)
        self._update_turbine_power()
        self._update_condenser_state()
        self._update_pump_state()
        self._update_net_state()
        print('\n')
        print(f'PP inlet -> P = {self.inlet_fluid.P}, T = {self.inlet_fluid.T}')
        print(f'PP outlet -> P = {self.outlet_fluid.P}, T = {self.outlet_fluid.T}')

        return self.P_out, self.T_out, 10
        # return 10000000, 320, 10

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> float:
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 1.0 #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow
        self._set_mult()
        self._set_constants()


    def _initialize_attributes(self) -> float:
        self._dP_pump: float = 0.
        # TODO: the below initialization should be removed!
        self._condensation_temperature_range = 0
        self.q_preheater: float = 0.
        self.q_boiler: float = 0.
        self.q_desuperheater: float = 0.


    def _process_specs(self, specs) -> dict:
        return specs['common'] | specs['surface']


    def _update_turbine_power(self) -> None:
        # self.w_turbine = -self.pp.components['turbine'].P.val
        self.w_turbine = -self.pp.t.P.val


    def _update_condenser_state(self) -> None:
        X_CO2 = self._X_CO2
        # self.q_cooler = 0
        self.q_condenser = -X_CO2 * self.pp.q_condenser
        # self._condensation_temperature_range = self.pp.turbine_condenser.T.val - self.pp.connections['condenser_cooler'].T.val
        self._condensation_temperature_range = 3.0
        self.w_cooler = 0
        self.w_condenser = X_CO2 * self.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)
        self.flash_separator_cost = 280.3*pow(self.pp.so_v.m.val, 0.67)
        self.expansion_valve_cost = 114.5*(self.pp.so_v.m.val)


    def _update_pump_state(self) -> None:
        X_CO2 = self._X_CO2
        self.P_out = self.pp.P_out
        # self.P_out = 4000000
        self.T_out = self.pp.T_out
        # self.T_out = 313.15
        self.w_pump = X_CO2 * (-self.pp.pump.P.val-self.pp.pump2.P.val)
        self._W_pump_prod = 9000000
        print('self.w_pump', self.w_pump)
        # print(self.P_out, self.T_out)

    def _update_net_state(self) -> None:
        self.w_net = self.w_turbine + self.w_cooler + self.w_condenser + self.w_pump














class SingleFlash:
    def __init__(self, fluid={'water': 1}, m=10, T=150, p=40):
        self.fluid = fluid
        self.m = m
        self.T = T
        self.p = p
        self.nw = Network(p_unit='bar', T_unit='C', iterinfo=False)
        self._setup_components()
        self._setup_connections()
        self._configure_components()
        self.solve()

    def _setup_components(self):
        self.so = Source('source')
        self.si = Sink('sink')
        self.v = Valve('valve')
        self.sig = Sink('gas flow')
        self.sil = Sink('liquid flow')
        self.ds = DropletSeparator('droplet separator')
        self.t = Turbine('turbine')
        self.sit = Sink('turbine outlet')
        self.condenser = SimpleHeatExchanger('condenser')
        self.pump = Compressor('pump')
        self.pump2 = Compressor('pump2')

    def _setup_connections(self):
        self.so_v = Connection(self.so, 'out1', self.v, 'in1')
        self.v_ds = Connection(self.v, 'out1', self.ds, 'in1')
        self.ds_t = Connection(self.ds, 'out2', self.t, 'in1')
        self.ds_pump2 = Connection(self.ds, 'out1', self.pump2, 'in1')
        self.pump2_sil = Connection(self.pump2, 'out1', self.sil, 'in1')
        self.t_con = Connection(self.t, 'out1', self.condenser, 'in1')
        self.con_pump = Connection(self.condenser, 'out1', self.pump, 'in1')
        self.pump_sit = Connection(self.pump, 'out1', self.sit, 'in1')

        self.nw.add_conns(self.so_v, self.v_ds, self.ds_t, self.ds_pump2, self.pump2_sil, self.t_con, self.con_pump, self.pump_sit)

    def _configure_components(self):
        self.t.set_attr(eta_s=1.0)
        self.so_v.set_attr(fluid=self.fluid, m=self.m, T=self.T, p=self.p, design=['m'])
        self.v_ds.set_attr(p=0.12)
        self.t_con.set_attr(p=0.05)
        self.con_pump.set_attr(p=0.05, x=0)
        self.pump.set_attr(eta_s=1)
        self.pump_sit.set_attr(p=30)
        self.pump2_sil.set_attr(p=30)
        self.pump2.set_attr(eta_s=1.0)

    def solve(self):
        self.nw.solve('design')
        self.nw.print_results()
        self._calculate_heat_transfers()

    def prepare_plot_data(self):
        self.nw.solve('design')
        points = {
            '1': {'h': self.so_v.h.val / 1000.0, 'p': self.so_v.p.val},
            '2': {'h': self.v_ds.h.val / 1000.0, 'p': self.v_ds.p.val},
            '3': {'h': self.ds_t.h.val / 1000.0, 'p': self.ds_t.p.val},
            '4': {'h': self.ds_pump2.h.val / 1000.0, 'p': self.ds_pump2.p.val},
            '5': {'h': self.t_con.h.val / 1000.0, 'p': self.t_con.p.val},
            '6': {'h': self.con_pump.h.val / 1000.0, 'p': self.con_pump.p.val},
            '7': {'h': self.pump_sit.h.val / 1000.0, 'p': self.pump_sit.p.val},
            '8': {'h': self.pump2_sil.h.val / 1000.0, 'p': self.pump2_sil.p.val},
        }
        connections = [
            ('1', '2'),
            ('2', '3'),
            ('3', '5'),
            ('2', '4'),
            ('5', '6'),
            ('6', '7'),
            ('4', '8'),
        ]
        return points, connections

    def _get_enthalpies(self):
        # Extract the enthalpy values for each connection in the circuit.
        # The enthalpy values are divided by 1000 to convert from J/kg to kJ/kg if needed based on your unit system.
        h1 = self.so_v.h.val / 1000.0  # Source to Valve
        h2 = self.v_ds.h.val / 1000.0  # Valve to Droplet Separator
        h3 = self.ds_t.h.val / 1000.0  # Droplet Separator to Turbine
        h4 = self.ds_pump2.h.val / 1000.0  # Droplet Separator to Liquid Sink
        h5 = self.t_con.h.val / 1000.0  # Turbine to Condenser
        h6 = self.con_pump.h.val / 1000.0  # Condenser to Pump
        h7 = self.pump_sit.h.val / 1000.0  # Pump to Sink (Turbine Outlet)
        h8 = self.pump2_sil.h.val / 1000.0  # Pump to Sink (Turbine Outlet)

        return h1, h2, h3, h4, h5, h6, h7, h8

    def _calculate_heat_transfers(self):
        h1, h2, h3, h4, h5, h6, h7, h8 = self._get_enthalpies()

        self.q_condenser = (h5 - h6) * self.t_con.m.val * 1000
        self.H_out = (self.t_con.m.val*h7 + self.ds_pump2.m.val*h8)/(self.t_con.m.val + self.ds_pump2.m.val)
        self.T_out = CP.PropsSI('T', 'P', self.pump_sit.p.val*100000, 'H', self.H_out*1000, 'Water')
        self.P_out = self.pump_sit.p.val*100000
