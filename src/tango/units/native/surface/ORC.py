from tango.core.constants import *
from tango.core.config import *
from tango.units.dataclasses import CommonSpecs
from tango.units.native.surface.base import *
from tango import utils
from dataclasses import dataclass

import logging
import math
import numpy as np
from scipy.interpolate import interp1d

import csv
import os


from dataclasses import dataclass

@dataclass
class SurfaceSpecsORCNative(CommonSpecs):
    """
    Surface specifications for Organic Rankine Cycle (ORC) systems.

    Attributes:
        # pipe_diameter (float): Diameter of the pipe (m).
        # approach_temperature (float): Temperature difference between condensing and surface temperature (K).
        # condensation_pressure_offset (float): Pressure offset for condensation (Pa).
        # refrigerant (str): Refrigerant type. Supported values are 'R600a' and 'R245fa'.
        # pinch_temperature (float): Pinch temperature in the system (default: 5.0 K).
        # temperature_range (float): Difference between inlet and outlet fluid temperature (default: 0.0 K).
        # eta_pump (float): Pump efficiency (default: 0.90).
        # total_pipe_length (float): Total length of the pipe per pattern (m).
        # epsilon (float): Roughness of the surface pipe (default: 55.e-6 m).
        # eta_turbine (float): Isentropic efficiency of the turbine (default: 0.78).
        # cooling_tower_design (str): Design of the cooling tower (default: 'CLOSED').
        # cooling_mode (str): Cooling mode, either 'WET' or 'DRY' (default: 'WET').
        # initial_outlet_pressure (float): Initial guess of outlet pressure (Pa) for ORC (default: 1.2e6 Pa).
        # initial_outlet_temperature (float): Initial guess of outlet temperature (K) for ORC (default: 333.15 K).
        # ORC_opt_mode (str): Optimization mode for ORC, either 'min_cost' or 'max_power' (default: 'min_cost').

    Raises:
        RuntimeError: If required fields are not provided during initialization.
        ValueError: If an unsupported refrigerant is provided.
    """

    pipe_diameter: float = None
    approach_temperature: float = None
    condensation_pressure_offset: float = None
    refrigerant: str = None
    pinch_temperature: float = 5.0
    temperature_range: float = 0.0
    eta_pump: float = 0.90
    total_pipe_length: float = None
    epsilon: float = 55.e-6
    eta_turbine: float = 0.78
    cooling_tower_design: str = 'CLOSED'
    cooling_mode: str = 'WET'
    initial_outlet_pressure: float = 1.2e6
    initial_outlet_temperature: float = 333.15
    ORC_opt_mode: str = 'min_cost'

    def __post_init__(self):
        """
        Validates the required fields and refrigerant options after initialization.
        """
        required_fields = ['pipe_diameter', 'approach_temperature', 'condensation_pressure_offset', 'refrigerant']
        for s in required_fields:
            if getattr(self, s, None) is None:
                raise RuntimeError(f"Required parameter: {s} is not found.")

        refrigerant_options = ['R600a', 'R245fa']
        if self.refrigerant not in refrigerant_options:
            raise ValueError(f"refrigerant: {self.refrigerant} is not supported. Available options: {refrigerant_options}")


