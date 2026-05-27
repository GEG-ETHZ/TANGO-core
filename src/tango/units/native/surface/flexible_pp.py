from copy import copy
from dataclasses import dataclass
from pathlib import Path

import CoolProp as CP
import numpy as np
from tespy.components import (
    Compressor,
    CycleCloser,
    DropletSeparator,
    HeatExchanger,
    Merge,
    SimpleHeatExchanger,
    Sink,
    Source,
    Turbine,
    Valve,
)
from tespy.connections import Connection
from tespy.networks import Network

from tango.core.constants import BAR_TO_MPA, C_TO_K, K_TO_C, MPA_TO_PA, PA_TO_BAR
from tango.core.errors import (
    EXCESS_SMOLAR_TEST,
    SUBZERO_DNSTY_ERR_TEST,
    TESPyExcessSMolarError,
    TESPySubZeroError,
    ValidationError,
    Validator,
)
from tango.core.fluidstate import FluidState
from tango.function_evaluator import FunctionEvaluator
from tango.parameter_mappings import TARGET_PARAMETER_MAPPING, VARIABLE_PARAMETER_MAPPING
from tango.units.dataclasses import CommonSpecs
from tango.units.native.surface.base import SurfaceUnitNative


@dataclass
class SurfaceSpecsFlexiblePP(CommonSpecs):
    # `None` is a placeholder to prevent inheritance issues
    pipe_diameter: float | None = None
    approach_temperature: float | None = None
    epsilon: float = 55.0e-6
    temperature_range: float = 0.0

    def __post_init__(self):
        required_fields = ["pipe_diameter"]
        for s in required_fields:
            if getattr(self, s, None) is None:
                raise RuntimeError(f"Required parameter: {s} is not found.")


