from tango.units.native.surface.base import *
from tango.units.dataclasses import SurfaceSpecsDoubleFlashTESPy

from tespy.components import Sink, Source, Turbine, HeatExchanger, SimpleHeatExchanger, Compressor, CycleCloser, Valve, DropletSeparator
from tespy.connections import Connection
from tespy.networks import Network
import CoolProp.CoolProp as CP
import matplotlib.pyplot as plt
from fluprodia import FluidPropertyDiagram
import numpy as np
import math
import logging


class SurfaceUnitDoubleFlashTESPy(SurfaceUnitNative):
    """TESPy power plant unit"""
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsDoubleFlashTESPy.from_dict(self._process_specs(specs))
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
        self.pp = DoubleFlash(fluid={'water': 1}, m=45, T=self.inlet_fluid.T-273.15, p=self.inlet_fluid.P/100000.0, p2=2, p_t2=0.05)
        self._update_turbine_power()
        self._update_condenser_state()
        self._update_pump_state()
        self._update_net_state()
        logging.info('\n')
        logging.info(f'PP inlet -> P = {self.inlet_fluid.P}, T = {self.inlet_fluid.T}')
        logging.info(f'PP outlet -> P = {self.outlet_fluid.P}, T = {self.outlet_fluid.T}')

        return self.P_out, self.T_out, 45

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> float:
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        # self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0 #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow
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
        self.w_turbine = -self.pp.t.P.val-self.pp.t2.P.val


    def _update_condenser_state(self) -> None:
        self.q_condenser = -self.pp.q_condenser
        self._condensation_temperature_range = 3.0
        self.w_cooler = 0
        self.w_condenser = self.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)
        self.flash_separator_cost = 280.3*pow(self.pp.so_v.m.val, 0.67) + 280.3*pow(self.pp.ds_v2.m.val, 0.67)
        self.expansion_valve_cost = 114.5*(self.pp.so_v.m.val + self.pp.ds_v2.m.val)


    def _update_pump_state(self) -> None:
        self.P_out = self.pp.P_out
        self.T_out = self.pp.T_out
        self.w_pump = (-self.pp.pump1.P.val-self.pp.pump2.P.val)
        self.w_downhole_pump = -0

    def _update_net_state(self) -> None:
        self.w_net = self.w_turbine + self.w_cooler + self.w_condenser + self.w_pump