class SurfaceUnitORCNative(SurfaceUnitNative):
    """
    Represents a power plant unit based on Organic Rankine Cycle (ORC) principles.

    Inherits from `SurfaceUnitNative`.

    Attributes:
        id (str): Unique identifier for the unit.
        specs (SurfaceSpecsORCNative): Specifications for the ORC system.
    """

    def __init__(self, id: str, specs: dict):
        """
        Initializes the SurfaceUnitORCNative object.

        Args:
            id (str): Unique identifier for the unit.
            specs (dict): Dictionary containing the specifications for the ORC unit.
        """
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsORCNative.from_dict(self._process_specs(specs))
        self._specs_post_processor()
        self._initialize_attributes()
        self.init_stream_interface()
        self.iterative_inj_pressure = 1_000_000  # 1 MPa
        self.iterative_inj_temperature = 302.0  # 302 K
        self.reservoir_file_reader = False
        self.current_row = 0

        if self.specs.flow_rate_from_csv == 'yes':
            self.csv_data = self._read_csv_file()

    def init_stream_interface(self, P: float=None, T: float=None) -> None:
        """
        Initializes the fluid stream interface.

        Args:
            P (float, optional): Initial pressure for the fluid (default: specs.initial_outlet_pressure).
            T (float, optional): Initial temperature for the fluid (default: specs.initial_outlet_temperature).
        """
        P = self.specs.initial_outlet_pressure if P is None else P
        T = self.specs.initial_outlet_temperature if T is None else T
        self.mass_rate = self.specs.mass_flow_rate
        self.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)
        self.outlet_fluid = FluidState.withPT(self._fluid_name, P, T)

    def process_stream(self) -> None:
        """
        Processes the fluid stream and updates state variables.

        If flow rate data is provided via a CSV file, updates the mass rate based on the current row.
        Also updates the diagram states and connections.

        Returns:
            tuple: Outlet pressure, outlet temperature, and mass rate.
        """
        if self.specs.flow_rate_from_csv == 'yes':
            if self.current_row < len(self.csv_data):
                row = self.csv_data[self.current_row]
                self.mass_rate = float(row[1])

        self._update_state_pipe()
        self._update_state_fluid()

        self._update_diagram_states()
        self._update_diagram_connections()
        print(self.P_out, self.T_out, self.mass_rate, 'process')

        return self.P_out, self.T_out, self.mass_rate

    def overwrite_state_pipe(self) -> None:
        """
        Updates the state of the pipe.
        """
        self._update_state_pipe()

    def _read_csv_file(self):
        """
        Reads flow rate data from a CSV file specified in the specifications.

        Returns:
            list: List of rows from the CSV file.

        Raises:
            FileNotFoundError: If the specified file does not exist.
        """
        file_path = self.specs.flow_rate_file
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)


    def _specs_post_processor(self) -> float:
        r"""
        Processes the specifications for the ORC system and computes derived attributes.

        Derived attributes include:

        - `self._fluid_name`: Name of the fluid.
        - `self._refrigerant_name`: Name of the refrigerant.
        - `self._cross_sectional_area`: Cross-sectional area of the pipe, calculated as:

          .. math::

              A = 0.25 \cdot \pi \cdot d^2

          where `d` is the pipe diameter.
        - `self._condensation_temperature`: Calculated as:

          .. math::

              T_{\text{condensation}} = T_{\text{surface}} + T_{\text{approach}}

        Returns:
            float: Placeholder return type.
        """
        self._fluid_name = self.specs.fluid_name
        self._refrigerant_name = self.specs.refrigerant
        self._cross_sectional_area = 0.25 * np.pi * self.specs.pipe_diameter ** 2
        self._condensation_temperature = self.specs.surface_temperature + self.specs.approach_temperature
        self._set_mult()
        self._set_constants()
        self._set_max_boiling_temperature()
        self._set_lookup_tables()

    def _initialize_attributes(self) -> float:
        """
        Initializes essential attributes for calculations.

        Attributes initialized:
        - `dT_LMTD_recuperator` (float): Log mean temperature difference for the recuperator.
        - `w_downhole_pump` (float): Work done by the downhole pump.
        - `q_cooler` (float): Heat rejected by the cooler.

        Returns:
            float: Placeholder return type.
        """
        self.dT_LMTD_recuperator: float = 0.0
        self.w_downhole_pump: float = 0.0
        self.q_cooler: float = 0.0

    def _process_specs(self, specs) -> dict:
        """
        Combines common and surface-specific specifications.

        Args:
            specs (dict): Input specifications.

        Returns:
            dict: Merged dictionary of specifications.
        """
        return self.specs['common'] | self.specs['surface']

    def _set_max_boiling_temperature(self) -> None:
        """
        Computes the maximum boiling temperature of the organic fluid.

        The temperature is determined at the pressure corresponding to the maximum saturated vapor entropy.
        Steps:
        - Determine critical pressure and entropy at various pressures.
        - Find the pressure and temperature where entropy is maximum.

        Returns:
            None
        """
        self._ORC_fluid_state = FluidState.withPT(
            self._refrigerant_name,
            P=self.specs.initial_outlet_pressure,
            T=self.specs.initial_outlet_temperature
        )
        ORC_fluid_Pcrit = self._ORC_fluid_state.Pcrit
        P_min = FluidState.withQT(self._refrigerant_name, Q=1.0, T=273.15).P
        P_arr = np.linspace(P_min, ORC_fluid_Pcrit, 1000)
        S_arr = np.zeros(len(P_arr))

        for i, P in enumerate(P_arr):
            S_arr[i] = FluidState.withPQ(self._refrigerant_name, P=P, Q=1.0).S

        S_max = np.max(S_arr)
        P_max = P_arr[np.argmax(S_arr)]
        self._max_boiling_temperature = FluidState.withPS(
            self._refrigerant_name, P=P_max, S=S_max).T

    def _set_lookup_tables(self) -> None:
        """
        Sets up lookup tables for the ORC boiling point optimization.

        The table filename is determined based on the optimization mode and refrigerant.

        Returns:
            None
        """
        fname = f"ORC_Tboil_optimum_{MAP_ORC_OPTNAME_TO_TABLE_NAME[self.specs.ORC_opt_mode]}_{self._refrigerant_name}.csv"
        self._ORC_Tboil_optimum_table = utils.get_table(fname)

    def _get_value_from_table(self, x: float, col_name: str) -> float:
        """
        Retrieves interpolated or extrapolated values from the lookup table.

        Args:
            x (float): Temperature in Kelvin.
            col_name (str): Column name, e.g., 'T_boil_C' or 'dT_pinch_C'.

        Returns:
            float: Interpolated or extrapolated value.

        Warnings:
            If `x` is outside the interpolation range, a warning is logged, and extrapolation is performed.
        """
        x += K_TO_C
        df = self._ORC_Tboil_optimum_table
        val = float(interp1d(df.T_C, df[col_name], bounds_error=False, kind='linear')(x))
        if np.isnan(val):
            logging.warning(
                f"A value {x} is outside the interpolation range in ORC_Tboil_optimum_table. "
                f"Extrapolating a value for {col_name}."
            )
            return float(
                interp1d(df.T_C, df[col_name], bounds_error=False, fill_value='extrapolate', kind='linear')(x))
        return val

    def _compute_friction_factor(self, rho: float, mu: float, u: float) -> float:
        r"""
        Computes the friction factor using the Haaland equation (1983).

        Equation:

        .. math::

            f = \left[ -1.8 \cdot \log_{10} \left( \frac{\epsilon / d}{3.7}^{1.11} + \frac{6.9}{Re} \right) \right]^{-2}

        Args:
            rho (float): Fluid density (kg/m³).
            mu (float): Dynamic viscosity (Pa·s).
            u (float): Flow velocity (m/s).

        Returns:
            float: Friction factor (-).
        """
        d = self.specs.pipe_diameter
        epsilon = self.specs.epsilon
        Re = rho * u * d / mu
        r = epsilon / d
        return (-1.8 * np.log10((r / 3.7) ** 1.11 + 6.9 / Re)) ** -2.0

    def _get_pipe_pressure_drop(self, rho: float, u: float, ff: float) -> float:
        r"""
        Computes the pressure drop across the pipe.

        Equation:

        .. math::

            \Delta P = 0.5 \cdot f \cdot L \cdot \rho \cdot u^2 / d

        Args:
            rho (float): Fluid density (kg/m³).
            u (float): Flow velocity (m/s).
            ff (float): Friction factor.

        Returns:
            float: Pressure drop (Pa).
        """
        d = self.specs.pipe_diameter
        L = self.specs.well_spacing
        return 0.5 * ff * L * rho * u ** 2 / d


    def _update_state_pipe(self) -> None:
        r"""
        Updates the state of the fluid in the surface pipe, accounting for pressure drops.

        The pressure drop is computed based on the pipe's cross-sectional area, fluid density,
        viscosity, flow velocity, and friction factor.

        Steps:
        - Calculate the flow velocity:

          .. math::

              u = \frac{\dot{m}}{A \cdot \rho}

          where:
          - :math:`\dot{m}` is the mass flow rate (kg/s),
          - :math:`A` is the cross-sectional area of the pipe (m²),
          - :math:`\rho` is the fluid density (kg/m³).

        - Compute the friction factor using the Haaland equation.
        - Calculate the pressure drop:

          .. math::

              \Delta P = 0.5 \cdot f \cdot L \cdot \rho \cdot u^2 / d

        - Update the inlet fluid state to account for the pressure drop.

        Returns:
            None
        """
        rho = self.inlet_fluid.rho
        mu = self.inlet_fluid.mu
        mdot = 1.0 / self._m_dot_mult * self.mass_rate
        u = mdot / self._cross_sectional_area / rho
        ff = self._compute_friction_factor(rho, mu, u)
        self.dP_pipe = self._get_pipe_pressure_drop(rho, u, ff)
        self.inlet_fluid.updatePT(P=self.inlet_fluid.P - self.dP_pipe, T=self.inlet_fluid.T)

    def _get_values_from_table(self, T_inlet: float) -> tuple:
        """
        Retrieves boiling temperature and pinch temperature difference from the lookup table.

        Args:
            T_inlet (float): Inlet temperature in Kelvin.

        Returns:
            tuple: A tuple containing boiling temperature (K) and pinch temperature difference (K).

        Raises:
            ValueError: If any of the following issues are detected:
                - Boiling temperature or pinch temperature difference is NaN.
                - Boiling temperature exceeds the critical temperature.
                - Pinch temperature difference is negative.
        """
        T_boiling = self._get_value_from_table(x=T_inlet, col_name='T_boil_C') + C_TO_K
        dT_pinch = self._get_value_from_table(x=T_inlet, col_name='dT_pinch_C')
        if np.isnan(T_boiling):
            raise ValueError("Nan ORC T_boiling found.")
        if np.isnan(dT_pinch):
            raise ValueError("Nan ORC dT_pinch found.")
        if T_boiling > self._ORC_fluid_state.Tcrit:
            raise ValueError("ORC T_boiling is greater than critical point.")
        if dT_pinch < 0:
            raise ValueError("Negative ORC dT_pinch found.")
        return T_boiling, dT_pinch



    def _update_state_fluid(self) -> None:
        r"""
        Updates the thermodynamic states of the working fluid and water throughout the ORC cycle.

        Key steps and calculations:

        1. **Retrieve Boiling and Pinch Temperatures**:
           - `T_boiling` and `dT_pinch` are retrieved from the lookup table based on the inlet temperature.

        2. **State Updates for Major Components**:

           - State 1: Condenser outlet -> Pump inlet (saturated liquid).
           - State 6: Cooler outlet -> Condenser inlet (saturated vapor).
           - State 3: Preheater outlet -> Boiler inlet (saturated liquid at boiling temperature).
           - State 4: Boiler outlet -> Turbine inlet (saturated vapor at boiling temperature).
           - State 5: Turbine outlet -> Cooler inlet (isentropic relations with turbine efficiency).

        3. **Auxiliary Heat/Work Calculations**:
           - Heat/work exchanges for each component are calculated based on enthalpy differences.

        4. **Cooling Tower and Parasitic Loads**:
           - The condensation temperature range and cooling tower parasitic loads are computed.

        5. **Water Heat Exchange**:
           - Assumes pressure 100 kPa above saturation pressure.
           - Ensures pinch constraints at the preheater outlet.

        6. **Log Mean Temperature Differences (LMTD)**:
           - Calculated for the preheater and boiler sections using:

             .. math::

                \Delta T_{\text{LMTD}} = \frac{\Delta T_A - \Delta T_B}{\ln\left(\left| \frac{\Delta T_A}{\Delta T_B} \right|\right) \cdot \text{sign}(\Delta T_A / \Delta T_B)}

        7. **Boundary Condition Checkpoints**:
           - Determines outlet pressure and temperature based on `bc_iteration_checkpoint` and optionally computes thermal power if a cascade power plant is in use.

        Raises:
            NotImplementedError: If cascade power plant mode is used with `production_well_bottom`.

        Returns:
            None
        """
        T_inlet = self.inlet_fluid.T
        T_boiling, dT_pinch = self._get_values_from_table(T_inlet)

        # State 1 (Condenser -> Pump)
        fluid_state_pump_inlet = FluidState.withQT(self._refrigerant_name, Q=0.0, T=self._condensation_temperature)
        self.condenser = fluid_state_pump_inlet

        # State 6 (Cooler -> Condenser)
        fluid_state_condenser_inlet = FluidState.withQT(self._refrigerant_name, Q=1.0, T=fluid_state_pump_inlet.T)
        self.cooler = fluid_state_condenser_inlet

        # State 3 (Preheater -> Boiler)
        fluid_state_boiler_inlet = FluidState.withQT(self._refrigerant_name, Q=0.0, T=T_boiling)
        self.pre_heater = fluid_state_boiler_inlet

        # State 4 (Boiler -> Turbine)
        fluid_state_turbine_inlet = FluidState.withQT(self._refrigerant_name, Q=1.0, T=fluid_state_boiler_inlet.T)
        self.boiler = fluid_state_turbine_inlet

        # State 5 (Turbine -> Cooler)
        fluid_state_cooler_inlet = FluidState.withPS(self._refrigerant_name, P=fluid_state_pump_inlet.P, S=fluid_state_turbine_inlet.S)
        hs_cooler_inlet = fluid_state_cooler_inlet.H
        h_cooler_inlet = fluid_state_turbine_inlet.H - self.specs.eta_turbine * (fluid_state_turbine_inlet.H - hs_cooler_inlet)
        fluid_state_cooler = FluidState.withHP(self._refrigerant_name, H=h_cooler_inlet, P=fluid_state_pump_inlet.P)
        self.turbine = fluid_state_cooler

        # State 2 (Pump -> Preheater)
        fluid_state_preheater_inlet = FluidState.withPS(self._refrigerant_name, P=fluid_state_boiler_inlet.P, S=fluid_state_pump_inlet.S)
        hs_preheater_inlet = fluid_state_preheater_inlet.H
        h_preheater = fluid_state_pump_inlet.H - ((fluid_state_pump_inlet.H - hs_preheater_inlet) / self.specs.eta_pump)
        fluid_state_preheater = FluidState.withHP(self._refrigerant_name, H=h_preheater, P=fluid_state_boiler_inlet.P)
        self.pump = fluid_state_preheater

        # Auxiliary heat/work
        self.aux_w_pump = fluid_state_pump_inlet.H - fluid_state_preheater.H
        self.aux_q_preheater = fluid_state_boiler_inlet.H - fluid_state_preheater.H
        self.aux_q_boiler = fluid_state_turbine_inlet.H - fluid_state_boiler_inlet.H
        self.aux_w_turbine = fluid_state_turbine_inlet.H - fluid_state_cooler.H
        self.aux_q_cooler = fluid_state_condenser_inlet.H - fluid_state_cooler.H
        self.aux_q_condenser = fluid_state_pump_inlet.H - fluid_state_condenser_inlet.H

        # Cooling tower parasitic loads
        self._condensation_temperature_range = fluid_state_cooler.T - fluid_state_condenser_inlet.T
        self.aux_w_cooler = self.aux_q_cooler * self._get_parasitic_power_fraction_cooling()
        self.aux_w_condenser = self.aux_q_condenser * self._get_parasitic_power_fraction_condensing()

        #
        # ... Water (assume pressure 100 kPa above saturation)
        #

        fluid_state_water = FluidState.withQT(self._fluid_name, Q=0., T=T_inlet)
        Psat_water = fluid_state_water.P
        cp_water = fluid_state_water.cp

        # Water state 11, inlet, 12, mid, 13 exit
        fluid_state_water = FluidState.withQT(self._fluid_name, Q=0.0, T=T_inlet)
        Psat_water = fluid_state_water.P
        cp_water = fluid_state_water.cp
        T_11 = T_inlet
        T_12 = T_boiling + dT_pinch
        mdot_ratio = cp_water * (T_11 - T_12) / self.aux_q_boiler
        T_13 = T_12 - mdot_ratio * self.aux_q_preheater / cp_water

        if T_13 < (fluid_state_preheater.T + dT_pinch):
            T_13 = fluid_state_preheater.T + dT_pinch
            R = self.aux_q_boiler / (self.aux_q_boiler + self.aux_q_preheater)
            T_12 = T_11 - (T_11 - T_13) * R
            mdot_ratio = cp_water * (T_11 - T_12) / self.aux_q_boiler

        # Calculate water heat/work
        self.q_preheater = mdot_ratio * self.mass_rate * self.aux_q_preheater
        self.q_boiler = mdot_ratio * self.mass_rate * self.aux_q_boiler
        self.q_desuperheater = mdot_ratio * self.mass_rate * self.aux_q_cooler
        self.q_condenser = mdot_ratio * self.mass_rate * self.aux_q_condenser
        # TODO: self._ORC_state.q_recuperator should be defined!
        self.q_recuperator = 0
        self.w_turbine = mdot_ratio * self.mass_rate * self.aux_w_turbine
        self.w_pump = mdot_ratio * self.mass_rate * self.aux_w_pump
        self.w_cooler = mdot_ratio * self.mass_rate * self.aux_w_cooler
        self.w_condenser = mdot_ratio * self.mass_rate * self.aux_w_condenser
        self.w_net = self.w_turbine + self.w_pump + self.w_cooler + self.w_condenser

        # Calculate temperatures
        self.dT_range_CT = fluid_state_cooler.T - fluid_state_condenser_inlet.T
        dT_A_p = T_13 - fluid_state_preheater.T
        dT_B_p = T_12 - fluid_state_boiler_inlet.T
        # print('aaa', T_12, T_13)

        if dT_A_p == dT_B_p:
            self.dT_LMTD_preheater = dT_A_p
        else:
            div = dT_A_p/dT_B_p
            self.dT_LMTD_preheater = (dT_A_p - dT_B_p) / (math.log(abs(div)) * np.sign(div))

        dT_A_b = T_12 - fluid_state_boiler_inlet.T
        dT_B_b = T_11 - fluid_state_turbine_inlet.T

        if dT_A_b == dT_B_b:
            self.dT_LMTD_boiler = dT_A_b
        else:
            div = dT_A_b / dT_B_b
            self.dT_LMTD_boiler = (dT_A_b - dT_B_b) / (math.log(abs(div)) * np.sign(div))

        if self.specs.bc_iteration_checkpoint == 'injection_well_bottom':
            if self.reservoir_file_reader and self.specs.injection_condition_back_calculation == 'yes':
                self.P_out = self.iterative_inj_pressure
                self.T_out = self.iterative_inj_temperature
            else:
                self.P_out = self.iterative_inj_pressure
                self.T_out = T_13

            if self.specs.cascade_power_plant == 'yes':
                self.lulu = FluidState.withPT(self._fluid_name, P=self.inlet_fluid.P, T=T_13)
                self.lulu_out = FluidState.withPT(self._fluid_name, P=self.iterative_inj_pressure, T=self.iterative_inj_temperature)
                self.thermal_power = self.mass_rate * (self.lulu.H - self.lulu_out.H)
        elif self.specs.bc_iteration_checkpoint == 'production_well_bottom':
            self.P_out = self.inlet_fluid.P
            self.T_out = T_13

            if self.specs.cascade_power_plant == 'yes':
                raise NotImplementedError("Cascade power plant is not supported for production_well_bottom.")

    def _update_diagram_states(self) -> None:
        """
        Updates the system's diagram states to include major components.

        The following components are added to `self.diagram_states`:
        - Pre-Heater
        - Boiler
        - Cooler
        - Condenser
        - Turbine
        - Pump

        Returns:
            None
        """
        self.diagram_states['Pre_Heater'] = self.pre_heater
        self.diagram_states['Boiler'] = self.boiler
        self.diagram_states['Cooler'] = self.cooler
        self.diagram_states['Condenser'] = self.condenser
        self.diagram_states['Turbine'] = self.turbine
        self.diagram_states['Pump'] = self.pump

    def _update_diagram_connections(self) -> None:
        """
        Updates the system's diagram connections to represent the thermodynamic cycle.

        Connections are specified as tuples of:
        - Starting component
        - Ending component
        - Connection type ('non-isentropic').

        Example connections:
        - ('Pre_Heater', 'Boiler', 'non-isentropic')
        - ('Pump', 'Pre_Heater', 'non-isentropic')

        Returns:
            None
        """
        self.diagram_connections = [
            ('Pre_Heater', 'Boiler', 'non-isentropic'),
            ('Boiler', 'Turbine', 'non-isentropic'),
            ('Turbine', 'Cooler', 'non-isentropic'),
            ('Cooler', 'Condenser', 'non-isentropic'),
            ('Condenser', 'Pump', 'non-isentropic'),
            ('Pump', 'Pre_Heater', 'non-isentropic')
        ]