class SurfaceUnitFlexiblePP(SurfaceUnitNative, Validator):
    def __init__(self, unit_id: str, specs: dict):
        self.raw_specs = specs
        specs_obj = SurfaceSpecsFlexiblePP.from_dict(self._process_specs(specs))
        self._fluid_name = specs_obj.fluid_name
        SurfaceUnitNative.__init__(self, unit_id, specs)
        self.specs = specs_obj
        Validator.__init__(self, Path(__file__).resolve().parent / "validation.yaml")
        self.specs.new_config = self._filter_power_plant_graph(specs)
        self.specs.org = specs

        self._m_dot_mult = 1
        self.current_row = 0
        self.prod_pump_w_list = []
        self.init_stream_interface()
        self.validate_pressure_monotonicity(specs)
        self.power_plant = PowerPlant(self.specs)

    def validate_custom(self):
        """Add boundaries so that target extration pressure is above saturation pressure and below a
        reasonable max
        """
        # estimated temperature of fluid entering powerplant
        specs = self.raw_specs
        te_pp_in_est = (
            specs["surface"]["surface_temperature"]
            + specs["reservoir"]["reservoir_depth"] * specs["props"]["thermal_gradient"]
        )
        try:
            p_sat = CP.CoolProp.PropsSI("P", "T", te_pp_in_est, "Q", 0, self._fluid_name)
            # warn if target_extraction is below this threshold
            p_sat_warn = p_sat * 1.01
            # err if target_extraction is below this threshold
            p_sat_err = p_sat
        except ValueError as err:
            if "Temperature to QT_flash" in str(err):
                p_sat = None  # type: ignore[no-redef]
                # warn if target_extraction is below this threshold
                p_sat_warn = None
                # err if target_extraction is below this threshold
                p_sat_err = None
            else:
                raise err
        # warn if target extraction pressure exceeds 35 MPa, which is typical for a superheated coal-fired
        # plant and would be absurdly high pressure for a geothermal plant
        p_max_warn = 35e6
        # error if target extraction pressure exceeds 50 MPa, which is higher than a superheated coal-fired
        # plant and would be ludicrously high pressure for a geothermal plant
        p_max_err = 50e6
        # target extraction pressure if not provided via config file
        if "target_extraction_pressure_warn" not in self.val_dict:
            self.val_dict["target_extraction_pressure_warn"] = [p_sat_warn, p_max_warn]
        # target extraction pressure if not provided via config file
        if "target_extraction_pressure_err" not in self.val_dict:
            self.val_dict["target_extraction_pressure_err"] = [p_sat_err, p_max_err]

        self.validate_pressure_monotonicity(specs)

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

    def validate_pressure_monotonicity(self, specs: dict) -> None:
        """Validate p_out values for physical consistency.

        Performs transitive checking: for each component with p_out, traces
        upstream through the graph and verifies p_out decreases along flow
        direction (stopping at pump/compressor boundaries).

        Raises:
            ValidationError: If pressure configuration is physically invalid.

        """
        pp_graph = specs.get("power_plant_graph", {})
        edges = pp_graph.get("edges", {})
        nodes = pp_graph.get("nodes", {})

        # Collect p_out values (bar) from component configs
        p_out_values: dict[str, float] = {}
        for comp_name in nodes.keys():
            comp_config = specs.get(comp_name, {})
            if isinstance(comp_config, dict) and "p_out" in comp_config:
                p_out_values[comp_name] = comp_config["p_out"]

        # Components that increase pressure by design
        pressure_increasing_types = {"Pump", "Compressor"}

        # Build reverse adjacency: target -> list of sources (upstream)
        upstream_map: dict[str, list[str]] = {}
        for edge_data in edges.values():
            src, tgt = edge_data.get("source"), edge_data.get("target")
            if tgt not in upstream_map:
                upstream_map[tgt] = []
            upstream_map[tgt].append(src)

        def find_upstream_p_out(node: str, visited: set[str]) -> list[tuple[str, float]]:
            """Find all upstream components with p_out, stopping at pumps/compressors."""
            if node in visited:
                return []
            visited.add(node)

            results: list[tuple[str, float]] = []
            for upstream in upstream_map.get(node, []):
                upstream_type = nodes.get(upstream, {}).get("type", "")
                # Stop at pressure-increasing components (they reset pressure context)
                if upstream_type in pressure_increasing_types:
                    continue
                # If upstream has p_out, record it
                if upstream in p_out_values:
                    results.append((upstream, p_out_values[upstream]))
                # Continue tracing further upstream
                results.extend(find_upstream_p_out(upstream, visited))
            return results

        errors: list[str] = []

        # For each component with p_out, check against all upstream p_out values
        for comp_name, comp_p_out in p_out_values.items():
            comp_type = nodes.get(comp_name, {}).get("type", "")
            # Skip if this component increases pressure
            if comp_type in pressure_increasing_types:
                continue
            upstream_pressures = find_upstream_p_out(comp_name, set())
            for upstream_name, upstream_p_out in upstream_pressures:
                if comp_p_out > upstream_p_out:
                    errors.append(
                        f"{comp_name}.p_out ({comp_p_out} bar) > {upstream_name}.p_out ({upstream_p_out} bar)",
                    )

        if errors:
            raise ValidationError("Invalid power plant pressure configuration:\n\t" + "\n\t".join(errors))

    def init_stream_interface(self, P: float = None, T: float = None) -> None:
        """Initializes the fluid states for the CO2 thermosiphon system:
        production_well - turbine - condenser - pump - injection_well.
        """
        if P is not None and T is not None:
            self.inlet_fluid = FluidState.withPT(self._fluid_name, P, T)

        self.mass_rate = (
            self.specs.mass_flow_rate
            * self.specs.well_pattern_dimens[0]
            * self.specs.well_pattern_dimens[1]
            / self.specs.num_pp
        )
        self.outlet_fluid = FluidState.withPT(self.specs.fluid_name, 10000000.0, 290.0)

    def process_stream(self) -> tuple[float, float, float]:
        """Processes the stream by [float, float, float]updating turbine, condenser, and pump states,
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
            production_temperature=self.inlet_fluid.T + K_TO_C,
        )
        try:
            self.power_plant.network.solve("design")
        except ValueError as err:
            import logging
            import traceback

            # Log detailed diagnostics at WARNING level
            tb_str = traceback.format_exc()
            diagnostics = self.power_plant.get_surface_diagnostics(tb_str)
            logging.warning(f"Surface power plant solve failed. Diagnostics:{diagnostics}")

            # Calculate saturation pressure at inlet temperature for analysis
            err_str = str(err)
            saturation_analysis = self._get_saturation_pressure_analysis()

            if SUBZERO_DNSTY_ERR_TEST.search(err_str) is not None:
                raise TESPySubZeroError(
                    f"TESPy network.solve('design') failed in SurfaceUnitFlexiblePP.process_stream()"
                    f"\n\tInlet state: P={self.inlet_fluid.P:.2e} Pa, T={self.inlet_fluid.T:.2f} K"
                    f"\n\t{err}"
                    f"{saturation_analysis}",
                ) from err

            if EXCESS_SMOLAR_TEST.search(str(err)):
                raise TESPyExcessSMolarError(
                    f"TESPy network.solve('design') failed in SurfaceUnitFlexiblePP.process_stream()"
                    f"\n\tInlet state: P={self.inlet_fluid.P:.2e} Pa, T={self.inlet_fluid.T:.2f} K"
                    f"\n\t{err}"
                    f"{saturation_analysis}",
                ) from err

            # Re-raise with diagnostics for other ValueErrors
            raise ValueError(
                f"TESPy network.solve('design') failed\n\t{err}{saturation_analysis}\n\tunit: surface",
            ) from err
        outlet_state = self.power_plant.get_outlet_conditions()
        self.w_net = self.power_plant.calculate_net_power()

        ps_out = (
            outlet_state["pressure"] * MPA_TO_PA,
            outlet_state["temperature"] + C_TO_K,
            self.mass_rate,
        )

        return ps_out

    def _get_saturation_pressure_analysis(self) -> str:
        """Analyze if any power plant components have outlet pressures below saturation.

        Calculates the saturation pressure at the inlet temperature and checks
        against configured outlet pressures in the power plant. Components with
        p_out < P_sat cannot physically work (would require flashing at sub-saturation).

        Returns:
            Formatted string with saturation analysis for error messages.

        """
        lines = []

        # Get saturation pressure at inlet temperature
        T_inlet_K = self.inlet_fluid.T
        T_inlet_C = T_inlet_K + K_TO_C
        fluid_name = self.specs.fluid_name

        try:
            # CoolProp saturation pressure lookup
            P_sat_Pa = CP.CoolProp.PropsSI("P", "T", T_inlet_K, "Q", 0, fluid_name)
            P_sat_bar = P_sat_Pa * PA_TO_BAR
        except Exception as e:
            lines.append(f"\n\tCould not calculate saturation pressure: {e}")
            return "".join(lines)

        lines.append("\n\t=== Saturation Pressure Analysis ===")
        lines.append(f"\n\tInlet T: {T_inlet_C:.1f} °C ({T_inlet_K:.1f} K)")
        lines.append(f"\n\tP_sat at inlet T: {P_sat_bar:.2f} bar ({P_sat_Pa:.2e} Pa)")

        # Check valve configurations - valve p_out must be <= P_sat to flash
        can_flash = []
        cannot_flash = []
        config = self.power_plant.config

        for comp_name, comp_config in config.items():
            if not isinstance(comp_config, dict):
                continue

            # Only check valves and turbines (expansion devices)
            if not (comp_name.lower().startswith("valve") or comp_name.lower().startswith("turbine")):
                continue

            p_out_value = comp_config.get("p_out")

            if p_out_value is not None:
                # Resolve function references if needed
                if isinstance(p_out_value, str):
                    p_out_value = self.power_plant.get_funcs().get(p_out_value, None)

                if p_out_value is not None and isinstance(p_out_value, (int, float)):
                    # Valve p_out must be <= P_sat to flash liquid to vapor
                    if p_out_value <= P_sat_bar:
                        can_flash.append((comp_name, p_out_value))
                    else:
                        cannot_flash.append((comp_name, p_out_value))

        lines.append("\n\tExpansion device outlet pressures (must be <= P_sat to flash):")
        if can_flash:
            for comp_name, p_val in can_flash:
                lines.append(f"\n\t  ✓ {comp_name}: p_out={p_val:.2f} bar")
        if cannot_flash:
            for comp_name, p_val in cannot_flash:
                lines.append(f"\n\t  ⚠ {comp_name}: p_out={p_val:.2f} bar (> P_sat, cannot flash)")
            lines.append(
                "\nTry increasing parameters that increase surface pipe inlet temperature (and correspondingly "
                + "decrease saturation pressure), e.g.:"
                + "\n- `schedule`: `well_spacing` (higher value increases reservoir residence time -> "
                "production temperature)"
                + "\n- `reservoir`: `thickness` (higher value increases reservoir residence time -> "
                + "production temperature)"
                + "\n- `reservoir`: `reservoir_depth` (higher value increases reservoir temperature -> "
                + "production temperature)"
                + "\n- `props`: `thermal_gradient` (higher values increase reservoir temperature -> "
                + "production temperature)"
                "",
            )
        if not can_flash and not cannot_flash:
            lines.append("\n\t  (no valves have configured outlet pressures)")

        # Check condensers: compare inlet vapor fraction vs configured outlet
        condenser_issues = []
        nodes = self.power_plant.config.get("power_plant_graph", {}).get("nodes", {})

        for conn in self.power_plant.connections:
            target_name = conn.target.label
            node_data = nodes.get(target_name, {})

            # Check if target is a condenser (SimpleHeatExchanger with Subtype=condenser)
            if node_data.get("type") != "SimpleHeatExchanger":
                continue

            comp_config = config.get(target_name, {})
            if comp_config.get("Subtype", "").lower() != "condenser":
                continue

            x_out_specified = comp_config.get("vapor_mass_fraction_out")
            if x_out_specified is None:
                continue

            # Get inlet vapor fraction from TESPy connection (may not be available if solve failed)
            try:
                x_inlet = conn.x.val
                has_inlet_data = x_inlet is not None and x_inlet >= 0
            except AttributeError:
                x_inlet = None
                has_inlet_data = False

            # Check if outlet is problematically high
            # If we have inlet data: warn if outlet >= inlet - tolerance
            # If no inlet data: warn if outlet > 0.5 (heuristic for "high")
            tolerance = 0.01
            if has_inlet_data:
                if x_out_specified >= x_inlet - tolerance:
                    condenser_issues.append((target_name, x_inlet, x_out_specified))
            elif x_out_specified > 0.5:
                # No inlet data, but high outlet is suspicious
                condenser_issues.append((target_name, None, x_out_specified))

        if condenser_issues:
            lines.append("\n\t=== Condenser Configuration Warning ===")
            for comp_name, x_in, x_out in condenser_issues:
                if x_in is not None:
                    lines.append(
                        f"\n\t  ⚠ {comp_name}: inlet x={x_in:.2f}, "
                        f"vapor_mass_fraction_out={x_out:.2f} (minimal/no condensation)",
                    )
                else:
                    lines.append(
                        f"\n\t  ⚠ {comp_name}: vapor_mass_fraction_out={x_out:.2f} "
                        "(unusually high, may prevent condensation)",
                    )
            lines.append(
                "\n\tHigh vapor_mass_fraction_out means minimal/no condensation. "
                "Reduce vapor_mass_fraction_out (e.g., 0 for full condensation).",
            )

        return "".join(lines)

    def get_dp_simple(self, te: float, p: float, mdot: float) -> float:
        r"""Return approximate flow pressure delta [Pa], accounting for gravitational
        effects

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
        u = mdot_pipe / (0.25 * np.pi * self.specs.pipe_diameter**2) / rho
        ff = self._compute_friction_factor(rho, mu, u)
        dP_pipe: float = self._get_pipe_pressure_drop(rho, u, ff)
        return dP_pipe

    def get_flow_res_per_dx(self, te: float, p: float, mdot: float) -> float:
        r"""Return approximate pressure delta [Pa] per unit length, accounting only for dissipative losses,

        # Arguments
        - `te`: estimated temperature [K] for property evaluations
        - `p`: estimated pressure [Pa] for property evaluations
        - `mdot`: mass flow rate [kg/s]
        """
        dP_pipe = self.get_dp_simple(te, p, mdot)
        dp_per_dx: float = dP_pipe / self.specs.__dict__["well_spacing"]

        return dp_per_dx

    def _update_state_pipe(self) -> None:
        r"""Updates the state of the fluid in the surface pipe, accounting for pressure drops.

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
        u = mdot / (0.25 * np.pi * self.specs.pipe_diameter**2) / rho
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
        r"""Computes the friction factor using the Haaland equation (1983).

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
        r"""Computes the pressure drop across the pipe.

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
        dP_pipe: float = 0.5 * ff * L * rho * u**2 / d
        return dP_pipe

    def _process_specs(self, specs) -> dict:
        """Combines common and surface-specific specifications.

        Args:
            specs (dict): Input specifications with keys `common` and `surface`.

        Returns:
            dict: Merged dictionary of specifications.

        """
        return specs["common"] | specs["surface"]


class PowerPlant:
    """A class representing a power plant model built using TESPy components and connections.

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
            economic=None,
        )

        self._specs = specs
        self._functions_evaluated = False

        self.funcs = {}
        self.iterative_inj_pressure = 9100000
        self.pp_specs = specs
        self.config = self.pp_specs.new_config

        self.nodes = {}
        for node_name, node_data in self.config["power_plant_graph"]["nodes"].items():
            self.nodes[node_name] = self._create_component(node_data["type"], node_name)

        self.connections = []
        for edge_data in self.config["power_plant_graph"]["edges"].values():
            source = self.nodes[edge_data["source"]]
            target = self.nodes[edge_data["target"]]
            source_port = edge_data.get("source_port", "out1")
            target_port = edge_data.get("target_port", "in1")
            connection = Connection(source, source_port, target, target_port)
            self.connections.append(connection)

        self.network = Network(p_unit="bar", T_unit="C", h_unit="kJ / kg", iterinfo=False)
        self.network.add_conns(*self.connections)

    def set_context(self, context):
        """Sets the context for the function evaluator and evaluates functions if not already done.

        Args:
            context (object): The context object (e.g., NativeWorkflow instance).

        """
        self.function_evaluator.set_context(context)

        if not self._functions_evaluated and "functions" in self._specs.org and self._specs.org["functions"]:
            self.function_evaluator.evaluate_functions(self._specs.org["functions"])
            self._functions_evaluated = True
            self.funcs = self.function_evaluator.evaluated_functions

    def get_funcs(self):
        """Gets the evaluated functions, with fallback to main workflow if needed.

        Returns:
            dict: Dictionary of evaluated functions.

        """
        if not self.funcs and hasattr(self, "context") and self.context:
            if hasattr(self.context, "function_evaluator"):
                return self.context.function_evaluator.evaluated_functions
        return self.funcs

    def _create_component(self, component_type, name):
        """Creates and returns a TESPy component based on the specified type.

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
            "Sink": Sink,
            "Source": Source,
            "Turbine": Turbine,
            "SimpleHeatExchanger": SimpleHeatExchanger,
            "Compressor": Compressor,
            "Valve": Valve,
            "DropletSeparator": DropletSeparator,
            "Merge": Merge,
            "HeatExchanger": HeatExchanger,
            "CycleCloser": CycleCloser,
        }
        return component_mapping[component_type](name)

    def set_attributes(self, fluid, mass_rate, production_pressure, production_temperature):
        """Sets the attributes of the power plant components and connections.

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
                    if attr_name == "efficiency":
                        adjusted_attributes["eta_s"] = attr_value
                    elif attr_name in ["ttd_u", "ttd_l", "pr1", "pr2"]:  # Specific to HeatExchanger
                        adjusted_attributes[attr_name] = attr_value
                component.set_attr(**adjusted_attributes)

        # Set attributes for connections
        for connection in self.connections:
            source_component = connection.source
            component_type = type(source_component).__name__

            # Handle attributes dynamically for each connection based on the component type
            connection_attributes = {}

            if component_type == "Source":
                if source_component.label == "inlet":
                    connection_attributes["fluid"] = fluid
                    connection_attributes["m"] = mass_rate
                    connection_attributes["T"] = production_temperature
                    connection_attributes["p"] = production_pressure
                else:
                    component_label = source_component.label
                    source_config = self.config.get(component_label, {})

                    if "fluid" in source_config:
                        fluid_value = source_config["fluid"]
                        if isinstance(fluid_value, str):
                            fluid_value = self.get_funcs().get(fluid_value, fluid_value)
                        connection_attributes["fluid"] = fluid_value

                    if "m" in source_config:
                        m_value = source_config["m"]
                        if isinstance(m_value, str):
                            m_value = self.get_funcs().get(m_value, m_value)
                        connection_attributes["m"] = m_value

                    if "T" in source_config:
                        T_value = source_config["T"]
                        if isinstance(T_value, str):
                            T_value = self.get_funcs().get(T_value, T_value)
                        connection_attributes["T"] = T_value

                    if "p" in source_config:
                        p_value = source_config["p"]
                        if isinstance(p_value, str):
                            p_value = self.get_funcs().get(p_value, p_value)
                        connection_attributes["p"] = p_value

                    if "vapor_mass_fraction_out" in source_config:
                        x_value = source_config["vapor_mass_fraction_out"]
                        if isinstance(x_value, str):
                            x_value = self.get_funcs().get(x_value, x_value)
                        connection_attributes["x"] = x_value

            elif component_type == "Sink":
                component_label = source_component.label
                sink_config = self.config.get(component_label, {})

                if "T" in sink_config:
                    T_value = sink_config["T"]
                    if isinstance(T_value, str):
                        T_value = self.get_funcs().get(T_value, T_value)
                    connection_attributes["T"] = T_value

                if "p" in sink_config:
                    p_value = sink_config["p"]
                    if isinstance(p_value, str):
                        p_value = self.get_funcs().get(p_value, p_value)
                    connection_attributes["p"] = p_value

            elif component_type == "Valve":
                component_label = source_component.label
                valve_config = self.config.get(component_label, {})
                if "p_out" in valve_config:
                    p_out_value = valve_config["p_out"]
                    if isinstance(p_out_value, str):
                        p_out_value = self.get_funcs().get(p_out_value, p_out_value)
                    connection_attributes["p"] = p_out_value

                if "T_out" in valve_config:
                    T_out_value = valve_config["T_out"]
                    if isinstance(T_out_value, str):
                        T_out_value = self.get_funcs().get(T_out_value, T_out_value)
                    connection_attributes["T"] = T_out_value

            elif component_type == "Turbine":
                component_label = source_component.label
                turbine_config = self.config.get(component_label, {})
                if "p_out" in turbine_config:
                    p_out_value = turbine_config["p_out"]
                    if isinstance(p_out_value, str):
                        p_out_value = self.get_funcs().get(p_out_value, p_out_value)
                    connection_attributes["p"] = p_out_value

                if "T_out" in turbine_config:
                    T_out_value = turbine_config["T_out"]
                    if isinstance(T_out_value, str):
                        T_out_value = self.get_funcs().get(T_out_value, T_out_value)
                    connection_attributes["T"] = T_out_value

            elif component_type == "SimpleHeatExchanger":
                component_label = source_component.label
                if component_label in self.config:
                    heat_exchanger_config = self.config[component_label]

                    if "p_out" in heat_exchanger_config:
                        p_out_value = heat_exchanger_config["p_out"]
                        if isinstance(p_out_value, str):
                            p_out_value = self.get_funcs().get(p_out_value, p_out_value)
                        connection_attributes["p"] = p_out_value

                    if "T_out" in heat_exchanger_config:
                        T_out_value = heat_exchanger_config["T_out"]
                        if isinstance(T_out_value, str):
                            T_out_value = self.get_funcs().get(T_out_value, T_out_value)
                        connection_attributes["T"] = T_out_value

                    if "vapor_mass_fraction_out" in heat_exchanger_config:
                        x_value = heat_exchanger_config["vapor_mass_fraction_out"]
                        if isinstance(x_value, str):
                            x_value = self.get_funcs().get(x_value, x_value)
                        connection_attributes["x"] = x_value

            elif component_type == "Compressor":
                component_label = source_component.label
                pump_config = self.config.get(component_label, {})
                if "p_out" in pump_config:
                    p_out_value = pump_config["p_out"]
                    if isinstance(p_out_value, str):
                        p_out_value = self.get_funcs().get(p_out_value, p_out_value)
                    connection_attributes["p"] = p_out_value

                if "T_out" in pump_config:
                    T_out_value = pump_config["T_out"]
                    if isinstance(T_out_value, str):
                        T_out_value = self.get_funcs().get(T_out_value, T_out_value)
                    connection_attributes["T"] = T_out_value

            elif (
                component_type == "DropletSeparator"
                or component_type == "Merge"
                or component_type == "CycleCloser"
            ):
                component_label = source_component.label
                self.config.get(component_label, {})

            elif component_type == "HeatExchanger":
                component_label = source_component.label
                heat_exchanger_config = self.config.get(component_label, {})
                source_port = connection.source_id  # Get the specific port (e.g., 'out1' or 'out2')
                port_suffix = "1" if source_port == "out1" else "2"  # Define mappings for out1 and out2 ports

                attribute_keys = [
                    f"p_out{port_suffix}",
                    f"p0_out{port_suffix}",
                    f"h0_out{port_suffix}",
                    f"T_out{port_suffix}",
                    f"vapor_mass_fraction_out{port_suffix}",
                    f"fluid_out{port_suffix}",
                ]

                mapped_keys = {
                    f"p_out{port_suffix}": "p",
                    f"p0_out{port_suffix}": "p0",
                    f"h0_out{port_suffix}": "h0",
                    f"T_out{port_suffix}": "T",
                    f"vapor_mass_fraction_out{port_suffix}": "x",
                    f"fluid_out{port_suffix}": "fluid",
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
        r"""Computes the parasitic power fraction using a BAC regression model.

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
        """Computes the parasitic power fraction for cooling.

        Returns:
            float: Cooling parasitic power fraction.

        """
        return self._BAC_regression_model(coeffs=self._coeffs_cooling_power)

    def _get_parasitic_power_fraction_condensing(self):
        """Computes the parasitic power fraction for condensing.

        Returns:
            float: Condensing parasitic power fraction.

        """
        return self._BAC_regression_model(coeffs=self._coeffs_condensing_power)

    def calculate_net_power(self):
        """Calculates the net power output of the power plant.

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

        for node in self.nodes.values():
            if isinstance(node, Turbine):
                gross_power_output += -node.P.val  # Turbine output power is negative in TESPy

        for node in self.nodes.values():
            if isinstance(node, Compressor):  # Pumps are modeled as compressors in TESPy
                auxiliary_power_consumption += node.P.val  # Pump input power is negative in TESPy

        w_cooler, w_condenser = self.compute_cooler_condenser_power()
        auxiliary_power_consumption += w_cooler + w_condenser
        net_power = gross_power_output - auxiliary_power_consumption

        return net_power

    def compute_cooler_condenser_power(self):
        """Computes the parasitic power consumption of coolers and condensers in the power plant.

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
                subtype = component_config.get("Subtype", "").lower()

                if subtype in ["cooler", "condenser"]:
                    tower_mode = component_config.get("cooling_tower_mode", "").upper()
                    if tower_mode not in ["WET", "DRY"]:
                        raise ValueError(
                            f"Invalid cooling_tower_mode '{tower_mode}' in component_config for {node_name}",
                        )

                    self._surface_cooling_tower_mode = tower_mode

                    if self._surface_cooling_tower_mode == "WET":
                        self._coeffs_cooling_power = [1.2, 0.0, -3.79e-3, 1.95e-2]
                        self._coeffs_condensing_power = [1.65, -6.24e-6, -5.03e-3, 0.0]
                    elif self._surface_cooling_tower_mode == "DRY":
                        self._coeffs_cooling_power = [7.65e-1, 0.0, 0.0, 1.28e-1]
                        self._coeffs_condensing_power = [0.619, 0.0, 0.0, 0.0]

                    if subtype == "cooler":
                        q_cooler = -node.Q.val
                        f_cooling = self._get_parasitic_power_fraction_cooling()
                        power = q_cooler * f_cooling
                        w_cooler += power
                        # print(f"{node.label} (Cooler) - Heat Load: {q_cooler:.2f} W, Parasitic Power: {power:.2f} W")

                    elif subtype == "condenser":
                        q_condenser = -node.Q.val
                        f_condensing = self._get_parasitic_power_fraction_condensing()
                        power = q_condenser * f_condensing
                        w_condenser += power
                        # print(f"{node.label} (Condenser) - Heat Load: {q_condenser:.2f} W, Parasitic Power: {power:.2f} W")

        return w_cooler, w_condenser

    def generate_output_table(
        self,
        step_index: int = -1,
        table_type: str = "power_plant",
        write_csv: bool = False,
        print_table: bool = True,
    ):
        """Generates and prints a table showing system information:
        Units, Ports, Pressure, Temperature, Enthalpy, Mass Rate, and Fluid Quality (x).
        Also writes the table data to a CSV file for each time step if write_csv is True.

        Args:
            step_index (int, optional): The time step index for CSV file naming.
            table_type (str, optional): File prefix for CSV output (default: 'power_plant').
            write_csv (bool, optional): Whether to write the table to a CSV file.
            print_table (bool, optional): Whether to print the table to the console.

        """
        import csv
        from itertools import cycle

        from tabulate import tabulate
        from termcolor import colored

        graph_nodes = self.nodes
        graph_edges = [(conn.source.label, conn.target.label) for conn in self.connections]
        table_data = []
        headers = [
            "Unit",
            "Port",
            "Pressure (MPa)",
            "Temperature (°C)",
            "Enthalpy (kJ/kg)",
            "Mass Rate (kg/s)",
            "Vapor Mass Fraction",
        ]
        processed_ports = set()

        for edge in graph_edges:
            source, target = edge
            source_unit = graph_nodes[source]
            target_unit = graph_nodes[target]

            for idx, outlet in enumerate(getattr(source_unit, "outl", [])):
                port_key = (source, f"Outlet-{idx + 1}")
                if port_key not in processed_ports:
                    processed_ports.add(port_key)
                    x_attr = getattr(outlet, "x", None)
                    x_val = x_attr.val if x_attr is not None and hasattr(x_attr, "val") else "N/A"
                    table_data.append(
                        [
                            source,
                            f"Outlet-{idx + 1}",
                            outlet.p.val / 10,
                            outlet.T.val,
                            outlet.h.val,
                            outlet.m.val,
                            x_val,
                        ],
                    )

            for idx, inlet in enumerate(getattr(target_unit, "inl", [])):
                port_key = (target, f"Inlet-{idx + 1}")
                if port_key not in processed_ports:
                    processed_ports.add(port_key)
                    x_attr = getattr(inlet, "x", None)
                    x_val = x_attr.val if x_attr is not None and hasattr(x_attr, "val") else "N/A"
                    table_data.append(
                        [
                            target,
                            f"Inlet-{idx + 1}",
                            inlet.p.val / 10,
                            inlet.T.val,
                            inlet.h.val,
                            inlet.m.val,
                            x_val,
                        ],
                    )

        # Rearrange table for better presentation
        if table_data:
            last_row = table_data.pop()
            table_data.insert(0, last_row)

        # Write to CSV file if requested
        if write_csv and step_index >= 0:
            csv_filename = f"{table_type}_{step_index}.csv"
            try:
                with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(headers)
                    writer.writerows(table_data)
                print(f"Output table written to: {csv_filename}")
            except Exception as e:
                print(f"Error writing CSV file: {e}")

        if print_table:
            available_colors = ["cyan", "green", "yellow", "red", "blue", "magenta", "white"]
            unit_names = list(graph_nodes.keys())
            color_map = dict(zip(unit_names, cycle(available_colors)))
            colored_table_data = []

            for row in table_data:
                unit_color = color_map.get(row[0], "white")
                colored_row = [colored(str(cell), unit_color, attrs=["bold"]) for cell in row]
                colored_table_data.append(colored_row)

            top_border = (
                "+"
                + "-" * 14
                + "+"
                + "-" * 14
                + "+"
                + "-" * 14
                + "+"
                + "-" * 14
                + "+"
                + "-" * 14
                + "+"
                + "-" * 14
                + "+"
                + "-" * 14
                + "+"
            )
            print(top_border)
            print(
                tabulate(
                    colored_table_data,
                    headers=headers,
                    tablefmt="fancy_grid",
                    colalign=("center", "center", "center", "center", "center", "center", "center"),
                ).replace("\u2500", " "),
            )
            print(top_border)

    def get_outlet_conditions(self):
        """Retrieves the outlet pressure and temperature from the results of the network calculation.

        Returns:
            dict: Outlet conditions with keys `pressure` (in MPa) and `temperature` (in °C).
                  If the outlet node is not properly calculated, the values will be `None`.

        """
        outlet_conditions = {"pressure": None, "temperature": None}

        for connection in self.connections:
            if isinstance(connection.target, Sink) and connection.target.label == "outlet":
                try:
                    outlet_conditions["pressure"] = connection.p.val * BAR_TO_MPA  # Convert bar to MPa
                    outlet_conditions["temperature"] = connection.T.val  # Convert K to °C
                except AttributeError:
                    pass
                break  # Exit after finding the outlet

        return outlet_conditions

    def get_surface_diagnostics(self, error_msg: str) -> str:
        """Extract diagnostic info for the surface power plant during TESPy solve failure.

        Shows:
        - Graph structure of the power plant network
        - Each component's inlet and outlet pressure and temperature
        - Identification of failed component from error message

        Args:
            error_msg: The error message string from TESPy

        Returns:
            Formatted diagnostic string for error reporting

        """
        import math

        lines = []

        # --- Section 1: Graph structure ---
        lines.append("\n\t=== Power Plant Graph ===")
        # Build adjacency from connections
        edges = []
        for conn in self.connections:
            src = conn.source.label
            tgt = conn.target.label
            edges.append((src, tgt))

        # Text-based graph: list edges grouped by source
        from collections import defaultdict

        adj = defaultdict(list)
        for src, tgt in edges:
            adj[src].append(tgt)

        # Find starting nodes (sources with no incoming edges)
        all_targets = {tgt for _, tgt in edges}
        all_sources = {src for src, _ in edges}
        start_nodes = all_sources - all_targets

        # Build ASCII graph representation
        lines.append("\n\t[Flow Structure]")
        visited = set()

        def format_node_flow(node: str, depth: int = 0) -> None:
            """Recursively format node and its downstream connections."""
            if node in visited:
                return
            visited.add(node)
            indent = "\t" + "  " * depth
            downstream = adj.get(node, [])
            if downstream:
                for i, tgt in enumerate(downstream):
                    connector = "├─>" if i < len(downstream) - 1 else "└─>"
                    lines.append(f"\n{indent}{node} {connector} {tgt}")
                    format_node_flow(tgt, depth + 1)
            elif node not in adj:
                lines.append(f"\n{indent}{node} (terminal)")

        for start in sorted(start_nodes):
            format_node_flow(start)

        # --- Section 2: Component states ---
        lines.append("\n\n\t=== Component States (P, T) ===")

        def get_pt_str(port) -> str:
            """Extract P and T from a port, return formatted string."""
            try:
                p_val = port.p.val if hasattr(port.p, "val") else port.p
                t_val = port.T.val if hasattr(port.T, "val") else port.T
                p_str = f"{p_val:.2f}" if not math.isnan(p_val) else "nan"
                t_str = f"{t_val:.1f}" if not math.isnan(t_val) else "nan"
                return f"P={p_str} bar, T={t_str} °C"
            except Exception:
                return "P=?, T=?"

        for comp_name, comp in self.nodes.items():
            comp_type = type(comp).__name__
            lines.append(f"\n\t{comp_name} ({comp_type}):")

            # Inlets
            inlets = getattr(comp, "inl", [])
            for idx, inlet in enumerate(inlets):
                lines.append(f"\n\t  in{idx + 1}:  {get_pt_str(inlet)}")

            # Outlets
            outlets = getattr(comp, "outl", [])
            for idx, outlet in enumerate(outlets):
                lines.append(f"\n\t  out{idx + 1}: {get_pt_str(outlet)}")

        # --- Section 3: Failed component identification ---
        lines.append("\n\n\t=== Failure Analysis ===")
        failed_comp_name = None
        for comp_name, comp in self.nodes.items():
            if comp_name in error_msg or (hasattr(comp, "label") and comp.label in error_msg):
                failed_comp_name = comp_name
                break

        if failed_comp_name is None:
            # Try component type matching
            comp_type_map = {
                "compressor": ["pump1", "pump2"],
                "turbine": ["turbine1", "turbine2"],
                "valve": ["valve1", "valve2"],
            }
            for comp_type, candidates in comp_type_map.items():
                if comp_type.lower() in error_msg.lower():
                    for cand in candidates:
                        if cand in self.nodes:
                            failed_comp_name = cand
                            break
                    break

        if failed_comp_name:
            lines.append(f"\n\tFailed component: {failed_comp_name}")
            # Show upstream/downstream
            upstream = [src for src, tgt in edges if tgt == failed_comp_name]
            downstream = [tgt for src, tgt in edges if src == failed_comp_name]
            if upstream:
                lines.append(f"\n\tUpstream: {', '.join(upstream)}")
            if downstream:
                lines.append(f"\n\tDownstream: {', '.join(downstream)}")
        else:
            lines.append("\n\tFailed component: Could not identify from error message")

        return "".join(lines)
