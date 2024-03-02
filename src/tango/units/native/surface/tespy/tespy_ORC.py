from tango.units.native.surface.base import *
from tango.units.dataclasses import SurfaceSpecsORCTESPy
# from tango.units.native.surface.tespy.tespy_input_adapter import *

from tespy.components import Sink, Source, Turbine, HeatExchanger, SimpleHeatExchanger, Compressor, CycleCloser
from tespy.connections import Connection
from tespy.networks import Network
import CoolProp.CoolProp as CP
import matplotlib.pyplot as plt
from fluprodia import FluidPropertyDiagram
import numpy as np
import math


class SurfaceUnitORCTESPy(SurfaceUnitNative):
    """TESPy power plant unit"""
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsORCTESPy.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self._initialize_attributes()
        self.init_stream_interface()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def init_stream_interface(self, P: float=None, T: float=None) -> None:
        # TODO: change the pressure temperature values!
        self.inlet_fluid = FluidState.withPT(self._fluid_name, 12000000, 380)
        self.mass_rate = self.specs.mass_flow_rate
        self.outlet_fluid = FluidState.copy(self.inlet_fluid)


    def process_stream(self) -> None:
        # yaml_file_path = self.specs.yaml_file_path
        # self.pp = PowerPlant(yaml_file_path, self.inlet_fluid.P/100000.0, self.inlet_fluid.T-273.15, self.mass_rate, {'CO2': 1})
        # self.pp = OrganicRankineCycle(refrigerant='R245fa', pressure=20, temperature=110, mass_rate=30, working_fluid={'water': 1})
        self.pp = OrganicRankineCycle(refrigerant='R245fa', pressure=self.inlet_fluid.P/100000.0, temperature=self.inlet_fluid.T-273.15, mass_rate=self.mass_rate, working_fluid={'water': 1})
        self._update_turbine_power()
        self._update_condenser_state()
        self._update_pump_state()
        self._update_net_state()
        print('outside', self.T_out, self.P_out)

        return self.P_out, self.T_out, self.mass_rate

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _specs_post_processor(self) -> float:
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0 #TODO: implement something like state.inlet_fluid.X_CO2 for multphase flow
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
        self.w_turbine = -self.pp.turbine.P.val


    def _update_condenser_state(self) -> None:
        X_CO2 = self._X_CO2
        self.q_cooler = X_CO2 * self.pp.q_cooler
        self.q_condenser = X_CO2 * self.pp.q_condenser
        # self._condensation_temperature_range = self.pp.turbine_condenser.T.val - self.pp.connections['condenser_cooler'].T.val
        self._condensation_temperature_range = 3.0
        self.w_cooler = X_CO2 * self.q_cooler * self._get_parasitic_power_fraction_cooling() # (W)
        self.w_condenser = X_CO2 * self.q_condenser * self._get_parasitic_power_fraction_condensing() # (W)


    def _update_pump_state(self) -> None:
        X_CO2 = self._X_CO2
        self.P_out = self.pp.P_out + 10000000
        self.T_out = self.pp.T_out
        self.w_pump = X_CO2 * -self.pp.pump.P.val
        print(self.P_out, self.T_out)

    def _update_net_state(self) -> None:
        self.w_net = self.w_turbine + self.w_cooler + self.w_condenser + self.w_pump














