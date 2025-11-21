from dataclasses import dataclass
import yaml
from tespy.components import (
    Sink,
    Source,
    Turbine,
    SimpleHeatExchanger,
    Compressor,
    Valve,
    DropletSeparator,
    Merge,
    HeatExchanger,
    CycleCloser
)
from tespy.connections import Connection
from tespy.networks import Network
import numpy as np
from tabulate import tabulate
from termcolor import colored
from itertools import cycle
from copy import copy

from tango.units.dataclasses import CommonSpecs
from tango.units.native.surface.base import SurfaceUnitNative
from tango.core.fluidstate import FluidState
from tango.function_evaluator import FunctionEvaluator
from tango.parameter_mappings import TARGET_PARAMETER_MAPPING, VARIABLE_PARAMETER_MAPPING
from tango.core.constants import BAR_TO_PA, PA_TO_BAR, C_TO_K, K_TO_C, BAR_TO_MPA, MPA_TO_PA


@dataclass
class SurfaceSpecsFlexiblePP(CommonSpecs):

    pipe_diameter: float = None
    approach_temperature: float = None
    epsilon: float = 55.e-6
    temperature_range: float = 0.0

    def __post_init__(self):
        required_fields = ['pipe_diameter']
        for s in required_fields:
            if getattr(self, s, None) is None:
                raise RuntimeError(f"Required parameter: {s} is not found.")


class SurfaceUnitFlexiblePP(SurfaceUnitNative):
    def __init__(self, id: str, specs: dict):
        SurfaceUnitNative.__init__(self, id, specs)
        self.specs = SurfaceSpecsFlexiblePP.from_dict(self._process_specs(specs))
        self.specs.new_config = self._filter_power_plant_graph(specs)
        self.specs.org = specs
        self._fluid_name = self.specs.fluid_name
        self._m_dot_mult = 1
        self.current_row = 0
        self.prod_pump_w_list = []
        self.init_stream_interface()
        self.power_plant = PowerPlant(self.specs)

    def _filter_power_plant_graph(self, specs: dict):
        """Filters and retains only the power_plant_graph, including nodes, edges, and their specifications."""
        if "power_plant_graph" not in specs:
            return {}

        filtered_specs = {"power_plant_graph": specs["power_plant_graph"]}

        # Add specifications for nodes if they exist in the main specs
        for node in specs["power_plant_graph"].get("nodes", {}):
            if node in specs:
                filtered_specs[node] = specs[node]

        return filtered_specs

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        """
        Initializes the fluid states for the CO2 thermosiphon system:
        production_well - turbine - condenser - pump - injection_well.
        """
        if P is not None and T is not None:
            self.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)

        self.mass_rate = (
            self.specs.mass_flow_rate * self.specs.well_pattern_dimens[0] * self.specs.well_pattern_dimens[1]
                / self.specs.num_pp
        )
        self.outlet_fluid = FluidState.withPT(self.specs.fluid_name, 10000000.0, 290.0)

    def process_stream(self) -> tuple[float, float, float]:
        """
        Processes the stream by [float, float, float]updating turbine, condenser, and pump states,
        and computes the net system performance.

        # Returns
        # - power plant outlet pressure [Pa]
        # - power plant outlet temperature [K]
        # - mass flow rate
        """
        self._update_state_pipe()
        self.power_plant.set_attributes(
            fluid={self.specs.fluid_name: 1},
            mass_rate=self.mass_rate,
            # this expects bar
            production_pressure=self.inlet_fluid.P * PA_TO_BAR,
            # this expects degrees Celsius
            production_temperature=self.inlet_fluid.T + K_TO_C
        )
        self.power_plant.network.solve('design')
        outlet_state = self.power_plant.get_outlet_conditions()
        self.w_net = self.power_plant.calculate_net_power()

        ps_out = (
            outlet_state['pressure'] * MPA_TO_PA,
            outlet_state['temperature'] + C_TO_K,
            self.mass_rate,
        )

        return ps_out

    def flow_res(self, te: float, p: float, mdot: float) -> float:
        r"""Return surface pipe approximate flow resistance [Pa / (kg / s)]

        This approximates the flow resistance based on fluid properties evaluated at the well inlet.

        # Arguments
        - `te`: estimated temperature [K] for property evaluations
        - `p`: estimated pressure [Pa] for property evaluations
        - `mdot`: mass flow rate [kg/s]
        """

        pipe_inlet_fluid = copy(self.inlet_fluid)
        pipe_inlet_fluid.updatePT(P=p, T=te)
        rho = self.inlet_fluid.rho
        mu = self.inlet_fluid.mu
        # divide mdot by the number of wells in the well pattern
        mdot_pipe = 1.0 / self._m_dot_mult * mdot
        u = mdot_pipe / (0.25 * np.pi * self.specs.pipe_diameter ** 2) / rho
        ff = self._compute_friction_factor(rho, mu, u)
        dP_pipe = self._get_pipe_pressure_drop(rho, u, ff)
        # this uses total mass flow rate through the power plant and total pressure drop through both the
        # surface pipes but does not account for the pressure change through the power plant because this is
        # not a flow resistance and some condensation is expected in the power plant
        flow_res_dp_per_mass_rate: float = mdot / dP_pipe
        return flow_res_dp_per_mass_rate

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
        u = mdot / (0.25 * np.pi * self.specs.pipe_diameter ** 2) / rho
        ff = self._compute_friction_factor(rho, mu, u)
        self.dP_pipe = self._get_pipe_pressure_drop(rho, u, ff)
        # NOTE: it seems like it would be better to have separate `FluidState`
        # attrtibutes to track fluid state at pipe inlet and fluid state at pipe
        # outlet, rather than just overwriting the `inlet_fluid` with the pipe
        # outlet state
        # Also, it would be good to have a `history` attribute that tracks both of these through time so that
        # we have that information in the results
        self.inlet_fluid.updatePT(P=self.inlet_fluid.P - self.dP_pipe, T=self.inlet_fluid.T)

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
        ff: float = (-1.8 * np.log10((r / 3.7) ** 1.11 + 6.9 / Re)) ** -2.0
        return ff

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
        dP_pipe: float = 0.5 * ff * L * rho * u ** 2 / d
        return dP_pipe

    def _process_specs(self, specs) -> dict:
        """
        Combines common and surface-specific specifications.

        Args:
            specs (dict): Input specifications with keys `common` and `surface`.

        Returns:
            dict: Merged dictionary of specifications.
        """
        return specs['common'] | specs['surface']

