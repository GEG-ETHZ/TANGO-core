import logging

from tango.units.dataclasses import CommonSpecs
from tango.units.native.surface.base import *
from dataclasses import dataclass

import csv
import os

@dataclass
class SurfaceSpecsCPGNative(CommonSpecs):
    r"""
    Specifications for a Surface Unit in a CO2 Thermosiphon System.

    Attributes:
        # pipe_diameter (float): Diameter of the pipe (m).
        # approach_temperature (float): Temperature difference between condensing and the surface temperature (K).
        # condensation_pressure_offset (float): Offset in condensation pressure (Pa).
        # temperature_range (float): Difference between inlet and exit fluid temperature (K).
        # eta_pump (float): Efficiency of the pump (-).
        # total_pipe_length (float): Total length of the pipe (m).
        # epsilon (float): Roughness of the surface pipe (m).
        # eta_turbine (float): Isentropic efficiency of the turbine (-).
        # cooling_tower_design (str): Design of the cooling tower ('CLOSED', etc.).
        # cooling_mode (str): Cooling mode ('WET', 'DRY').

    Methods:
        __post_init__: Ensures required fields are provided and validates input.
    """
    pipe_diameter: float = None
    approach_temperature: float = None
    condensation_pressure_offset: float = None
    temperature_range: float = 0.0
    eta_pump: float = 0.90
    total_pipe_length: float = None
    epsilon: float = 55.e-6
    eta_turbine: float = 0.78
    cooling_tower_design: str = 'CLOSED'
    cooling_mode: str = 'WET'

    def __post_init__(self):
        required_fields = ['pipe_diameter', 'approach_temperature', 'condensation_pressure_offset']
        for s in required_fields:
            if getattr(self, s, None) is None:
                raise RuntimeError(f"Required parameter: {s} is not found.")