class OrganicRankineCycle:
    def __init__(self, refrigerant='R245fa', pressure=20, temperature=110, mass_rate=30, working_fluid={'water': 1}):
        self.refrigerant = refrigerant
        self.pressure = pressure
        self.temperature = temperature
        self.mass_rate = mass_rate
        self.working_fluid = working_fluid
        self.nw = Network(p_unit='bar', T_unit='C', iterinfo=False)
        self._setup_components()
        self._setup_connections()
        self._configure_components()
        self.solve()
        print(self.pressure, self.temperature, self.mass_rate)

    def _setup_components(self):
        self.cc = CycleCloser('cycle closer')
        self.so1 = Source('source1')
        self.si1 = Sink('sink1')
        self.so2 = Source('source2')
        self.si2 = Sink('sink2')
        self.so3 = Source('source3')
        self.si3 = Sink('sink3')
        self.des = HeatExchanger('heat_exchanger')
        self.boiler = HeatExchanger('boiler')
        self.turbine = Turbine('turbine')
        self.condenser = SimpleHeatExchanger('condenser')
        self.pump = Compressor('pump')

    def _setup_connections(self):
        self.so1_des = Connection(self.so1, 'out1', self.des, 'in1')
        self.des_si1 = Connection(self.des, 'out1', self.si1, 'in1')
        self.cc_des = Connection(self.cc, 'out1', self.des, 'in2')
        self.des_turbine = Connection(self.des, 'out2', self.turbine, 'in1')
        self.turbine_condenser = Connection(self.turbine, 'out1', self.condenser, 'in1')
        self.condenser_pump = Connection(self.condenser, 'out1', self.pump, 'in1')
        self.pump_cc = Connection(self.pump, 'out1', self.cc, 'in1')

        self.nw.add_conns(self.so1_des, self.des_si1, self.cc_des, self.des_turbine, self.turbine_condenser, self.condenser_pump, self.pump_cc)

    def _configure_components(self):
        self.des.set_attr(pr1=1, pr2=1)
        self.so1_des.set_attr(fluid=self.working_fluid, T=self.temperature, p=self.pressure, m=self.mass_rate)
        saturation_temp = CP.PropsSI('T', 'P', 1100000, 'Q', 0, self.refrigerant) - 273.15
        self.cc_des.set_attr(fluid={self.refrigerant: 1}, p=11, m=35)
        self.des_turbine.set_attr(T=saturation_temp+0.2)
        self.turbine.set_attr(eta_s=1)
        self.turbine_condenser.set_attr(p=1)
        self.condenser_pump.set_attr(p=1, x=0)
        self.pump.set_attr(eta_s=1)

    def solve(self):
        self.nw.solve('design')
        self.nw.print_results()
        self._calculate_heat_transfers()

    def prepare_plot_data(self):
        self.nw.solve('design')

        p1 = self.so1_des.p.val
        h1 = self.so1_des.h.val/1000.0

        p3 = self.des_si1.p.val
        h3 = self.des_si1.h.val/1000.0

        p4 = self.cc_des.p.val
        h4 = self.cc_des.h.val/1000.0

        p5 = p4
        h5 = CP.PropsSI('H', 'P', p4*100000, 'Q', 0, self.refrigerant)/1000.0
        t5 = CP.PropsSI('T', 'P', p4*100000, 'H', h5*1000, self.refrigerant) - 273.15

        p2 = p1
        h2 = h1-h5+h4
        t2 = CP.PropsSI('T', 'P', p2*100000, 'H', h2*1000, self.refrigerant) - 273.15

        p6 = self.des_turbine.p.val
        h6 = self.des_turbine.h.val/1000.0

        p7 = self.turbine_condenser.p.val
        h7 = self.turbine_condenser.h.val/1000.0

        p8 = p7
        h8 = CP.PropsSI('H', 'P', p7*100000, 'Q', 1, self.refrigerant)/1000.0

        p9 = self.condenser_pump.p.val
        h9 = self.condenser_pump.h.val/1000.0

        points = {
            '1': {'h': h1, 'p': p1},
            '2': {'h': h2, 'p': p2},
            '3': {'h': h3, 'p': p3},
            '4': {'h': h4, 'p': p4},
            '5': {'h': h5, 'p': p5},
            '6': {'h': h6, 'p': p6},
            '7': {'h': h7, 'p': p7},
            '8': {'h': h8, 'p': p8},
            '9': {'h': h9, 'p': p9},
        }

        connections = [
            ('1', '2'),
            ('2', '3'),
            ('4', '5'),
            ('5', '6'),
            ('6', '7'),
            ('7', '8'),
            ('8', '9'),
            ('9', '4'),
        ]

        return points, connections

    def _calculate_heat_transfers(self):
        h1, h2, h3, h4, h5, h6, h7, h8, h9 = self._get_enthalpies()

        self.q_preheater = (h5 - h4) * self.turbine_condenser.m.val * 1000
        self.q_boiler = (h6 - h5) * self.turbine_condenser.m.val * 1000
        self.q_cooler = (h7 - h8) * self.turbine_condenser.m.val * 1000
        self.q_condenser = (h8 - h9) * self.turbine_condenser.m.val * 1000

        # Calculate temperatures based on enthalpies and pressures
        t2 = CP.PropsSI('T', 'P', self.so1_des.p.val*100000, 'H', h2*1000, self.refrigerant) - 273.15
        t5 = CP.PropsSI('T', 'P', self.cc_des.p.val*100000, 'H', h5*1000, self.refrigerant) - 273.15

        # Temperature differences for LMTD calculation
        # print('ttt = ', h1, h2, h3, h4, h5, h6, h7, h8, h9)
        dta_p = t2 - t5
        dtb_p = self.des_si1.T.val - self.cc_des.T.val
        dta_b = self.so1_des.T.val - t5
        dtb_b = dta_p

        # print('nnn = ', dta_p, dtb_p, dta_b, dtb_b)

        # Logarithmic Mean Temperature Difference (LMTD) calculations
        self.dT_LMTD_preheater = (dta_p - dtb_p) / (math.log(abs(dta_p/dtb_p)) * np.sign(dta_p/dtb_p))
        self.dT_LMTD_boiler = (dta_b - dtb_b) / (math.log(abs(dta_b/dtb_b)) * np.sign(dta_b/dtb_b))

        # Output temperature and pressure
        self.T_out = self.des_si1.T.val + 273.15
        self.P_out = self.des_si1.p.val * 1e5
        print('inside', self.T_out, self.P_out)

    def _get_enthalpies(self):
        # This is a utility function to extract the enthalpies after the network has been solved.
        # Modify this function based on how you store/access the connection objects in your class.
        h1 = self.so1_des.h.val / 1000.0
        # h2 = self.des_si1.h.val / 1000.0
        # h3 = h2  # Just an example, adjust according to your system
        h3 = self.des_si1.h.val/1000.0
        h4 = self.cc_des.h.val / 1000.0
        h5 = CP.PropsSI('H', 'P', self.cc_des.p.val*100000, 'Q', 0, self.refrigerant) / 1000.0
        h2 = h1-h5+h4
        # Continue for h6, h7, h8, h9 based on your system
        h6 = self.des_turbine.h.val / 1000.0
        h7 = self.turbine_condenser.h.val / 1000.0
        h8 = CP.PropsSI('H', 'P', self.turbine_condenser.p.val*100000, 'Q', 1, self.refrigerant) / 1000.0
        h9 = self.condenser_pump.h.val / 1000.0
        return h1, h2, h3, h4, h5, h6, h7, h8, h9
