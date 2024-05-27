from tango.units.dataclasses import WellSpecsNative

import numpy as np
from CoolProp.CoolProp import PropsSI
import logging
import csv

class FluidState:
    def __init__(self, fluid_name):
        self.fluid_name = fluid_name
        self.P = None
        self.T = None
        self.rho = None
        self.H = None
        self.mu = None

    def updatePT(self, P, T):
        self.P = P
        self.T = T
        self.rho = PropsSI('D', 'P', P, 'T', T, self.fluid_name)
        self.H = PropsSI('H', 'P', P, 'T', T, self.fluid_name)
        self.mu = PropsSI('V', 'P', P, 'T', T, self.fluid_name)

    def updateHP(self, H, P):
        self.H = H
        self.P = P
        self.T = PropsSI('T', 'H', H, 'P', P, self.fluid_name)
        self.rho = PropsSI('D', 'H', H, 'P', P, self.fluid_name)
        self.mu = PropsSI('V', 'H', H, 'P', P, self.fluid_name)

    @classmethod
    def copy(cls, fluid_state):
        new_state = cls(fluid_state.fluid_name)
        new_state.P = fluid_state.P
        new_state.T = fluid_state.T
        new_state.rho = fluid_state.rho
        new_state.H = fluid_state.H
        new_state.mu = fluid_state.mu
        return new_state