class SurfaceUnitCPGNative(SurfaceUnitNative):
    r"""
    Native Surface Unit for CO2 Thermosiphon System based on Adams et al. (2015).

    Attributes:
        specs (SurfaceSpecsCPGNative): Specifications for the surface unit.
        iterative_inj_pressure (float): Injection pressure for iterative computations (Pa).
        iterative_inj_temperature (float): Injection temperature for iterative computations (K).
        reservoir_file_reader (bool): Indicates if reservoir file reading is enabled.
        cooler_include (bool): Indicates if a cooler is included in the system.
        current_row (int): Tracks the current row in the CSV file if flow rate is from a CSV.

    Methods:
        init_stream_interface: Initializes fluid state at the inlet and outlet streams.
        process_stream: Updates the system states and computes outputs.
        update_dP_pump: Updates the pump pressure drop.
        get_dP_pump: Retrieves the pump pressure drop.
    """

    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsCPGNative.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self._initialize_attributes()
        self.init_stream_interface()
        self.iterative_inj_pressure = 9000000
        self.iterative_inj_temperature = 302.0
        self.reservoir_file_reader = False
        self.cooler_include = False
        self.current_row = 0
        if self.specs.flow_rate_from_csv == 'yes':
            self.csv_data = self._read_csv_file()

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        """
        Initializes the fluid states for the CO2 thermosiphon system:
        production_well - turbine - condenser - pump - injection_well.
        """
        if P is not None and T is not None:
            self.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)

        self.mass_rate = self.specs.mass_flow_rate

        self.outlet_fluid_turbine = FluidState.withQT(self._fluid_name, Q=1.0, T=self._condensation_temperature)
        self.outlet_fluid_condenser = FluidState.withQT(self._fluid_name, Q=0.0, T=self._condensation_temperature)
        self.outlet_fluid_cooler = FluidState.withQT(self._fluid_name, Q=0.0, T=self._condensation_temperature)
        self.condensation_pressure = self.outlet_fluid_condenser.P + self.specs.condensation_pressure_offset
        self.condenser_saturated_vapor_h = FluidState.withPQ(self._fluid_name, Q=1.0, P=self.condensation_pressure).H
        self.condenser_saturated_liquid_h = FluidState.withPQ(self._fluid_name, Q=0.0, P=self.condensation_pressure).H
        self.inlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)
        self.outlet_fluid_pump = FluidState.withPT(self._fluid_name, self.condensation_pressure, self._condensation_temperature)

        self.outlet_fluid = FluidState.copy(self.outlet_fluid_pump)

    def process_stream(self) -> None:
        """
        Processes the stream by updating turbine, condenser, and pump states,
        and computes the net system performance.
        """
        if self.specs.flow_rate_from_csv == 'yes':
            if self.current_row < len(self.csv_data):
                row = self.csv_data[self.current_row]
                self.mass_rate = float(row[1])

        self._update_turbine_power()
        self._update_condenser_state()
        self._update_pump_state()
        self._update_net_state()

        self._update_diagram_states()
        self._update_diagram_connections()

        return self.P_out, self.T_out, self.mass_rate

    def _read_csv_file(self):
        """
        Reads flow rate data from a CSV file if specified in the configuration.

        Returns:
            list: Rows from the CSV file.
        """
        file_path = self.specs.flow_rate_file
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)

    def update_dP_pump(self, val) -> None:
        """
        Updates the pressure drop across the pump.

        Args:
            val (float): New pressure drop value.
        """
        self._dP_pump = val

    def get_dP_pump(self) -> float:
        """
        Retrieves the pressure drop across the pump.

        Returns:
            float: Current pressure drop.
        """
        return self._dP_pump

    def _specs_post_processor(self) -> float:
        """
        Processes the specifications for the fluid system.

        Updates the following attributes:
        - `self._fluid_name`: Sets the fluid name from the specifications.
        - `self._condensation_temperature`: Calculated as:
          .. math::

              T_{\text{condensation}} = T_{\text{surface}} + T_{\text{approach}}

          where `T_surface` is the surface temperature and `T_approach` is the approach temperature.
        - `self._X_CO2`: Sets to 1.0 if the fluid is CO₂, otherwise 0.0.

        TODO:
        - Implement a mechanism to extract CO₂ mass fraction (`X_CO2`) for multiphase flow.

        Returns:
            float: Placeholder return type.
        """
        self._fluid_name = self.specs.fluid_name
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._X_CO2 = 1.0 if self._fluid_name == 'CO2' else 0.0  # TODO: Multiphase flow handling
        self._set_mult()
        self._set_constants()

    def _initialize_attributes(self) -> float:
        """
        Initializes key attributes for the fluid system.

        Attributes:
        - `self._dP_pump`: Pressure drop across the pump (default: 0).
        - `self._condensation_temperature_range`: Placeholder for condensation temperature range.
        - `self.q_preheater`, `self.q_boiler`, `self.q_desuperheater`: Heat quantities for different stages of the process.

        TODO:
        - Remove placeholder initialization of `self._condensation_temperature_range`.

        Returns:
            float: Placeholder return type.
        """
        self._dP_pump: float = 0.
        self._condensation_temperature_range = 0
        self.q_preheater: float = 0.
        self.q_boiler: float = 0.
        self.q_desuperheater: float = 0.

    def _process_specs(self, specs) -> dict:
        """
        Combines common and surface-specific specifications.

        Args:
            specs (dict): Input specifications with keys `common` and `surface`.

        Returns:
            dict: Merged dictionary of specifications.
        """
        return specs['common'] | specs['surface']

    def _update_turbine_power(self) -> None:
        r"""
        Updates turbine power output based on inlet and outlet conditions.

        Calculations:
        - Updates turbine work output:

          .. math::

              W_{\text{turbine}} = X_{\text{CO2}} \cdot \dot{m} \cdot \eta \cdot (h_{\text{inlet}} - h_{s,\text{outlet}})

          where:

          - :math:`X_{\text{CO2}}` is the CO₂ mass fraction.

          - :math:`\dot{m}` is the mass flow rate.

          - :math:`\eta` is the turbine efficiency.

          - :math:`h_{\text{inlet}}` and :math:`h_{s,\text{outlet}}` are the inlet and ideal outlet specific enthalpies respectively.

        Returns:
            None
        """
        self.outlet_fluid_turbine.updatePS(P=self.condensation_pressure, S=self.inlet_fluid.S)
        hs_outlet = self.outlet_fluid_turbine.H  # Ideal enthalpy (J/kg)
        h_inlet = self.inlet_fluid.H  # (J/kg)
        eta = self.specs.eta_turbine  # Turbine efficiency (-)
        X_CO2 = self._X_CO2

        self.w_turbine = X_CO2 * self.mass_rate * eta * (h_inlet - hs_outlet)

    def _update_condenser_state(self) -> None:
        r"""
        Updates the state of the condenser, calculating required cooling and condensing work.

        Calculations:
        - Heat rejected in the condenser:

          .. math::

              Q_{\text{condenser}} = \dot{m} \cdot (h_{\text{condensed}} - h_{\text{turbine,outlet}})

        - If desuperheating is needed:

          .. math::

              Q_{\text{cooler}} = \dot{m} \cdot (h_{\text{saturated,vapor}} - h_{\text{turbine,outlet}})

        - Cooling and condensing parasitic power:

          .. math::

              W_{\text{cooler}} = X_{\text{CO2}} \cdot Q_{\text{cooler}} \cdot f_{\text{cooling}}

              W_{\text{condenser}} = X_{\text{CO2}} \cdot Q_{\text{condenser}} \cdot f_{\text{condensing}}

        Returns:
            None
        """
        hs_outlet = self.outlet_fluid_turbine.H  # Ideal enthalpy (J/kg)
        h_inlet = self.inlet_fluid.H  # (J/kg)
        eta = self.specs.eta_turbine
        X_CO2 = self._X_CO2
        h_saturated_vapor = self.condenser_saturated_vapor_h  # (J/kg)
        h_condensed = self.condenser_saturated_liquid_h  # (J/kg)
        h_turbine_outlet = h_inlet - eta * (h_inlet - hs_outlet)  # (J/kg)

        self.q_cooler = 0.0
        self.q_condenser = self.mass_rate * (h_condensed - h_turbine_outlet)
        if h_turbine_outlet > h_saturated_vapor:
            self.cooler_include = True
            self.q_cooler = self.mass_rate * (h_saturated_vapor - h_turbine_outlet)
            self.q_condenser = self.mass_rate * (h_condensed - h_saturated_vapor)
            T_turbine_outlet = FluidState.withHP(self._fluid_name, h_turbine_outlet, self.condensation_pressure).T
            self._condensation_temperature_range = T_turbine_outlet - self._condensation_temperature

        self.w_cooler = X_CO2 * self.q_cooler * self._get_parasitic_power_fraction_cooling()
        self.w_condenser = X_CO2 * self.q_condenser * self._get_parasitic_power_fraction_condensing()

        self.outlet_fluid_cooler.updateHP(h_saturated_vapor, self.condensation_pressure)
        self.outlet_fluid_condenser.updateHP(h_condensed, self.condensation_pressure)


    def _update_pump_state(self) -> None:
        r"""
        Updates the pump state based on the specified boundary condition checkpoint (BC iteration checkpoint).

        Depending on the BC checkpoint, updates the following attributes:
        - `self.P_out`: Outlet pressure of the pump.
        - `self.T_out`: Outlet temperature of the pump.
        - `self.w_pump`: Work done by the pump.

        Calculations:
        - Pump work:

          .. math::

              W_{\text{pump}} = -X_{\text{CO2}} \cdot \dot{m} \cdot (h_{\text{outlet}} - h_{\text{inlet}})

        Args:
            None

        Returns:
            None
        """
        eta = self.specs.eta_pump
        X_CO2 = self._X_CO2

        if self.specs.bc_iteration_checkpoint == 'injection_well_bottom':
            if self.reservoir_file_reader and self.specs.injection_condition_back_calculation == 'yes':
                self.P_out = self.iterative_inj_pressure
                self.T_out = self.iterative_inj_temperature
                self.outlet_fluid_pump.updatePT(self.P_out, self.T_out)
                self.w_pump = -1.0 * X_CO2 * self.mass_rate * (self.outlet_fluid_pump.H - self.inlet_fluid_pump.H)
            else:
                P_pump_outlet = self.iterative_inj_pressure
                h_pump_inlet = self.inlet_fluid_pump.H

                self.outlet_fluid_pump.updatePS(P=P_pump_outlet, S=self.inlet_fluid_pump.S)
                h_pump_outlet = h_pump_inlet + (self.outlet_fluid_pump.H - h_pump_inlet) / eta
                self.outlet_fluid_pump.updateHP(h_pump_outlet, P_pump_outlet)

                self.w_pump = -1.0 * X_CO2 * self.mass_rate * (h_pump_outlet - h_pump_inlet)
                self.P_out = P_pump_outlet
                self.T_out = self.outlet_fluid_pump.T

        elif self.specs.bc_iteration_checkpoint == 'production_well_bottom':
            if self.specs.injection_condition_back_calculation == 'yes':
                raise NotImplementedError("Injection condition back calculation is not supported for production well bottom.")
            if self.reservoir_file_reader:
                raise NotImplementedError("Reservoir file reader is not supported for production well bottom.")

            dP_pump = self.get_dP_pump()
            P_pump_outlet = self.condensation_pressure + dP_pump
            h_pump_inlet = self.inlet_fluid_pump.H
            h_pump_outlet = h_pump_inlet

            if dP_pump > 0:
                try:
                    self.outlet_fluid_pump.updatePS(P=P_pump_outlet, S=self.inlet_fluid_pump.S)
                except:
                    logging.warning("Failed to update fluid state with PS. Updating with PT instead.")
                    self.outlet_fluid_pump.updatePT(P=P_pump_outlet, T=self.inlet_fluid_pump.T)
                h_pump_outlet = h_pump_inlet + (self.outlet_fluid_pump.H - h_pump_inlet) / eta

            self.w_pump = -1.0 * X_CO2 * self.mass_rate * (h_pump_outlet - h_pump_inlet)
            P_inj_inlet = P_pump_outlet + min(0.0, dP_pump)
            self.P_out = P_inj_inlet
            self.T_out = self.outlet_fluid_pump.T

    def _update_net_state(self) -> None:
        """
        Updates the net work of the system by summing the work contributions from various components.

        Calculation:
        - Net work:

          .. math::

              W_{\text{net}} = W_{\text{turbine}} + W_{\text{cooler}} + W_{\text{condenser}} + W_{\text{pump}}

        Returns:
            None
        """
        self.w_net = self.w_turbine + self.w_cooler + self.w_condenser + self.w_pump

    def _update_diagram_states(self) -> None:
        """
        Updates the states for the system diagram.

        Attributes:
        - Adds turbine, cooler, and condenser states to the `diagram_states` dictionary.
        - Includes cooler state only if `self.cooler_include` is True.

        Returns:
            None
        """
        self.diagram_states['turbine'] = self.outlet_fluid_turbine
        if self.cooler_include:
            self.diagram_states['cooler'] = self.outlet_fluid_cooler
        self.diagram_states['condenser'] = self.outlet_fluid_condenser

    def _update_diagram_connections(self) -> None:
        """
        Updates the connections for the system diagram.

        Attributes:
        - Defines non-isentropic connections for various components.
        - Includes cooler connections only if `self.cooler_include` is True.

        Returns:
            None
        """
        if self.cooler_include:
            self.diagram_connections = [
                ('production_well', 'turbine', 'non-isentropic'),
                ('turbine', 'turbine', 'non-isentropic'),
                ('cooler', 'condenser', 'non-isentropic'),
                ('condenser', 'surface', 'non-isentropic')
            ]
        else:
            self.diagram_connections = [
                ('production_well', 'turbine', 'non-isentropic'),
                ('turbine', 'condenser', 'non-isentropic'),
                ('condenser', 'surface', 'non-isentropic')
            ]


