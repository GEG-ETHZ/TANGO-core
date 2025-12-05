import logging
import numpy as np
import csv
import os
from pathlib import Path

from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from tango.core.errors import CoolPropError, Validator
from tango.core.abstracts.unit import Unit, FluidState, SimplePressureDrop
from tango.units.dataclasses import WellSpecsNative


class WellUnitNative(Unit, SimplePressureDrop, Validator):
    """
    Represents a native well unit based on Adams et al. (2015) for simulating fluid flow in wellbores.

    This class provides methods to process fluid flow through wellbores, accounting for various factors
    such as pressure, temperature, and fluid properties. It is designed to handle dynamic changes in wellbore
    conditions and can read flow rate data from external CSV files.

    Attributes:
        _T_r (ndarray): Temperature distribution of the rock (in Kelvin).
        _P (ndarray): Array of pressure values (in Pascals).
        _h (ndarray): Array of specific enthalpy values (in J/kg).
        _rho (ndarray): Array of fluid density values (in kg/m³).
        _mu (ndarray): Array of fluid dynamic viscosity values (in Pa·s).
        _T_f (ndarray): Array of fluid temperature values (in Kelvin).
        _u (ndarray): Array of flow velocity values (in meters per second).
    """

    def __init__(self, unit_id: str, specs: dict):
        """
        Initializes a new instance of the WellUnitNative class.

        Args:
            id (str): A unique identifier for the well unit.
            specs (dict): Specifications of the well, which will be parsed into WellSpecsNative.

        Raises:
            FileNotFoundError: If the CSV file specified in `specs` does not exist.
        """
        super().__init__(unit_id, specs)
        Validator.__init__(self, Path(__file__).parent / "validation.yaml")
        self._specs = WellSpecsNative.from_dict(specs)
        self._specs_post_processor()
        self._initialize_attributes()
        self.current_row = 0

        if self._specs.flow_rate_from_csv == "yes":
            self.csv_data = self._read_csv_file()

    # ----------------------------------------- Public Functions ----------------------------------------- #

    def get_dp_simple(self, te: float, p: float, mdot: float) -> float:
        r"""Return approximate flow pressure delta [Pa], including gravity effects, accounting
        for gravitational effects

        This approximates the flow resistance based on fluid properties evaluated at the well inlet.

        # Arguments
        - `te`: estimated temperature [K] for property evaluations
        - `p`: estimated pressure [Pa] for property evaluations
        - `mdot`: mass flow rate [kg/s]
        """
        state = FluidState.withPT(self._specs.fluid_name, p, te)
        rho = state.rho
        mu = state.mu

        u = mdot / self._cross_sectional_area / rho
        ff = self._compute_friction_factor(rho, mu, u)
        dp_loss_for_cell = self._compute_delta_P_loss(ff, rho, u)
        dp_grav_for_cell = self._f_dir * rho * self._g * self._dz
        dp_tot_for_cell = dp_loss_for_cell + dp_grav_for_cell
        # positive indicates pressure drop in direction of flow
        dp_tot_for_well: float = dp_tot_for_cell * self._num_cells

        return dp_tot_for_well

    def get_flow_res_per_dx(self, te: float, p: float, mdot: float) -> float:
        r"""Return approximate pressure delta [Pa] per unit length, accounting only for dissipative losses,

        # Arguments
        - `te`: estimated temperature [K] for property evaluations
        - `p`: estimated pressure [Pa] for property evaluations
        - `mdot`: mass flow rate [kg/s]
        """
        state = FluidState.withPT(self._specs.fluid_name, p, te)
        rho = state.rho
        mu = state.mu

        u = mdot / self._cross_sectional_area / rho
        ff = self._compute_friction_factor(rho, mu, u)
        dp_loss_for_cell = self._compute_delta_P_loss(ff, rho, u)

        dp_per_dx: float = dp_loss_for_cell / self._dL
        return dp_per_dx

    def stream_interface(self) -> None:
        """
        Interface for processing the stream within the well unit.

        Processes the fluid stream to update enthalpy, pressure, and mass rate, and prints
        the inlet and outlet fluid properties.
        """
        try:
            outlet_enthalpy, outlet_pressure, mass_rate = self.process_stream()
            self.mass_rate = mass_rate
            self.outlet_fluid.updateHP(outlet_enthalpy, outlet_pressure)
        except CoolPropError as cpe:
            raise type(cpe)(
                f"Well `stream_interface` failed\n\t{cpe}"
            ) from cpe
        except Exception as err:
            raise type(err)(
                "Well `stream_interface` failed"
            ) from err

    def process_stream(self) -> tuple[float, float, float]:
        r"""
        Updates dynamic variables along the wellbore.

        This method calculates fluid properties at each step along the wellbore by accounting
        for pressure loss, heat exchange, and friction, updating the state accordingly.

        Returns:
            tuple: (float, float, float) representing the outlet enthalpy, outlet pressure, and mass rate.

        Notes:
            The pressure drop and heat loss calculations are performed iteratively along the wellbore:

            1. **Pressure Loss**: Calculated using:

            .. math::
                \Delta P_{\text{loss}} = \frac{1}{2} f \frac{\Delta L \rho u^2}{D}

            Where:
                - :math:`f` is the friction factor (dimensionless),
                - :math:`\Delta L` is the segment length (meters),
                - :math:`\rho` is the fluid density (kg/m³),
                - :math:`u` is the flow velocity (m/s),
                - :math:`D` is the diameter of the wellbore (meters).

            2. **Heat Loss**: Calculated using:

            .. math::
                Q_{\text{loss}} = 2 \pi \Delta l k_{\text{rock}} \beta \Delta T

            Where:
                - :math:`k_{rock}` is the thermal conductivity of the surrounding rock (W/(m·K)),
                - :math:`\beta` is a dimensionless coefficient based on dimensionless time,
                - :math:`\Delta T` is the temperature difference between the rock and the fluid (K).
        """
        if self._specs.flow_rate_from_csv == "yes" and self.current_row < len(self.csv_data):
            row = self.csv_data[self.current_row]
            self.mass_rate = float(row[1]) * self.scaling_factor

        self._initialize_state()
        # print('t_d',(self._t_d - self._t_d_old) / self._t_scaling_factor / YEAR_TO_SECOND)
        t_d = self._get_dimensionless_time()
        g, dz, f_dir = self._g, self._dz, self._f_dir
        mdot, A = self.mass_rate, self._cross_sectional_area

        for i in range(1, self._num_cells):
            ff = self._compute_friction_factor(self._rho[i - 1], self._mu[i - 1], self._u[i - 1])
            dP_loss = self._compute_delta_P_loss(ff, self._rho[i - 1], self._u[i - 1])
            Q_loss = self._compute_Q_loss(self._T_f[i - 1] - self._T_r[i - 1], t_d)
            # TODO: make `Well` a pydantic dataclass and add this attribute so it's not mysteriously getting added here
            self.dp_loss_for_cell = dP_loss
            dp_grav_for_cell = f_dir * self._rho[i - 1] * g * dz
            self._P[i] = self._P[i - 1] - dp_grav_for_cell - dP_loss
            self._h[i] = self._h[i - 1] - f_dir * g * dz - Q_loss / mdot

            try:
                self.fluid_state_tmp.updateHP(self._h[i], self._P[i])
            except CoolPropError as outer_err:
                try:
                    # TODO: `self._T_f[i] = 300.0` could have unintented consequences
                    if self._T_f[i] == 0:
                        self._T_f[i] = 300.0
                    self.fluid_state_tmp.updatePT(self._P[i], self._T_f[i])
                except CoolPropError as inner_err:
                    raise type(inner_err)(
                        f"cell: {i} of {self._num_cells}\n\t{inner_err}"
                    ) from outer_err

            self._rho[i] = self.fluid_state_tmp.rho
            self._mu[i] = self.fluid_state_tmp.mu
            self._T_f[i] = self.fluid_state_tmp.T
            self._u[i] = mdot / A / self._rho[i]

        return self._h[i], self._P[i], self.mass_rate

    # -------------------------------------- Data Storing Functions -------------------------------------- #
    # These PUBLIC functions are specific to native wellbore units. Some of them are called by the native
    # orchestrator for iterative computations, while others are invoked by the economic unit. Please avoid
    # setting them for external wellbore units, as they will not be called by the native orchestrator,
    # and the economic inputs will need to be provided manually.

    def get_well_length(self) -> float:
        """
        Returns the length of the well.

        Returns:
            float: The well length (in meters).
        """
        # TODO: figure out if this method is really needed
        return self._well_length

    def get_diameter(self) -> float:
        """
        Returns the diameter of the wellbore.

        Returns:
            float: The diameter of the wellbore (in meters).
        """
        return self._diameter

    def get_probability_of_success(self) -> float:
        """
        Returns the probability of success for the well operation.

        Returns:
            float: The probability of success.
        """
        return self._specs.probability_of_success

    def update_dimensionless_time_old(self) -> None:
        """
        Updates the old dimensionless time with the current time.
        """
        self._t_d_old = self._t_d
        self.time_step += 1

    def update_dimensionless_time(self, del_t) -> None:
        """
        Updates the dimensionless time based on the time step provided.

        Args:
            del_t (float): The time step increment.
        """
        self._t_d = self._t_d_old + del_t

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _read_csv_file(self):
        """
        Reads flow rate data from a specified CSV file.

        Returns:
            list: The data read from the CSV file, excluding the header row.

        Raises:
            FileNotFoundError: If the specified CSV file does not exist.
        """
        file_path = self._specs.flow_rate_file
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, "r") as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)

    def _specs_post_processor(self):
        r"""
        Processes and sets various well specifications after initialization.

        This method initializes several key attributes of the well based on the specifications
        provided, such as the diameter, relative roughness, and cross-sectional area. It also sets up
        the well length, discretized variables, far-field temperature, gravity multiplier, and time scaling factor.

        The following steps are performed:

        1. **Diameter and Relative Roughness**:
            - Sets the wellbore diameter from the specifications.
            - Calculates the relative roughness using the formula:

            .. math::

                q = \frac{\epsilon}{Diameter}

            Where:
                - :math:`\epsilon` is the roughness height.

        2. **Cross-Sectional Area**:
            - The cross-sectional area is calculated using:

            .. math::

                \text{Area} = 0.25 \cdot \pi \cdot \text{Diameter}^2

        3. **Well Length**:
            - Initializes the well length using the method `_set_well_length()`.

        4. **Discretized Variables**:
            - Initializes variables that are discretized along the length of the wellbore by calling `_initialize_discretized_vars()`.

        5. **Far-Field Temperature**:
            - Sets up the temperature profile of the surrounding rock by calling `_initialize_farfield_temperature()`.

        6. **Gravity Multiplier**:
            - Configures the gravity multiplier based on the specifications using `_set_gravity_multiplier()`.

        7. **Time Scaling Factor**:
            - Computes the time scaling factor for the simulation using `_compute_time_scaling_factor()`.

        Returns:
            float: The computed time scaling factor for use in further calculations.

        Example:
            This method is typically called during the initialization of the well unit:

            .. code-block:: python

                well_unit = WellUnitNative(id="Well_01", specs=well_specs)
                well_unit._specs_post_processor()

        """
        self._diameter = self._specs.diameter
        self._relative_roughness = self._specs.epsilon / self._diameter
        self._cross_sectional_area = 0.25 * np.pi * self._diameter**2
        self._well_length = self._set_well_length()
        self._initialize_discretized_vars()
        self._initialize_farfield_temperature()
        self._set_gravity_multiplier()
        self._t_scaling_factor = self._compute_time_scaling_factor()

    def _initialize_attributes(self) -> float:
        """
        Initializes time-related attributes for the well unit.

        This method sets up dimensionless time variables used for simulating processes
        within the well. These attributes are essential for tracking the progression of
        time-dependent simulations and calculations.

        Attributes:
            _t_d (float): Dimensionless time at the current time step.
            _t_d_old (float): Dimensionless time at the previous time step.
        """
        self._t_d = 0.0  # dimensionless time at the current time step
        self._t_d_old = 0.0  # dimensionless time at the previous time step
        self.time_step = 0

    def _set_well_length(self) -> float:
        """
        Sets the well length based on the specifications.

        This method retrieves the well length from the provided specifications. It checks
        if the length is defined, and if not, raises an error to indicate that the necessary
        parameter is missing.

        Returns:
            float: The well length (in meters).

        Raises:
            RuntimeError: If the 'well_length' parameter is not found in the specifications.
        """
        if self._specs.well_length is None:
            raise RuntimeError(f"Required parameter 'well_length' is not found in specs.")
        else:
            return self._specs.well_length

    def _initialize_farfield_temperature(self) -> None:
        """
        Initializes the far-field temperature profile along the wellbore.

        This method sets up the temperature distribution of the surrounding rock along the well,
        based on the thermal gradient and surface temperature. It uses the specifications to
        calculate temperatures at various depths. The method does not support vertical deviation,
        and will raise an error if a deviation is specified.

        Raises:
            ValueError: If 'vertical_deviation' is specified, as it is not supported.
        """
        if self._specs.vertical_deviation is not None:
            raise ValueError(
                f"'vertical_deviation' is not supported in vertical well classes. Please use horizontal well."
            )

        zspace = np.linspace(self._specs.wellhead_depth, self._well_length, self._num_cells + 1)
        zspace = (zspace[1:] + zspace[:-1]) * 0.5  # depth at cell centers
        dTdz = self._specs.thermal_gradient
        T0 = self._specs.surface_temperature
        self._T_r = T0 + zspace * dTdz  # rock temperature (K)

    def _initialize_discretized_vars(self) -> None:
        """
        Initializes discretized variables for simulation along the wellbore.

        This method sets up arrays for various physical properties that will be used in discretized calculations
        along the wellbore. It also calculates the segment length for each cell in the simulation.

        Attributes:

        """
        num_cells = self._specs.num_cells
        self._num_cells = num_cells
        self._dL = self._well_length / num_cells
        self._dz = self._dL
        # TODO: these should be nested in a `WellState` class instance attribute
        # in the future which itself should be stored in a `History` class
        # instance attribute in each time step
        self._P = np.zeros(num_cells)  # pressure (Pa)
        self._h = np.zeros(num_cells)  # specific enthalpy (J/kg)
        self._rho = np.zeros(num_cells)  # fluid density (kg/m3)
        self._mu = np.zeros(num_cells)  # fluid dynamic viscosity (Pa s)
        self._T_f = np.zeros(num_cells)  # fluid temperature (K)
        self._T_r = np.zeros(num_cells)  # far-field temperature (K)
        self._u = np.zeros(num_cells)  # flow velocity (m/s)

    def _set_gravity_multiplier(self) -> None:
        """
        Configures the gravity multiplier for use in calculations.

        This method sets the gravity acceleration multiplier based on the specified scaling factor,
        allowing for modifications to gravitational effects in the simulation.

        Attributes:
            _g (float): The adjusted gravity acceleration (in meters per second squared).
        """
        self._g = GRAVITY_ACCELERATION * self._specs.gravity_scale_factor

    def _compute_time_scaling_factor(self) -> float:
        r"""
        Computes the time scaling factor for dimensionless time calculations.

        The time scaling factor is derived from the properties of the surrounding rock, following
        principles from Carslaw and Jaeger (1959). It is used to adjust time scales in the simulation
        of heat transfer processes.

        Returns:
            float: The computed time scaling factor.

        Formula:
            .. math::

                \text{Scaling Factor} = \frac{4 k_{\text{rock}}}{\rho_{\text{rock}} c_{p,\text{rock}} D^2}

            Where:
                - :math:`k_{rock}` is the thermal conductivity of the rock (W/m·K),
                - :math:`\rho_{rock}` is the density of the rock (kg/m³),
                - :math:`c_{p,rock}` is the specific heat capacity of the rock (J/kg·K),
                - :math:`D` is the wellbore diameter (m).
        """
        return (
            4.0
            * self._specs.rock_k
            / (self._specs.rock_density * self._specs.rock_cp * self._diameter**2)
        )

    def _initialize_state(self) -> None:
        """
        Initializes the fluid state and related properties at the start of the simulation.

        This method sets up the initial fluid properties (pressure, enthalpy, density, viscosity, etc.)
        and calculates initial conditions based on the fluid state at the well inlet. It uses the initial
        dimensionless time to begin the simulation.

        Attributes Managed:
            - `_P[0]`: Initial pressure (in Pascals).
            - `_h[0]`: Initial specific enthalpy (in J/kg).
            - `_rho[0]`: Initial fluid density (in kg/m³).
            - `_mu[0]`: Initial fluid viscosity (in Pa·s).
            - `_T_f[0]`: Initial fluid temperature (in Kelvin).
            - `_u[0]`: Initial flow velocity (in meters per second).
        """
        self.update_dimensionless_time(
            del_t=self._t_scaling_factor * self._specs.dt_list[self.time_step] * YEAR_TO_SECOND
        )
        # NOTE:
        # These values in `self.fluid_state_init` will likely be overwritten in
        # src/tango/orchestrators/native.py::SystemNative::update
        # depending on whether the system is balanced, which is most likely not
        # in the first iteration
        self.fluid_state_init = self.inlet_fluid
        # breakpoint()
        self._P[0] = self.fluid_state_init.P
        self._h[0] = self.fluid_state_init.H
        self._rho[0] = self.fluid_state_init.rho
        self._mu[0] = self.fluid_state_init.mu
        self._T_f[0] = self.fluid_state_init.T
        self._u[0] = self.mass_rate / self._cross_sectional_area / self._rho[0]
        self.fluid_state_tmp = FluidState.copy(self.inlet_fluid)

    def _compute_Q_loss(self, delta_T: float, t_d: float) -> float:
        r"""
        Computes heat loss based on temperature differences and dimensionless time.

        Args:
            delta_T (float): Temperature difference between the far-field and fluid (K).
            t_d (float): Dimensionless time.

        Returns:
            float: The computed heat loss.

        Notes:
            The dimensionless coefficient \( \beta \) is calculated as follows:

            .. math::
                \beta = \begin{cases}
                    (\pi t_d)^{-0.5} + 0.5 - 0.25 (t_d / \pi)^{0.5} + 0.125 t_d, & t_d \leq 2.8 \\
                    \frac{2.0}{\ln(4.0 t_d) - 1.16} - \frac{1.16}{(\ln(4.0 t_d) - 1.16)^2}, & t_d > 2.8
                \end{cases}
        """
        if t_d <= 2.8:
            beta = (np.pi * t_d) ** -0.5 + 0.5 - 0.25 * (t_d / np.pi) ** 0.5 + 0.125 * t_d
        else:
            beta = 2.0 / (np.log(4.0 * t_d) - 1.16) - 1.16 / (np.log(4.0 * t_d) - 1.16) ** 2

        return 2.0 * self._dL * np.pi * self._specs.rock_k * beta * delta_T

    def _compute_delta_P_loss(self, ff: float, rho: float, u: float) -> float:
        r"""
        Computes pressure loss using the Darcy-Weisbach equation.

        Args:
            ff (float): Friction factor.
            rho (float): Fluid density (kg/m³).
            u (float): Flow velocity (m/s).

        Returns:
            float: The computed pressure loss (Pa).

        Notes:
            The pressure loss is calculated using:

            .. math::
                \Delta P_{\text{loss}} = \frac{1}{2} f \frac{\Delta L \rho u^2}{D}

            Where:
                - :math:`f` is the friction factor (dimensionless),
                - :math:`\Delta L` is the segment length (meters),
                - :math:`\rho` is the fluid density (kg/m³),
                - :math:`u` is the flow velocity (m/s),
                - :math:`D` is the diameter of the wellbore (meters).
        """
        return 0.5 * ff * self._dL * rho * u**2 / self._diameter

    def _compute_friction_factor(self, rho, mu, u) -> float:
        r"""
        Computes friction factor using the Haaland equation.

        Args:
            rho (float): Fluid density (kg/m³).
            mu (float): Dynamic viscosity (Pa·s).
            u (float): Flow velocity (m/s).

        Returns:
            float: The computed friction factor.

        Notes:
            The Haaland equation for friction factor is:

            .. math::
                \frac{1}{\sqrt{f}} = -1.8 \log_{10} \left[ \left( \frac{r}{3.7} \right)^{1.11} + \frac{6.9}{Re} \right]

            Where:
                - \( Re \) is the Reynolds number, calculated as:

                .. math::
                    Re = \frac{\rho u D}{\mu}
        """
        Re = rho * u * self._diameter / mu  # Reynolds number
        r = self._relative_roughness  # relative roughness
        ff: float = (-1.8 * np.log10((r / 3.7) ** 1.11 + 6.9 / Re)) ** -2.0
        return ff

    def _get_dimensionless_time(self) -> float:
        return self._t_d