class wellbore:
    def __init__(self):
        self._specs_post_processor()
        self._initialize_attributes()
        self.mass_rate = 50.0
        self._specs = WellSpecsNative

    def _initialize_attributes(self) -> float:
        self._t_d: float = 0.  # dimensionless time at current time step
        self._t_d_old: float = 0.  # dimensionless time at previous time step

    def update_dimensionless_time_old(self) -> None:
        self._t_d_old = self._t_d

    def update_dimensionless_time(self, del_t) -> None:
        self._t_d += del_t

    def _specs_post_processor(self) -> float:
        self._diameter = 0.4
        self._relative_roughness = 0.001 / self._diameter
        self._cross_sectional_area = 0.25 * np.pi * self._diameter ** 2
        self._well_length = 3000
        self._initialize_discretized_vars()
        self._initialize_farfield_temperature()
        self._set_gravity_multiplier()
        self._t_scaling_factor = self._compute_time_scaling_factor()

    def _initialize_discretized_vars(self) -> None:
        num_cells = 100
        self._num_cells = num_cells
        self._dL = self._well_length / num_cells
        self._dz = self._well_length / num_cells
        self._P = np.zeros(num_cells)  # pressure (Pa)
        self._h = np.zeros(num_cells)  # specific enthalpy (J/kg)
        self._rho = np.zeros(num_cells)  # fluid density (kg/m3)
        self._mu = np.zeros(num_cells)  # fluid dynamic viscosity (Pa s)
        self._T_f = np.zeros(num_cells)  # fluid temperature (K)
        self._T_r = np.zeros(num_cells)  # far field temperature (K)
        self._u = np.zeros(num_cells)  # flow velocity (m/s)

    def _initialize_farfield_temperature(self) -> None:
        zspace = np.linspace(0, self._well_length, self._num_cells + 1)
        zspace = (zspace[1:] + zspace[:-1]) * 0.5  # depth at cell centers
        dTdz = 0.03
        T0 = 283
        self._T_r = T0 + zspace * dTdz  # rock temperature (K)

    def _set_gravity_multiplier(self) -> None:
        self._g = 9.81 * 1.0

    def _compute_time_scaling_factor(self) -> float:
        """Carslaw and Jaeger (1959) for the scaling of time."""
        return 4.0 * 3.0 / (2500 * 1000 * self._diameter ** 2)

    def process_stream(self, inj_P) -> None:
        """update dynamic variables along wellbore"""
        self.inlet_fluid = FluidState('CO2')
        self.inlet_fluid.updatePT(inj_P, 323)
        self._initialize_state()
        g, dz, f_dir = self._g, self._dz, -1.0
        mdot, A = self.mass_rate, self._cross_sectional_area
        for i in range(1, self._num_cells):
            ff = self._compute_friction_factor(self._rho[i - 1], self._mu[i - 1], self._u[i - 1])
            dP_loss = self._compute_delta_P_loss(ff, self._rho[i - 1], self._u[i - 1])
            Q_loss = self._compute_Q_loss(delta_T=self._T_f[i - 1] - self._T_r[i - 1], t_d=self._t_d)
            self._P[i] = self._P[i - 1] - f_dir * self._rho[i - 1] * g * dz - dP_loss
            self._h[i] = self._h[i - 1] - f_dir * g * dz - Q_loss / mdot
            try:
                self.fluid_state_tmp.updateHP(self._h[i], self._P[i])
            except:
                logging.warning(f"Failed to update fluid state with HP. Updating with PT instead.")
                self.fluid_state_tmp.updatePT(self._P[i], self._T_f[i])
            self._rho[i] = self.fluid_state_tmp.rho
            self._mu[i] = self.fluid_state_tmp.mu
            self._T_f[i] = self.fluid_state_tmp.T
            self._u[i] = mdot / A / self._rho[i]

    def _initialize_state(self) -> None:
        self.update_dimensionless_time(del_t=self._t_scaling_factor * 1 * 31536000)
        self.fluid_state_init = self.inlet_fluid
        self._P[0] = self.fluid_state_init.P
        self._h[0] = self.fluid_state_init.H
        self._rho[0] = self.fluid_state_init.rho
        self._mu[0] = self.fluid_state_init.mu
        self._T_f[0] = self.fluid_state_init.T
        self._u[0] = self.mass_rate / self._cross_sectional_area / self._rho[0]
        self.fluid_state_tmp = FluidState.copy(self.inlet_fluid)

    def _get_dimensionless_time(self) -> float:
        return self._t_d

    def _compute_Q_loss(self, delta_T: float, t_d: float) -> float:
        """Returns the heat loss introduced Zhang et al., 2011 (10.1016/j.geothermics.2011.08.003).

        Args:
            delta_T (float): temperature differences between the farfield and fluid (K)
            t_d (float): dimensionless time (-)

        Returns:
            float: the heat loss
        """
        if t_d <= 2.8:
            beta = (np.pi * t_d) ** -0.5 + 0.5 - 0.25 * (t_d / np.pi) ** 0.5 + 0.125 * t_d
        else:
            beta = 2.0 / (np.log(4.0 * t_d) - 1.16) - 1.16 / (np.log(4.0 * t_d) - 1.16) ** 2

        return 2.0 * self._dL * np.pi * 3.0 * beta * delta_T

    def _compute_delta_P_loss(self, ff: float, rho: float, u: float) -> float:
        """Returns the pressure loss calculated using the Darcy--Weisbach equation.

        Args:
            ff (float): the friction factor (-)
            rho (float): the fluid density (kg/m3)
            u (float): the flow velocity (m/s)

        Returns:
            float: the pressure loss (Pa)
        """
        return 0.5 * ff * self._dL * rho * u ** 2 / self._diameter

    def _compute_friction_factor(self, rho, mu, u) -> float:
        """Returns the friction factor calculated using the Haaland equation (1983).

        Args:
            rho (float): the fluid density (kg/m3)
            mu (float): the dynamic viscosity (Pa s)
            u (float): the flow velocity (m/s)

        Returns:
            float: the friction factor (-)
        """
        Re = rho * u * self._diameter / mu  # Reynolds number
        r = self._relative_roughness  # relative roughness
        return (-1.8 * np.log10((r / 3.7) ** 1.11 + 6.9 / Re)) ** -2.0

    def save_to_csv(self, year):
        filename = f'wellbore_data_year_{year}.csv'
        with open(filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Cell', 'Pressure (Pa)', 'Temperature (K)'])
            for i in range(self._num_cells):
                writer.writerow([i, self._P[i], self._T_f[i]])

    def find_injection_pressure(self, target_bottom_pressure, P0_guess1, P0_guess2, tol=100000, max_iter=100):
        """Find the injection pressure using the secant method.

        Args:
            target_bottom_pressure (float): The desired bottom pressure of the wellbore.
            P0_guess1 (float): Initial guess for the injection pressure.
            P0_guess2 (float): Second guess for the injection pressure.
            tol (float, optional): Tolerance for the bottom pressure difference. Defaults to 1e-5.
            max_iter (int, optional): Maximum number of iterations. Defaults to 100.

        Returns:
            float: The estimated injection pressure.
        """
        def f(P0):
            self.process_stream(P0)
            return self._P[-1] - target_bottom_pressure

        P0_1, P0_2 = P0_guess1, P0_guess2
        f1, f2 = f(P0_1), f(P0_2)

        for i in range(max_iter):
            if abs(f2 - f1) < tol:
                raise ValueError("The difference between function values is too small.")

            P0_new = P0_2 - f2 * (P0_2 - P0_1) / (f2 - f1)
            f_new = f(P0_new)
            print(i, P0_new, f_new)

            if abs(f_new) < tol:
                return P0_new

            P0_1, P0_2 = P0_2, P0_new
            f1, f2 = f2, f_new

        raise RuntimeError("Secant method did not converge within the maximum number of iterations.")




# # Example usage
# wb = wellbore()
# target_bottom_pressure = 40534527  # example bottom pressure in Pascals
# P0_guess1 = 8e6  # initial guess for the injection pressure
# P0_guess2 = 15e6  # second guess for the injection pressure
#
# try:
#     estimated_injection_pressure = wb.find_injection_pressure(target_bottom_pressure, P0_guess1, P0_guess2)
#     print(f"Estimated Injection Pressure: {estimated_injection_pressure} Pa")
# except Exception as e:
#     print(str(e))
