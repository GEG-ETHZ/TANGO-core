import numpy as np
from math import erfc
from math import e as exp
from collections.abc import Callable
from pathlib import Path
import logging

from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from tango.core.abstracts.unit import Unit, SimplePressureDrop
from tango.core.fluidstate import FluidState
from tango.units.dataclasses import ReservoirSpecsNative
from tango.core.errors import CoolPropError, Validator

import csv
import os


class ReservoirUnitNative(Unit, SimplePressureDrop, Validator):
    """
    Represents a 1-D reservoir unit (well-pair) based on Adams et al. (2015).

    This class simulates fluid flow and thermal dynamics within a reservoir,
    managing fluid properties, mass rates, and fracking conditions. It supports
    reading flow rate data from CSV files for dynamic simulation.

    Attributes:
        specs (ReservoirSpecsNative): Specifications of the reservoir.
        inlet_fluid (FluidState): Fluid state at the reservoir inlet.
        outlet_fluid (FluidState): Fluid state at the reservoir outlet.
        mass_rate (float): Mass flow rate (in kg/s).
        fracing_mass_rate (float): Maximum mass rate before fracking occurs (in kg/s).
        current_row (int): Current row index for CSV data processing.
        csv_data (list): Data read from the CSV file, if applicable.
    """

    def __init__(self, id: str, specs: dict) -> None:
        """
        Initializes a new instance of the ReservoirUnitNative class.

        Args:
            id (str): Unique identifier for the reservoir unit.
            specs (dict): Specifications of the reservoir unit.
        """
        super().__init__(id, specs)
        Validator.__init__(self, Path(__file__).resolve().parent / "reservoir_validation.yaml")
        self.specs = ReservoirSpecsNative.from_dict(self._process_specs(specs))
        self._initialize_attributes()
        self._specs_post_processor()
        self.validate()
        thickness_warn = self.val_dict["thickness_warn"]
        if not (float(thickness_warn[0]) <= self.specs.thickness <= float(thickness_warn[-1])):
            logging.warning(
                f"Thickness ({self.specs.thicness:.3g} m) is outside expected range ({thickness_warn})"
            )
            logging.warning(f"This is ok if permeability ({self.permeability} m^2 is high")
        self.init_stream_interface()
        if self.specs.bc_iteration == None:
            self._thermal_depletion()
        self.current_row = 0
        if self.specs.flow_rate_from_csv == "yes":
            self.csv_data = self._read_csv_file()

    def init_stream_interface(self, P: float | None = None, T: float | None = None) -> None:
        """
        Initializes the fluid interface for the reservoir.

        Args:
            P (float, optional): Initial pressure (in Pascals). Defaults to `initial_pressure`.
            T (float, optional): Initial temperature (in Kelvin). Defaults to `initial_temperature`.
        """
        P = self.initial_pressure if P is None else P
        T = self.initial_temperature if T is None else T
        self.inlet_fluid = FluidState.withPT(self.fluid_name, P, T)
        self.outlet_fluid = FluidState.withPT(self.fluid_name, P, T)

    def stream_interface(self) -> None:
        r"""
        Manages the reservoir stream processing, updating fluid properties and checking fracking conditions.

        This method processes the fluid stream and calculates the fracking mass rate using:

        .. math::
            q_{\text{fracing}} = \frac{k h \Delta P}{\mu \ln(r_e / r_w)}

        Where:
            - \( q_{\text{fracing}} \): Fracking mass rate (kg/s).
            - \( k \): Permeability of the reservoir (m²).
            - \( h \): Thickness of the reservoir (m).
            - \( \Delta P \): Pressure difference across the reservoir (Pa).
            - \( \mu \): Fluid viscosity (Pa·s).
            - \( r_e \): Effective radius of the reservoir (m).
            - \( r_w \): Wellbore radius (m).

        Adjustments are made based on user choices to prevent fracking if necessary. The inlet
        and outlet fluid properties are then updated.

        Warnings:
            If the mass rate exceeds the fracking mass rate, the user is prompted to select an action.
        """
        try:
            outlet_pressure, outlet_temperature, mass_rate = self.process_stream()
            self.mass_rate = mass_rate
            self.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)
        except CoolPropError as cpe:
            raise type(cpe)(f"Reservoir `stream_interface` failed\n\t{cpe}")
        except Exception as err:
            raise type(err)("Reservoir `stream_interface` failed") from err

    def process_stream(self) -> tuple[float, float, float]:
        r"""
        Updates the reservoir state given the inlet state (outlet fluid state of the injection well).

        This method updates the reservoir's pressure, temperature, and mass flow rate by
        considering fluid properties, impedance, and energy dynamics. It supports reading
        flow rate data from a CSV file if specified.

        Returns:
            tuple: (float, float, float) representing outlet pressure (Pa), outlet temperature (K), and mass flow rate (kg/s).

        Process:
            1. **Mass Flow Rate**:
                If flow rates are specified in a CSV file, the mass rate is updated from the current row.

            2. **Impedance and Pressure Update**:
                The outlet pressure is computed as:

                .. math::
                    P_{\text{out}} = P_{\text{in}} - \dot{m} \cdot Z

                Where:
                    - \( P_{\text{out}} \): Outlet pressure (Pa).
                    - \( P_{\text{in}} \): Inlet pressure (Pa).
                    - \( \dot{m} \): Mass flow rate (kg/s).
                    - \( Z \): Impedance (Pa·s/kg).

                Impedance is calculated using average viscosity (\( \mu \)) and density (\( \rho \)) of the fluid.

            3. **Energy and Temperature Update**:
                Energy extraction and outlet temperature are updated iteratively:

                - Reservoir energy is calculated as:

                .. math::
                    E_{\text{reservoir}} = V_{\text{rock}} \cdot C_{v,\text{rock}} \cdot \Delta T

                - Energy extracted during the time step:

                .. math::
                    \Delta E = \dot{m} \cdot (h_{\text{prod}} - h_{\text{inj}}) \cdot \Delta t

                - Fraction of energy extracted:

                .. math::
                    \psi = \frac{\Delta E_{\text{extracted}}}{E_{\text{reservoir}}}

                - Outlet temperature:

                .. math::
                    T_{\text{out}} = \gamma \cdot \Delta T + T_{\text{in}}

                Where \( \gamma \) is a depletion curve factor based on \( \psi \).

        Notes:
            The energy dynamics are updated to account for reservoir depletion over time.
        """
        if self.specs.flow_rate_from_csv == "yes":
            if self.current_row < len(self.csv_data):
                row = self.csv_data[self.current_row]
                self.mass_rate = float(row[1])

        self.m_dot = self.m_dot_mult * self.mass_rate

        # Update reservoir pressure
        # TODO: `average_rho` and `outlet_pressure` should also be stored inside
        # `self` as state variables so that they are accessible in other methods
        # rather than recalculated, e.g. in `self.resistance`
        average_mu = 0.5 * (self.inlet_fluid.mu + self.outlet_fluid.mu)
        average_rho = 0.5 * (self.inlet_fluid.rho + self.outlet_fluid.rho)
        self._update_impedance(average_mu, average_rho)
        outlet_pressure = self.inlet_fluid.P - self.m_dot * self.impedance

        # Update reservoir temperature
        dt = self.specs.dt_list[self.time_step] * YEAR_TO_SECOND
        T_inj = self.inlet_fluid.T
        dT = self.initial_temperature - T_inj
        h_inj = self.inlet_fluid.H
        h_prod = self.outlet_fluid.H
        reservoir_energy = self.rock_volume * self.rock_C_v * dT
        self.update_energy_extracted(del_=self.m_dot * (h_prod - h_inj) * dt)
        # print('psi',(self._energy_extracted - self._energy_extracted_old) / (self.m_dot*(h_prod - h_inj))/ YEAR_TO_SECOND)
        psi = self._get_energy_extracted() / reservoir_energy
        gamma = self._depletion_curve(psi)
        outlet_temperature = gamma * dT + self.inlet_fluid.T

        return outlet_pressure, outlet_temperature, self.m_dot

    # -------------------------------------- Data Storing Functions -------------------------------------- #

    def get_del_pressure(self) -> float:
        """
        Retrieves the pressure drop between the previous and current time steps.

        Returns:
            float: The pressure drop (Pa).
        """
        return self._pressure_old - self.outlet_fluid.P

    def update_pressure_old(self) -> None:
        """
        Updates the previous pressure value with the current outlet pressure.
        """
        self._pressure_old = self.outlet_fluid.P

    def update_energy_extracted_old(self) -> None:
        """
        Updates the previous energy extracted value with the current energy value and increments the time step.
        """
        self._energy_extracted_old = self._energy_extracted
        self.time_step += 1

    def update_energy_extracted(self, del_: float) -> None:
        """Update the total energy extracted from the reservoir.

        Args:
            del_ (float): Energy extracted in the current time step (J).

        """
        self._energy_extracted = self._energy_extracted_old + del_

    def get_dp_simple(self, te: float, p: float, mdot: float) -> float:
        r"""Return approximate flow pressure delta [Pa], accounting for gravitational effects

        # Arguments
        - `te`: estimated temperature [K] for property evaluations
        - `p`: estimated pressure [Pa] for property evaluations
        - `mdot`: mass flow rate [kg/s], not used in this implementation
        """
        _mdot = mdot
        state = FluidState.withPT(self.specs.fluid_name, p, te)
        rho = state.rho
        mu = state.mu
        # (Pa·s/kg)
        impedance = self.get_impedance(mu, rho)
        dp = impedance * mdot
        return dp

    def get_flow_res_per_dx(self, te: float, p: float, mdot: float) -> float:
        r"""Return approximate flow pressure delta [Pa] per length, accounting only for dissipative losses

        # Arguments
        - `te`: estimated temperature [K] for property evaluations
        - `p`: estimated pressure [Pa] for property evaluations
        - `mdot`: mass flow rate [kg/s], not used in this implementation
        """
        dp = self.get_dp_simple(te, p, mdot)
        dp_per_dx: float = dp / self.specs.well_spacing

        return dp_per_dx

    # ----------------------------------------- Private Functions ---------------------------------------- #

    def _read_csv_file(self) -> list:
        """
        Reads flow rate data from a specified CSV file.

        Returns:
            list: The data read from the CSV file, excluding the header row.

        Raises:
            FileNotFoundError: If the specified CSV file does not exist.
        """
        file_path = self.specs.flow_rate_file
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"The CSV file does not exist at {file_path}")

        with open(file_path, "r") as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row
            return list(reader)

    def _specs_post_processor(self):
        """
        Processes reservoir specifications and initializes key attributes.

        Steps:
            - Computes reservoir area, volume, and porosity.
            - Calculates volumetric heat capacity of rocks.
            - Sets initial temperature and pressure.
            - Initializes impedance and other dynamic variables.
        """
        self.fluid_name = self.specs.fluid_name
        self.well_pattern = self.specs.well_pattern.upper()
        self.area = self._compute_area()
        self.volume = self.specs.thickness * self.area
        self.fluid_volume = self.specs.porosity * self.volume
        self.rock_volume = self.volume - self.fluid_volume
        self.rock_C_v = self.specs.rock_density * self.specs.rock_cp
        self.initial_temperature = self._compute_initial_temperature()
        self.initial_pressure = self._compute_initial_pressure()
        self.specs.well_diameter = self.specs.well_eff_diameter
        self._initialize_mdot_mult()
        self._set_impedance_func()
        self._set_pressure_old(self.initial_pressure)

    def _initialize_attributes(self) -> None:
        """
        Initializes reservoir state variables for simulation.

        Attributes:
            - `_pressure_old`: Reservoir pressure from the previous time step (Pa).
            - `_energy_extracted`: Total energy extracted from the reservoir (J).
            - `_energy_extracted_old`: Energy extracted in the previous time step (J).
            - `time_step`: Current simulation time step.
        """
        self._pressure_old = 0.0
        self._energy_extracted = 0.0
        self._energy_extracted_old = 0.0
        self.time_step = 0

    def _process_specs(self, specs) -> dict:
        """
        Processes the reservoir specifications and computes derived parameters.

        This method ensures the effective well diameter is computed if not already specified,
        and merges common and reservoir-specific specifications.

        Args:
            specs (dict): Input specifications for the reservoir.

        Returns:
            dict: Processed specifications with all required parameters.

        Process:
            - If `well_eff_diameter` is not specified:
                - Use the diameter of the injection and production wells to compute an effective diameter.
                - Defaults to 0.41 m if no values are provided.
            - Merge common and reservoir-specific specs.
        """
        if "well_eff_diameter" not in specs["reservoir"]:
            val = 0.41
            if "injection_well" in specs:
                if "diameter" in specs["injection_well"]:
                    val = specs["injection_well"]["diameter"]
            if "production_well" in specs:
                if "diameter" in specs["production_well"]:
                    val = 0.5 * (val + specs["production_well"]["diameter"])
            specs["reservoir"]["well_eff_diameter"] = val
        return specs["common"] | specs["reservoir"]

    def _compute_area(self) -> float:
        r"""
        Computes the reservoir area.

        Returns:
            float: The computed area (m²).

        Formula:
            .. math::
                A = \frac{1}{2} S^2

            Where:
                - \( S \): Well spacing (m).
        """
        return 0.5 * (self.specs.well_spacing**2) if self.specs.area is None else self.specs.area

    def _compute_initial_temperature(self) -> float:
        r"""
        Computes the initial reservoir temperature.

        Returns:
            float: The initial temperature (°C).

        Formula:
            .. math::
                T_{\text{init}} = T_0 + h \cdot \frac{dT}{dz}

            Where:
                - \( T_0 \): Surface temperature (°C).
                - \( h \): Reservoir depth (m).
                - \( \frac{dT}{dz} \): Thermal gradient (°C/m).
        """
        if self.specs.initial_temperature is not None:
            return self.specs.initial_temperature
        h, dTdz, T0 = (
            self.specs.reservoir_depth,
            self.specs.thermal_gradient,
            self.specs.surface_temperature,
        )
        return T0 + h * dTdz

    def _compute_initial_pressure(self) -> float:
        r"""
        Computes the initial reservoir pressure.

        Returns:
            float: The initial pressure (Pa).

        Formula:
            .. math::
                P_{\text{init}} = \rho_{\text{brine}} \cdot g \cdot h

            Where:
                - \( \rho_{\text{brine}} \): Brine density (kg/m³).
                - \( g \): Gravitational acceleration (m/s²).
                - \( h \): Reservoir depth (m).
        """
        if self.specs.initial_pressure is not None:
            return self.specs.initial_pressure
        return self.specs.brine_density * GRAVITY_ACCELERATION * self.specs.reservoir_depth

    def _initialize_mdot_mult(self) -> None:
        """
        Initializes the multiplier for converting injection flow rate to mass flow rate.

        Process:
            - Sets multiplier to 0.25 for 'INVERTED_5SPOT' well pattern.
            - Defaults to 1.0 for other patterns.
        """
        self.m_dot_mult = 0.25 if self.well_pattern == "INVERTED_5SPOT" else 1.0

    def _set_impedance_func(self) -> None:
        """
        Configures the impedance function based on the well pattern.

        Raises:
            ValueError: If the well pattern is not supported.
        """
        # TODO: use `match` statement to control which impedance function gets used so it's
        # more obvious what options are possible here
        self.impedance_func = getattr(
            self, f"_impedance_func_{self.well_pattern.lower().split('_')[-1]}", None
        )
        if self.impedance_func is None:
            raise ValueError(f"well_pattern: {self.well_pattern} is not supported in native reservoir unit.")

    @staticmethod
    def _impedance_func_5spot(mu, rho, k, b, L, D) -> float:
        r"""
        Computes impedance for a 5-spot well pattern.

        Formula:
            .. math::
                Z = \frac{\mu \ln(4L / \pi D)}{\rho k b}

        Args:
            mu (float): Fluid viscosity (Pa·s).
            rho (float): Fluid density (kg/m³).
            k (float): Reservoir permeability (m²).
            b (float): Reservoir thickness (m).
            L (float): Well spacing (m).
            D (float): Well diameter (m).

        Returns:
            float: Impedance (Pa·s/kg).
        """
        return mu * np.log(4.0 * L / (np.pi * D)) / (rho * k * b)

    @staticmethod
    def _impedance_func_doublet(mu, rho, k, b, L, D) -> float:
        r"""
        Computes impedance for a doublet well pattern.

        Formula:
            .. math::
                Z = \frac{\mu \left[\ln(L / (e \cdot D)) + \frac{D}{L}\right]}{\rho k b \pi}

        Args:
            mu (float): Fluid viscosity (Pa·s).
            rho (float): Fluid density (kg/m³).
            k (float): Reservoir permeability (m²).
            b (float): Reservoir thickness (m).
            L (float): Well spacing (m).
            D (float): Well diameter (m).

        Returns:
            float: Impedance (Pa·s/kg).
        """
        impedance: float = (
            mu  # (Pa * s)
            * (np.log(L / (np.e * D)) + D / L)  # non-dimensional
            / (rho * k * b * np.pi)  # (kg / m^3 * m^2 * m )
        )
        return impedance

    def _compute_depletion_curve_coeffs(self) -> list:
        r"""
        Computes coefficients for the thermal depletion curve.

        Returns:
            list: Depletion curve coefficients [p1, p2, p3].

        Process:
            1. Compute coefficients based on reservoir and fluid properties.
            2. \( p1 \), \( p2 \), and \( p3 \) are used in the depletion curve function.
        """
        if self.specs.bc_iteration != None:
            m_dot = self.mass_rate / 4.0 if self.well_pattern == "INVERTED_5SPOT" else self.mass_rate
        else:
            m_dot = (
                self.specs.mass_flow_rate / 4.0
                if self.well_pattern == "INVERTED_5SPOT"
                else self.specs.mass_flow_rate
            )

        b = self.specs.thickness
        k_rock = self.specs.rock_k
        rho_rock = self.specs.rock_density
        rho_fluid = 0.5 * (self.inlet_fluid.rho + self.outlet_fluid.rho)
        cp_rock = self.specs.rock_cp
        cp_fluid = 0.5 * (self.inlet_fluid.cp + self.outlet_fluid.cp)
        R = self.specs.well_spacing

        coeff1 = b * k_rock * rho_fluid / m_dot / rho_rock / cp_rock
        coeff2 = k_rock * R * rho_fluid / rho_rock / cp_fluid / m_dot

        p1 = np.minimum(-890.97 * coeff1 - 1.30, -1.3)
        p2 = 0.4095 * np.exp(-0.7815 * p1)
        p3 = np.clip(1 - (1.4646 * np.exp(-377.3 * coeff2)), 0.0, 1.0)

        return p1, p2, p3

    def _update_impedance(self, mu: float, rho: float) -> None:
        r"""Update the reservoir impedance by calling `self.get_impedance`"""
        self.impedance = self.get_impedance(mu, rho)

    def get_impedance(self, mu: float, rho: float) -> float:
        r"""Calculate and return the reservoir impedance using the doublet solution from
        Adams et al. (2020).

        This method calculates the impedance based on fluid properties, permeability, well spacing,
        and effective reservoir thickness.

        Args:
            mu (float): Fluid viscosity (Pa·s).
            rho (float): Fluid density (kg/m³).

        Process:
            1. Compute effective reservoir thickness:

            .. math::
                b_{\text{eff}} = b \cdot \text{NTG}

            Where:
                - \( b \): Reservoir thickness (m).
                - \( \text{NTG} \): Net-to-gross ratio (dimensionless).

            2. Impedance is computed using the configured impedance function:

            .. math::
                Z = f(\mu, \rho, k, b_{\text{eff}}, L, D)

            Where:
                - \( k \): Permeability (m²).
                - \( L \): Well spacing (m).
                - \( D \): Well diameter (m).
                - \( Z \): Impedance (Pa·s/kg).
        """
        k, b, NTG = float(self.specs.permeability), self.specs.thickness, self.specs.net_to_gross_ratio
        L, D = self.specs.well_spacing, self.specs.well_diameter
        b_eff = b * NTG  # Effective thickness
        impedance: float = self.impedance_func(mu, rho, k, b_eff, L, D)

        return impedance

    def _depletion_curve(self, psi: float) -> float:
        r"""
        Computes the depletion curve factor based on energy extraction.

        Args:
            psi (float): Fraction of energy extracted from the reservoir (dimensionless).

        Returns:
            float: The depletion curve value (dimensionless).

        Formula:
            For \( \psi \leq -p1 / p2 \):
            .. math::

                \gamma = 1 - (1 - p3) \cdot (1 - 0.5 \cdot \text{erfc}(p2 \psi + p1))

            For \( \psi > -p1 / p2 \):
            .. math::

                \gamma = 1 - (1 - p3) \cdot (1 - 0.5 \cdot \exp(-C \cdot (p2 \psi + p1)))

            Where:
                - \( p1, p2, p3 \): Depletion curve coefficients.
                - \( C \): Exponential decay constant, default value is 1.13.
                - \( \psi \): Fraction of energy extracted.

        Notes:
            - The depletion curve models how energy extraction affects reservoir temperature dynamics.
        """
        if self.specs.bc_iteration != None:
            self._thermal_depletion()

        p1, p2, p3 = self.p1, self.p2, self.p3
        if psi <= (-p1 / p2):
            return 1 - (1 - p3) * (1 - 0.5 * erfc(p2 * psi + p1))
        else:
            C = 1.13
            return 1 - (1 - p3) * (1 - 0.5 * np.exp(-C * (p2 * psi + p1)))

    def _get_energy_extracted(self) -> float:
        """
        Retrieves the total energy extracted from the reservoir.

        Returns:
            float: Total energy extracted (J).
        """
        return self._energy_extracted

    def _set_pressure_old(self, val: float) -> None:
        """
        Sets the previous reservoir pressure to the specified value.

        Args:
            val (float): Pressure value to set (Pa).
        """
        self._pressure_old = val

    def _thermal_depletion(self) -> None:
        r"""
        Initializes the thermal depletion curve coefficients.

        Process:
            - Calls the `_compute_depletion_curve_coeffs` method to compute coefficients \( p1, p2, p3 \).
            - Stores these coefficients for use in depletion curve calculations.
        """
        self.p1, self.p2, self.p3 = self._compute_depletion_curve_coeffs()