class DoubleFlash:
    def __init__(self, fluid={'water': 1}, m=5, T=150, p=40, p2=2, p_t2=0.05):
        self.fluid = fluid
        self.m = m
        self.T = T
        self.p = p
        self.p2 = p2
        self.p_t2 = p_t2
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
        self.v2 = Valve('valve 2')
        self.ds2 = DropletSeparator('droplet separator 2')
        self.t2 = Turbine('turbine 2')
        self.condenser = SimpleHeatExchanger('condenser')
        self.pump1 = Compressor('pump1')
        self.pump2 = Compressor('pump2')

    def _setup_connections(self):
        self.so_v = Connection(self.so, 'out1', self.v, 'in1')
        self.v_ds = Connection(self.v, 'out1', self.ds, 'in1')
        self.ds_t = Connection(self.ds, 'out2', self.t, 'in1')
        self.t_sit = Connection(self.t, 'out1', self.sit, 'in1')

        self.ds_v2 = Connection(self.ds, 'out1', self.v2, 'in1')
        self.v2_ds2 = Connection(self.v2, 'out1', self.ds2, 'in1')
        self.ds2_pump1 = Connection(self.ds2, 'out1', self.pump1, 'in1')
        self.pump1_sil = Connection(self.pump1, 'out1', self.sil, 'in1')

        self.ds2_t2 = Connection(self.ds2, 'out2', self.t2, 'in1')
        self.t2_con = Connection(self.t2, 'out1', self.condenser, 'in1')
        self.con_pump2 = Connection(self.condenser, 'out1', self.pump2, 'in1')
        self.pump2_sig = Connection(self.pump2, 'out1', self.sig, 'in1')

        self.nw.add_conns(self.so_v, self.v_ds, self.ds_t, self.ds_v2, self.t_sit, self.v2_ds2,
                          self.ds2_t2, self.ds2_pump1, self.pump1_sil, self.t2_con, self.con_pump2, self.pump2_sig)

    def _configure_components(self):
        self.t.set_attr(eta_s=1.0)
        self.so_v.set_attr(fluid=self.fluid, m=self.m, T=self.T, p=self.p, design=['m'])
        self.v_ds.set_attr(p=self.p2)
        self.t_sit.set_attr(p=0.05)

        self.v2_ds2.set_attr(p=0.2)
        self.t2.set_attr(eta_s=1.0)
        self.t2_con.set_attr(p=self.p_t2)
        self.con_pump2.set_attr(p=self.p_t2, x=0)
        self.pump2.set_attr(eta_s=1)
        self.pump2_sig.set_attr(p=30)

        self.pump1.set_attr(eta_s=1)
        self.pump1_sil.set_attr(p=30)

    def solve(self):
        self.nw.solve('design')
        self.nw.print_results()
        self._calculate_heat_transfers()

    def prepare_plot_data(self):
        # Solve the network again to ensure all data is up to date
        self.nw.solve('design')

        # Define points based on the connection objects' enthalpy (h) and pressure (p) values
        points = {
            '1': {'h': self.so_v.h.val / 1000.0, 'p': self.so_v.p.val},
            '2': {'h': self.v_ds.h.val / 1000.0, 'p': self.v_ds.p.val},
            '3': {'h': self.ds_t.h.val / 1000.0, 'p': self.ds_t.p.val},
            '4': {'h': self.ds_v2.h.val / 1000.0, 'p': self.ds_v2.p.val},
            '5': {'h': self.t_sit.h.val / 1000.0, 'p': self.t_sit.p.val},
            '6': {'h': self.v2_ds2.h.val / 1000.0, 'p': self.v2_ds2.p.val},
            '7': {'h': self.ds2_pump1.h.val / 1000.0, 'p': self.ds2_pump1.p.val},
            '8': {'h': self.ds2_t2.h.val / 1000.0, 'p': self.ds2_t2.p.val},
            '9': {'h': self.t2_con.h.val / 1000.0, 'p': self.t2_con.p.val},
            '10': {'h': self.con_pump2.h.val / 1000.0, 'p': self.con_pump2.p.val},
            '11': {'h': self.pump1_sil.h.val / 1000.0, 'p': self.pump1_sil.p.val},
            '12': {'h': self.pump2_sig.h.val / 1000.0, 'p': self.pump2_sig.p.val},
        }

        # Define connections to reflect the actual component connections in your system
        connections = [
            ('1', '2'),  # Source to Valve
            ('2', '3'),  # Valve to Turbine through Droplet Separator
            ('3', '5'),  # Turbine to Sink (Turbine outlet)
            ('2', '4'),  # Valve through Droplet Separator to Valve 2
            ('4', '6'),  # Valve 2 to Droplet Separator 2
            ('6', '7'),  # Droplet Separator 2 to Pump 1
            ('7', '11'), # Pump 1 to Liquid Sink
            ('6', '8'),  # Droplet Separator 2 to Turbine 2
            ('8', '9'),  # Turbine 2 to Condenser
            ('9', '10'), # Condenser to Pump 2
            ('10', '12'),# Pump 2 to Gas Sink
        ]

        return points, connections

    def _get_enthalpies(self):
        # Extract enthalpy values from connections, converting from J/kg to kJ/kg if your unit system necessitates it.
        h1 = self.so_v.h.val / 1000.0  # Source to Valve
        h2 = self.v_ds.h.val / 1000.0  # Valve to Droplet Separator
        h3 = self.ds_t.h.val / 1000.0  # Droplet Separator to Turbine
        h4 = self.ds_v2.h.val / 1000.0  # Droplet Separator to Valve 2
        h5 = self.t_sit.h.val / 1000.0  # Turbine to Sink (Turbine outlet)
        h6 = self.v2_ds2.h.val / 1000.0  # Valve 2 to Droplet Separator 2
        h7 = self.ds2_pump1.h.val / 1000.0  # Droplet Separator 2 to Pump 1
        h8 = self.ds2_t2.h.val / 1000.0  # Droplet Separator 2 to Turbine 2
        h9 = self.t2_con.h.val / 1000.0  # Turbine 2 to Condenser
        h10 = self.con_pump2.h.val / 1000.0  # Condenser to Pump 2
        h11 = self.pump1_sil.h.val / 1000.0  # Pump 1 to Liquid Sink
        h12 = self.pump2_sig.h.val / 1000.0  # Pump 2 to Gas Sink

        return h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11, h12

    def _calculate_heat_transfers(self):
       h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11, h12 = self._get_enthalpies()

       self.q_condenser = (h9 - h10)*self.t2_con.m.val*1000 + (h5 - h10)*self.t_sit.m.val*1000
       self.H_out = (self.con_pump2.m.val*h12 + self.ds2_pump1.m.val*h11)/(self.con_pump2.m.val + self.ds2_pump1.m.val)
       self.T_out = CP.PropsSI('T', 'P', self.pump2_sig.p.val*100000, 'H', self.H_out*1000, 'Water')
       self.P_out = self.pump2_sig.p.val*100000