class PowerPlant:
    """
    A class representing a power plant model built using TESPy components and connections.

    Attributes:
        function_evaluator (FunctionEvaluator): An instance used for evaluating mathematical functions.
        funcs (dict): A dictionary containing evaluated functions.
        iterative_inj_pressure (float): The iterative injection pressure for the system.
        pp_specs (object): The specifications object containing the configuration details.
        config (dict): Configuration settings for the power plant.
        nodes (dict): A dictionary of TESPy components representing power plant units.
        connections (list): A list of TESPy connections between the components.
        network (Network): A TESPy network containing all system components and connections.

    Args:
        specs (object): An object containing the specifications and configuration for the power plant.
    """
    def __init__(self, specs):

        self.function_evaluator = FunctionEvaluator(
            target_mapping=TARGET_PARAMETER_MAPPING,
            variable_mapping=VARIABLE_PARAMETER_MAPPING,
            orchestrator=None,
            economic=None
        )
        
        self._specs = specs
        self._functions_evaluated = False
        
        self.funcs = {}
        self.iterative_inj_pressure = 9100000
        self.pp_specs = specs
        self.config = self.pp_specs.new_config

        self.nodes = {}
        for node_name, node_data in self.config['power_plant_graph']['nodes'].items():
            self.nodes[node_name] = self._create_component(node_data['type'], node_name)

        self.connections = []
        for edge_id, edge_data in self.config['power_plant_graph']['edges'].items():
            source = self.nodes[edge_data['source']]
            target = self.nodes[edge_data['target']]
            source_port = edge_data.get('source_port', 'out1')
            target_port = edge_data.get('target_port', 'in1')
            connection = Connection(source, source_port, target, target_port)
            self.connections.append(connection)

        self.network = Network(p_unit='bar', T_unit='C', h_unit='kJ / kg', iterinfo=False)
        self.network.add_conns(*self.connections)

    def set_context(self, context):
        """
        Sets the context for the function evaluator and evaluates functions if not already done.
        
        Args:
            context (object): The context object (e.g., NativeWorkflow instance).
        """
        self.function_evaluator.set_context(context)
        
        if not self._functions_evaluated and 'functions' in self._specs.org and self._specs.org['functions']:
            self.function_evaluator.evaluate_functions(self._specs.org['functions'])
            self._functions_evaluated = True
            self.funcs = self.function_evaluator.evaluated_functions

    def get_funcs(self):
        """
        Gets the evaluated functions, with fallback to main workflow if needed.
        
        Returns:
            dict: Dictionary of evaluated functions.
        """
        if not self.funcs and hasattr(self, 'context') and self.context:
            if hasattr(self.context, 'function_evaluator'):
                return self.context.function_evaluator.evaluated_functions
        return self.funcs

    def _create_component(self, component_type, name):
        """
        Creates and returns a TESPy component based on the specified type.

        This method maps the component type to its corresponding TESPy class and
        initializes an instance of that component.

        Args:
            component_type (str): The type of the component (e.g., 'Turbine', 'Valve', 'HeatExchanger').
            name (str): The name to assign to the component.

        Returns:
            object: An instance of the specified TESPy component.

        Raises:
            KeyError: If the provided component type is not recognized.
        """
        component_mapping = {
            'Sink': Sink,
            'Source': Source,
            'Turbine': Turbine,
            'SimpleHeatExchanger': SimpleHeatExchanger,
            'Compressor': Compressor,
            'Valve': Valve,
            'DropletSeparator': DropletSeparator,
            'Merge': Merge,
            'HeatExchanger': HeatExchanger,
            'CycleCloser': CycleCloser
        }
        return component_mapping[component_type](name)

    def set_attributes(self, fluid, mass_rate, production_pressure, production_temperature):
        """
        Sets the attributes of the power plant components and connections.

        This method assigns operational parameters such as fluid properties,
        mass flow rate, pressure, and temperature to the TESPy components
        and their respective connections based on the power plant configuration.

        Args:
            fluid (dict): A dictionary specifying the fluid composition for the system.
            mass_rate (float): The mass flow rate of the working fluid (kg/s).
            production_pressure (float): The production pressure of the working fluid (Pa).
            production_temperature (float): The production temperature of the working fluid (°C).

        Notes:
            - Attributes are dynamically assigned based on the power plant configuration.
            - Special handling is applied for different component types (e.g., `Source`, `Sink`, `Valve`, `Turbine`).
            - Function mappings (`self.funcs`) are used to evaluate attribute values when specified as strings.
        """
        for component_name, attributes in self.config.items():
            if component_name in self.nodes:
                component = self.nodes[component_name]
                adjusted_attributes = {}
                for attr_name, attr_value in attributes.items():
                    if isinstance(attr_value, str):
                        attr_value = self.get_funcs().get(attr_value, attr_value)
                    if attr_name == 'efficiency':
                        adjusted_attributes['eta_s'] = attr_value
                    elif attr_name in ['ttd_u', 'ttd_l', 'pr1', 'pr2']:  # Specific to HeatExchanger
                        adjusted_attributes[attr_name] = attr_value
                component.set_attr(**adjusted_attributes)

        # Set attributes for connections
        for connection in self.connections:
            source_component = connection.source
            component_type = type(source_component).__name__

            # Handle attributes dynamically for each connection based on the component type
            connection_attributes = {}

            if component_type == 'Source':
                if source_component.label == 'inlet':
                    connection_attributes['fluid'] = fluid
                    connection_attributes['m'] = mass_rate
                    connection_attributes['T'] = production_temperature
                    connection_attributes['p'] = production_pressure
                else:
                    component_label = source_component.label
                    source_config = self.config.get(component_label, {})

                    if 'fluid' in source_config:
                        fluid_value = source_config['fluid']
                        if isinstance(fluid_value, str):
                            fluid_value = self.get_funcs().get(fluid_value, fluid_value)
                        connection_attributes['fluid'] = fluid_value

                    if 'm' in source_config:
                        m_value = source_config['m']
                        if isinstance(m_value, str):
                            m_value = self.get_funcs().get(m_value, m_value)
                        connection_attributes['m'] = m_value

                    if 'T' in source_config:
                        T_value = source_config['T']
                        if isinstance(T_value, str):
                            T_value = self.get_funcs().get(T_value, T_value)
                        connection_attributes['T'] = T_value

                    if 'p' in source_config:
                        p_value = source_config['p']
                        if isinstance(p_value, str):
                            p_value = self.get_funcs().get(p_value, p_value)
                        connection_attributes['p'] = p_value

                    if 'vapor_mass_fraction_out' in source_config:
                        x_value = source_config['vapor_mass_fraction_out']
                        if isinstance(x_value, str):
                            x_value = self.get_funcs().get(x_value, x_value)
                        connection_attributes['x'] = x_value

            elif component_type == 'Sink':
                component_label = source_component.label
                sink_config = self.config.get(component_label, {})

                if 'T' in sink_config:
                    T_value = sink_config['T']
                    if isinstance(T_value, str):
                        T_value = self.get_funcs().get(T_value, T_value)
                    connection_attributes['T'] = T_value

                if 'p' in sink_config:
                    p_value = sink_config['p']
                    if isinstance(p_value, str):
                        p_value = self.get_funcs().get(p_value, p_value)
                    connection_attributes['p'] = p_value

            elif component_type == 'Valve':
                component_label = source_component.label
                valve_config = self.config.get(component_label, {})
                if 'p_out' in valve_config:
                    p_out_value = valve_config['p_out']
                    if isinstance(p_out_value, str):
                        p_out_value = self.get_funcs().get(p_out_value, p_out_value)
                    connection_attributes['p'] = p_out_value

                if 'T_out' in valve_config:
                    T_out_value = valve_config['T_out']
                    if isinstance(T_out_value, str):
                        T_out_value = self.get_funcs().get(T_out_value, T_out_value)
                    connection_attributes['T'] = T_out_value

            elif component_type == 'Turbine':
                component_label = source_component.label
                turbine_config = self.config.get(component_label, {})
                if 'p_out' in turbine_config:
                    p_out_value = turbine_config['p_out']
                    if isinstance(p_out_value, str):
                        p_out_value = self.get_funcs().get(p_out_value, p_out_value)
                    connection_attributes['p'] = p_out_value

                if 'T_out' in turbine_config:
                    T_out_value = turbine_config['T_out']
                    if isinstance(T_out_value, str):
                        T_out_value = self.get_funcs().get(T_out_value, T_out_value)
                    connection_attributes['T'] = T_out_value

            elif component_type == 'SimpleHeatExchanger':
                component_label = source_component.label
                if component_label in self.config:
                    heat_exchanger_config = self.config[component_label]

                    if 'p_out' in heat_exchanger_config:
                        p_out_value = heat_exchanger_config['p_out']
                        if isinstance(p_out_value, str):
                            p_out_value = self.get_funcs().get(p_out_value, p_out_value)
                        connection_attributes['p'] = p_out_value

                    if 'T_out' in heat_exchanger_config:
                        T_out_value = heat_exchanger_config['T_out']
                        if isinstance(T_out_value, str):
                            T_out_value = self.get_funcs().get(T_out_value, T_out_value)
                        connection_attributes['T'] = T_out_value

                    if 'vapor_mass_fraction_out' in heat_exchanger_config:
                        x_value = heat_exchanger_config['vapor_mass_fraction_out']
                        if isinstance(x_value, str):
                            x_value = self.get_funcs().get(x_value, x_value)
                        connection_attributes['x'] = x_value

            elif component_type == 'Compressor':
                component_label = source_component.label
                pump_config = self.config.get(component_label, {})
                if 'p_out' in pump_config:
                    p_out_value = pump_config['p_out']
                    if isinstance(p_out_value, str):
                        p_out_value = self.get_funcs().get(p_out_value, p_out_value)
                    connection_attributes['p'] = p_out_value

                if 'T_out' in pump_config:
                    T_out_value = pump_config['T_out']
                    if isinstance(T_out_value, str):
                        T_out_value = self.get_funcs().get(T_out_value, T_out_value)
                    connection_attributes['T'] = T_out_value

            elif component_type == 'DropletSeparator':
                component_label = source_component.label
                droplet_separator_config = self.config.get(component_label, {})

            elif component_type == 'Merge':
                component_label = source_component.label
                merge_config = self.config.get(component_label, {})

            elif component_type == 'CycleCloser':
                component_label = source_component.label
                CycleCloser_config = self.config.get(component_label, {})

            elif component_type == 'HeatExchanger':
                component_label = source_component.label
                heat_exchanger_config = self.config.get(component_label, {})
                source_port = connection.source_id  # Get the specific port (e.g., 'out1' or 'out2')
                port_suffix = '1' if source_port == 'out1' else '2' # Define mappings for out1 and out2 ports

                attribute_keys = [
                    f'p_out{port_suffix}', f'p0_out{port_suffix}', f'h0_out{port_suffix}',
                    f'T_out{port_suffix}', f'vapor_mass_fraction_out{port_suffix}', f'fluid_out{port_suffix}'
                ]

                mapped_keys = {
                    f'p_out{port_suffix}': 'p',
                    f'p0_out{port_suffix}': 'p0',
                    f'h0_out{port_suffix}': 'h0',
                    f'T_out{port_suffix}': 'T',
                    f'vapor_mass_fraction_out{port_suffix}': 'x',
                    f'fluid_out{port_suffix}': 'fluid'
                }

                for attr_key in attribute_keys:
                    if attr_key in heat_exchanger_config:
                        attr_value = heat_exchanger_config[attr_key]
                        if isinstance(attr_value, str):
                            attr_value = self.get_funcs().get(attr_value, attr_value)
                        connection_attributes[mapped_keys[attr_key]] = attr_value

            connection.set_attr(**connection_attributes)

        for connection in self.connections:
            if isinstance(connection.target, Sink) and connection.target.label == "outlet":
                source_component = connection.source
                connection.set_attr(
                    p=self.iterative_inj_pressure / 100_000.0,
                )
                break  # Exit loop after finding the outlet

    def _BAC_regression_model(self, coeffs: list) -> float:
        r"""
        Computes the parasitic power fraction using a BAC regression model.

        Args:
            coeffs (list): Coefficients for the regression model.

        Returns:
            float: Parasitic power fraction.

        Formula:
            .. math::
                f = \frac{a}{\Delta T_{\text{approach}}} + b \cdot T_{\text{ambient}} + c \cdot \frac{T_{\text{ambient}}}{\Delta T_{\text{approach}}} + \frac{d}{\Delta T_{\text{approach}} + \Delta T_{\text{range}}}

        Where:
            - \( a, b, c, d \): Regression coefficients.
            - \( T_{\text{ambient}} \): Ambient temperature (\(^\circ\text{C}\)).
            - \( \Delta T_{\text{approach}} \): Approach temperature difference (\(^\circ\text{C}\)).
            - \( \Delta T_{\text{range}} \): Condensation temperature range (\(^\circ\text{C}\)).
        """
        a, b, c, d = coeffs
        T_ambient = self.pp_specs.surface_temperature
        dT_approach = self.pp_specs.approach_temperature
        dT_range = self.pp_specs.temperature_range

        return a / dT_approach + b * T_ambient + c * T_ambient / dT_approach + d / (dT_approach + dT_range)

    def _get_parasitic_power_fraction_cooling(self):
        """
        Computes the parasitic power fraction for cooling.

        Returns:
            float: Cooling parasitic power fraction.
        """
        return self._BAC_regression_model(coeffs=self._coeffs_cooling_power)

    def _get_parasitic_power_fraction_condensing(self):
        """
        Computes the parasitic power fraction for condensing.

        Returns:
            float: Condensing parasitic power fraction.
        """
        return self._BAC_regression_model(coeffs=self._coeffs_condensing_power)

    def calculate_net_power(self):
        """
        Calculates the net power output of the power plant.

        This method computes the net power by summing up the power generated by
        turbines and subtracting the auxiliary power consumption, which includes
        power used by pumps, coolers, and condensers.

        Returns:
            float: The net power output of the power plant (in watts).

        Notes:
            - Turbines produce negative power in TESPy (representing power generation).
            - Compressors (pumps) consume power, contributing to auxiliary power consumption.
            - Additional power consumption from cooling and condensing units is included.
        """
        gross_power_output = 0.0
        auxiliary_power_consumption = 0.0

        for node_name, node in self.nodes.items():
            if isinstance(node, Turbine):
                gross_power_output += -node.P.val  # Turbine output power is negative in TESPy

        for node_name, node in self.nodes.items():
            if isinstance(node, Compressor):  # Pumps are modeled as compressors in TESPy
                auxiliary_power_consumption += node.P.val  # Pump input power is negative in TESPy

        w_cooler, w_condenser = self.compute_cooler_condenser_power()
        auxiliary_power_consumption += w_cooler + w_condenser
        net_power = gross_power_output - auxiliary_power_consumption

        return net_power

    def compute_cooler_condenser_power(self):
        """
        Computes the parasitic power consumption of coolers and condensers in the power plant.

        This method iterates through all cooler and condenser components within the power plant,
        calculates their respective heat loads, and determines the parasitic power consumption
        based on predefined coefficients for cooling tower modes ('WET' or 'DRY').

        Returns:
            tuple: A tuple containing:
                - float: Total cooling power consumption in watts (W).
                - float: Total condensing power consumption in watts (W).

        Notes:
            - Coolers and condensers are identified by their `Subtype` in the power plant configuration.
            - Supported cooling tower modes: 'WET' and 'DRY'.
            - The method raises a ValueError if an invalid `cooling_tower_mode` is encountered.
            - Heat loads are assumed to be given as positive values in TESPy, hence negated here.

        Prints:
            - Heat loads of each cooler and condenser.
            - Calculated cooling and condensing power consumption.

        Raises:
            ValueError: If an invalid `cooling_tower_mode` is specified in the component configuration.
        """
        w_cooler = w_condenser = 0.0
        q_cooler = q_condenser = 0.0

        for node_name, node in self.nodes.items():
            if isinstance(node, SimpleHeatExchanger):
                component_config = self.config.get(node_name, {})
                subtype = component_config.get('Subtype', '').lower()

                if subtype in ['cooler', 'condenser']:
                    tower_mode = component_config.get('cooling_tower_mode', '').upper()
                    if tower_mode not in ['WET', 'DRY']:
                        raise ValueError(f"Invalid cooling_tower_mode '{tower_mode}' in component_config for {node_name}")

                    self._surface_cooling_tower_mode = tower_mode

                    if self._surface_cooling_tower_mode == 'WET':
                        self._coeffs_cooling_power = [1.2, 0.0, -3.79e-3, 1.95e-2]
                        self._coeffs_condensing_power = [1.65, -6.24e-6, -5.03e-3, 0.0]
                    elif self._surface_cooling_tower_mode == 'DRY':
                        self._coeffs_cooling_power = [7.65e-1, 0.0, 0.0, 1.28e-1]
                        self._coeffs_condensing_power = [0.619, 0.0, 0.0, 0.0]

                    if subtype == 'cooler':
                        q_cooler = -node.Q.val
                        f_cooling = self._get_parasitic_power_fraction_cooling()
                        power = q_cooler * f_cooling
                        w_cooler += power
                        # print(f"{node.label} (Cooler) - Heat Load: {q_cooler:.2f} W, Parasitic Power: {power:.2f} W")

                    elif subtype == 'condenser':
                        q_condenser = -node.Q.val
                        f_condensing = self._get_parasitic_power_fraction_condensing()
                        power = q_condenser * f_condensing
                        w_condenser += power
                        # print(f"{node.label} (Condenser) - Heat Load: {q_condenser:.2f} W, Parasitic Power: {power:.2f} W")

        return w_cooler, w_condenser

    def generate_output_table(self, step_index: int = -1, table_type: str = "power_plant", write_csv: bool = False, print_table: bool = True):
        """
        Generates and prints a table showing system information:
        Units, Ports, Pressure, Temperature, Enthalpy, Mass Rate, and Fluid Quality (x).
        Also writes the table data to a CSV file for each time step if write_csv is True.
        Args:
            step_index (int, optional): The time step index for CSV file naming.
            table_type (str, optional): File prefix for CSV output (default: 'power_plant').
            write_csv (bool, optional): Whether to write the table to a CSV file.
            print_table (bool, optional): Whether to print the table to the console.
        """
        import csv
        from tabulate import tabulate
        from termcolor import colored
        from itertools import cycle

        graph_nodes = self.nodes
        graph_edges = [(conn.source.label, conn.target.label) for conn in self.connections]
        table_data = []
        headers = ["Unit", "Port", "Pressure (MPa)", "Temperature (°C)", "Enthalpy (kJ/kg)", "Mass Rate (kg/s)", "Vapor Mass Fraction"]
        processed_ports = set()

        for edge in graph_edges:
            source, target = edge
            source_unit = graph_nodes[source]
            target_unit = graph_nodes[target]

            for idx, outlet in enumerate(getattr(source_unit, 'outl', [])):
                port_key = (source, f"Outlet-{idx + 1}")
                if port_key not in processed_ports:
                    processed_ports.add(port_key)
                    x_attr = getattr(outlet, 'x', None)
                    x_val = x_attr.val if x_attr is not None and hasattr(x_attr, 'val') else 'N/A'
                    table_data.append([
                        source,
                        f"Outlet-{idx + 1}",
                        outlet.p.val / 10,
                        outlet.T.val,
                        outlet.h.val,
                        outlet.m.val,
                        x_val
                    ])

            for idx, inlet in enumerate(getattr(target_unit, 'inl', [])):
                port_key = (target, f"Inlet-{idx + 1}")
                if port_key not in processed_ports:
                    processed_ports.add(port_key)
                    x_attr = getattr(inlet, 'x', None)
                    x_val = x_attr.val if x_attr is not None and hasattr(x_attr, 'val') else 'N/A'
                    table_data.append([
                        target,
                        f"Inlet-{idx + 1}",
                        inlet.p.val / 10,
                        inlet.T.val,
                        inlet.h.val,
                        inlet.m.val,
                        x_val
                    ])

        # Rearrange table for better presentation
        if table_data:
            last_row = table_data.pop()
            table_data.insert(0, last_row)

        # Write to CSV file if requested
        if write_csv and step_index >= 0:
            csv_filename = f"{table_type}_{step_index}.csv"
            try:
                with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(headers)
                    writer.writerows(table_data)
                print(f"Output table written to: {csv_filename}")
            except Exception as e:
                print(f"Error writing CSV file: {e}")

        if print_table:
            available_colors = ["cyan", "green", "yellow", "red", "blue", "magenta", "white"]
            unit_names = list(graph_nodes.keys())
            color_map = {unit: color for unit, color in zip(unit_names, cycle(available_colors))}
            colored_table_data = []

            for row in table_data:
                unit_color = color_map.get(row[0], "white")
                colored_row = [colored(str(cell), unit_color, attrs=["bold"]) for cell in row]
                colored_table_data.append(colored_row)

            top_border = "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+" + "-" * 14 + "+"
            print(top_border)
            print(tabulate(colored_table_data, headers=headers, tablefmt="fancy_grid", colalign=("center", "center", "center", "center", "center", "center", "center")).replace("\u2500", " "))
            print(top_border)

    def get_outlet_conditions(self):
        """
        Retrieves the outlet pressure and temperature from the results of the network calculation.

        Returns:
            dict: Outlet conditions with keys `pressure` (in MPa) and `temperature` (in °C).
                  If the outlet node is not properly calculated, the values will be `None`.
        """
        outlet_conditions = {
            "pressure": None,
            "temperature": None
        }

        for connection in self.connections:
            if isinstance(connection.target, Sink) and connection.target.label == "outlet":
                try:
                    outlet_conditions["pressure"] = connection.p.val * BAR_TO_MPA  # Convert bar to MPa
                    outlet_conditions["temperature"] = connection.T.val  # Convert K to °C
                except AttributeError:
                    pass
                break  # Exit after finding the outlet

        return outlet_conditions