# The below class and its usage is implemented during the development phase to visualize the result of the DoubleFlash
# class. You can activate the below lines and run the module separately to check the result on a phase diagram.

# class CycleDiagramPlotter:
#     def __init__(self, fluid, points, connections):
#         self.fluid = fluid
#         self.points = points
#         self.connections = connections
#
#     def plot_diagram(self):
#         diagram = FluidPropertyDiagram(fluid=self.fluid)
#         diagram.set_unit_system(T='°C', h='kJ/kg', p='bar')
#         Q = np.linspace(0, 1, 2)
#         T = np.arange(25, 501, 25)
#         p = np.geomspace(0.01, 1000, 6) * 1e5
#         diagram.set_isolines(Q=Q, T=T, p=p)
#         diagram.calc_isolines()
#
#         fig, ax = plt.subplots(1, figsize=(8, 5))
#         diagram.draw_isolines(diagram_type='logph', fig=fig, ax=ax, x_min=0, x_max=3000, y_min=0.01, y_max=1000)
#
#         for key, value in self.points.items():
#             ax.plot(value['h'], value['p'], 'o', label=f"Point {key}")
#
#         for start, end in self.connections:
#             start_h, start_p = self.points[start]['h'], self.points[start]['p']
#             end_h, end_p = self.points[end]['h'], self.points[end]['p']
#             ax.plot([start_h, end_h], [start_p, end_p], 'k-')
#
#         ax.set_xlabel('Enthalpy [kJ/kg]')
#         ax.set_ylabel('Pressure [bar]')
#         ax.set_yscale('log')
#         ax.legend(loc='best')
#         plt.tight_layout()
#         plt.show()
#
#
# # Initialize and solve the advanced water circuit
# awc = DoubleFlash(fluid={'water': 1}, m=45, T=170, p=40, p2=1, p_t2=0.05)
# print('lll', awc.q_condenser, awc.H_out, awc.T_out, awc.t.P.val+awc.t2.P.val)
# # awc.solve()
#
# # Prepare plot data and plot the cycle diagram
# points, connections = awc.prepare_plot_data()
# plotter = CycleDiagramPlotter('H2O', points, connections)
# plotter.plot_diagram()
#
#
# print(280.3*pow(awc.so_v.m.val, 0.67))
# print(280.3*pow(awc.ds_v2.m.val, 0.67))
# print(114.5*awc.so_v.m.val)
# print(114.5*awc.ds_v2.m.val)
