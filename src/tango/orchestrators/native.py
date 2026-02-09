import networkx as nx
import numpy as np
import copy
import logging
import inspect

from tango.core.config import CONVERGENCE_CRITERIA
from tango.core.constants import MIN_INJ_TEMPERATURE
from tango.core.abstracts.orchestrator import UnitManager
from tango.utils import newton
from tango.core.errors import CoolPropError


class SystemNative(UnitManager):
    """
    Base class for managing native systems in TANGO.

    This class provides the framework for system iterations, convergence checks, and time-dependent variable updates.

    Attributes:
        x_lst (list): List of x-values for root-finding or iterative calculations.
        y_lst (list): List of y-values corresponding to `x_lst`.
        MAX_NUM_ITR (int): Maximum number of iterations allowed for convergence.
    """
    def __init__(self, specs):
        """
        Initializes the SystemNative object.

        Args:
            specs (dict): The specifications for the system.
        """
        super().__init__(specs)
        self.x_lst, self.y_lst = [], []
        self.MAX_NUM_ITR = CONVERGENCE_CRITERIA['max_num_itr']

    def max_itr_reached(self, count) -> bool:
        """
        Checks if the maximum number of iterations has been reached.

        Args:
            count (int): Current iteration count.

        Returns:
            bool: True if the maximum number of iterations is reached, False otherwise.
        """
        if count > self.MAX_NUM_ITR:
            logging.warning(f"Max number of iteration (={count}) has reached in '{inspect.stack()[1][3]}'. Exiting iteration.")
            return True

        return False

    def balanced(self) -> bool:
        """
        Determines if the system is balanced.

        Returns:
            bool: True (default implementation always returns True).
        """
        return True

    def update_time_dependent_vars(self) -> None:
        """
        Updates variables that depend on time.

        Placeholder in this base class.
        """
        pass

    def update(self) -> None:
        """
        Updates unknowns to balance the system.

        Placeholder in this base class.
        """
        pass


class SystemCPGNative(SystemNative):
    """
    Class for managing native systems in TANGO with CPG (Conventional Petroleum Geothermal) integration.

    This class extends `SystemNative` to include specific convergence criteria and balancing logic.

    Attributes:
        _CONVERGENCE_CRIT_DP_RESERVOIR (float): Convergence criterion for reservoir pressure difference.
        stop (bool): Indicates if the system should stop iterations.
    """
    def __init__(self, specs):
        """
        Initializes the SystemCPGNative object.

        Args:
            specs (dict): The specifications for the system.
        """
        super().__init__(specs)
        self._set_convergence_criteria()
        self.stop = False

    def _set_convergence_criteria(self) -> None:
        """
        Sets the convergence criteria for the system.
        """
        self._CONVERGENCE_CRIT_DP_RESERVOIR = CONVERGENCE_CRITERIA['dP_reservoir']

    def balanced(self) -> bool:
        """
        Determines if the system is balanced based on reservoir pressure.

        Returns:
            bool: True if the system is balanced, False otherwise.
        """
        if self.specs['schedule']['bc_iteration_checkpoint'] == 'production_well_bottom':
            self.dP_reservoir = self.unit.reservoir.get_del_pressure()
        elif self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom':
            self.dP_reservoir = 10000000

        is_balanced: bool = np.abs(self.dP_reservoir) < self._CONVERGENCE_CRIT_DP_RESERVOIR
        return is_balanced

    def update(self) -> None:
        """
        Updates unknown variables to balance the system.

        Handles pressure adjustments for production and injection wells.
        """
        if self.specs['schedule']['bc_iteration_checkpoint'] == 'production_well_bottom':
            self.x_lst.append(self.unit.surface.get_dP_pump())
            self.y_lst.append(self.dP_reservoir)
            if len(self.x_lst) == 1:  # First iteration
                root = 0.5 * self.dP_reservoir
            else:
                root = newton(self.x_lst, self.y_lst)
                self.x_lst.pop(0)
                self.y_lst.pop(0)
            self.unit.surface.update_dP_pump(root)
        elif self.specs['schedule']['bc_iteration_checkpoint'] == 'injection_well_bottom':
            raise NotImplementedError(f"injection_well_bottom checkpoint is not supperted in native workflow!")

        try:
            outlet_pressure, outlet_temperature, mass_rate = self.unit.surface.process_stream()
            self.unit.surface.outlet_fluid.updatePT(outlet_pressure, outlet_temperature)
        except CoolPropError as cpe:
            raise type(cpe)(
                f"Surface `process_stream` or `outlet_fluid.updatePT` failed\n\t{cpe}"
            ) from cpe
        except Exception as err:
            raise type(err)(
                "Surface `process_stream` or `outlet_fluid.updatePT` failed"
            ) from err
        

    def update_time_dependent_vars(self) -> None:
        """
        Updates time-dependent variables for all units in the system.

        Handles dimensionless time updates and increments row indices for time steps.
        """
        self.x_lst.clear()
        self.y_lst.clear()
        self.unit.reservoir.update_pressure_old()
        self.unit.reservoir.update_energy_extracted_old()
        self.unit.injection_well.update_dimensionless_time_old()
        self.unit.production_well.update_dimensionless_time_old()
        self.unit.surface.current_row += 1
        self.unit.reservoir.current_row += 1
        self.unit.injection_well.current_row += 1
        self.unit.production_well.current_row += 1


class SystemORCNative(SystemNative):
    """
    Class for managing native systems in TANGO with ORC (Organic Rankine Cycle) integration.

    This class extends `SystemNative` to include input checks specific to ORC systems.

    Attributes:
        None specific to this class beyond the inherited attributes.

    Methods:
        None specific to this class beyond the inherited methods.
    """
    def __init__(self, state):
        """
        Initializes the SystemORCNative object.

        Args:
            state (dict): The state for the system.
        """
        super().__init__(state)
        self._input_check(['injection_well', 'reservoir', 'production_well', 'production_well_pump', 'surface'])
        self._set_convergence_criteria()

    def _set_convergence_criteria(self) -> None:
        """
        Sets the convergence criteria for the system.

        Convergence criteria include:
        - Reservoir pressure difference (`dP_reservoir`).
        - Surface pressure difference (`dP_surface`).
        - Surface temperature difference (`dT_surface`).

        Updates:
            - `self._CONVERGENCE_CRIT_DP_RESERVOIR`
            - `self._CONVERGENCE_CRIT_DP_SURFACE`
            - `self._CONVERGENCE_CRIT_DT_SURFACE`
        """
        self._CONVERGENCE_CRIT_DP_RESERVOIR: float = CONVERGENCE_CRITERIA['dP_reservoir']
        self._CONVERGENCE_CRIT_DP_SURFACE: float = CONVERGENCE_CRITERIA['dP_surface']
        self._CONVERGENCE_CRIT_DT_SURFACE: float = CONVERGENCE_CRITERIA['dT_surface']

    def _update_injection_well_inlet_P(self) -> None:
        """
        Performs local iterations to update the injection well inlet pressure.

        Logic:

        - Iteratively adjusts the injection well inlet pressure to minimize the reservoir pressure difference.
        - Uses a root-finding approach with a Newton-Raphson method.

        Steps:

        - Updates the inlet state of the injection well.
        - Adjusts the pressure using `newton` root-finding until the reservoir pressure difference (`dP_reservoir`)
          is within the convergence criterion.

        Raises:
            RuntimeError: If the maximum number of iterations is reached.
        """
        self.unit.injection_well.update_inlet_state()
        dP_reservoir = self.unit.reservoir.get_del_pressure()
        x_lst, y_lst = [], []
        count = 0

        while np.abs(dP_reservoir) > self._CONVERGENCE_CRIT_DP_RESERVOIR:
            try:
                if self.max_itr_reached(count):
                    break
                x_lst.append(copy.deepcopy(self.unit.injection_well.inlet_fluid.P))
                y_lst.append(dP_reservoir)
                if len(x_lst) == 1:
                    root = x_lst[0] + dP_reservoir
                else:
                    root = newton(x_lst, y_lst)
                    x_lst.pop(0), y_lst.pop(0)
                self.unit.injection_well.update_inlet_fluid_state_PT(P=root)
                outlet_enthalpy, outlet_pressure, mass_rate = self.unit.injection_well.process_stream()
                self.unit.injection_well.outlet_fluid.updateHP(outlet_enthalpy, outlet_pressure)
                self.unit.reservoir.update_inlet_state()
                self.unit.reservoir.stream_interface()
                self.unit.reservoir.update_outlet_streams()
                dP_reservoir = self.unit.reservoir.get_del_pressure()
                count += 1
            except CoolPropError as cpe:
                raise type(cpe)(
                    f"`_update_injection_well_inlet_P` failed on iteration {count}\n\t{cpe}"
                ) from cpe
            except Exception as err:
                raise type(err)(
                    f"`_update_injection_well_inlet_P` failed on iteration {count}"
                ) from err

    def _compute_dP_surface(self) -> float:
        """
        Computes the surface pressure difference (`dP_surface`).

        Formula:
            dP_surface = P_outlet_production_pump - P_inlet_injection_well - dP_pipe

        Returns:
            float: Surface pressure difference.
        """
        dp_surface: float = self.unit.production_well_pump.outlet_fluid.P \
             - self.unit.injection_well.inlet_fluid.P \
             - self.unit.surface.dP_pipe
        return dp_surface

    def _update_production_well(self) -> None:
        """
        Updates the production well states.

        Steps:
        - Updates the inlet state of the production well.
        - Processes streams for the production well and its pump.
        - Updates the outlet streams and dependent states.
        - Calls `_update_production_well_pump` for further adjustments.
        """
        try:
            self.unit.production_well.update_inlet_state()
        except CoolPropError as cpe:
            raise type(cpe)(
                f"`self.unit.production_well.update_inlet_state` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.production_well.update_inlet_state` failed"
            ) from err
        try:
            self.unit.production_well.stream_interface()
        except CoolPropError as cpe:
            raise type(cpe)(
                f"`self.unit.production_well.stream_interface` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.production_well.stream_interface` failed"
            ) from err
        try:
            self.unit.production_well.update_outlet_streams()
        except CoolPropError as cpe:
            raise type(cpe)(
                f"`self.unit.production_well.update_outlet_streams` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.production_well.update_outlet_streams` failed"
            ) from err
        try:
            self.unit.production_well_pump.update_inlet_state()
        except CoolPropError as cpe:
            raise type(cpe)(
                f"`self.unit.production_well_pump.update_inlet_state` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.production_well_pump.update_inlet_state` failed"
            ) from err
        try:
            self.unit.production_well_pump.stream_interface()
        except CoolPropError as cpe:
            raise type(cpe)(
                f"`self.unit.production_well_pump.stream_interface` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.production_well_pump.stream_interface` failed"
            ) from err
        try:
            self.unit.production_well_pump.update_outlet_streams()
        except CoolPropError as cpe:
            raise type(cpe)(
                f"`self.unit.production_well_pump.update_outlet_streams` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.production_well_pump.update_outlet_streams` failed"
            ) from err
        try:
            self._update_production_well_pump()
        except CoolPropError as cpe:
            raise type(cpe)(
                f"`self._update_production_well_pump` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self._update_production_well_pump` failed"
            ) from err

    def _update_production_well_pump(self) -> None:
        """
        Performs local iterations to update `dP_pump` for the production well pump.

        Logic:
        - Iteratively adjusts the pump pressure difference (`dP_pump`) to minimize the surface pressure difference.
        - Uses a root-finding approach with the Newton-Raphson method.

        Steps:
        - Computes `dP_surface` and checks if pumping is needed.
        - Updates `dP_pump` iteratively until the convergence criterion is met.

        Raises:
            RuntimeError: If the maximum number of iterations is reached.
        """
        dP_pump = self.unit.production_well_pump.get_dP_pump()
        dP_surface = self._compute_dP_surface()

        if dP_pump == 0. and dP_surface >= 0:
            return  # No pumping needed

        x_lst, y_lst = [], []
        count = 0

        while np.abs(dP_surface) > self._CONVERGENCE_CRIT_DP_SURFACE:
            if self.max_itr_reached(count):
                break
            x_lst.append(copy.deepcopy(dP_pump))
            y_lst.append(dP_surface)
            if len(x_lst) == 1:
                root = -1.0 * dP_surface
            else:
                root = newton(x_lst, y_lst)
                x_lst.pop(0), y_lst.pop(0)
            try:
                self.unit.production_well_pump.set_dP_pump(root)
                self.unit.production_well_pump.update_inlet_fluid_state_with_pump()
                outlet_enthalpy, outlet_pressure, mass_rate = self.unit.production_well_pump.process_stream()
                self.unit.production_well_pump.outlet_fluid.updateHP(outlet_enthalpy, outlet_pressure)
            except CoolPropError as cpe:
                raise type(cpe)(
                    f"`_update_production_well_pump` failed on iteration {count}\n\t{cpe}"
                ) from cpe
            except Exception as err:
                raise type(err)(
                    f"`_update_production_well_pump` failed on iteration {count}"
                ) from err
            
            self.unit.surface.update_inlet_state()
            self.unit.surface.overwrite_state_pipe()
            dP_pump = self.unit.production_well_pump.get_dP_pump()
            dP_surface = self._compute_dP_surface()
            count += 1

        self.unit.surface.w_downhole_pump = self.unit.production_well_pump.get_w_pump()

    def _update_surface(self) -> None:
        """
        Updates the surface system states.

        Steps:
        - Updates the inlet and outlet states of the surface system.
        - Integrates with the injection well to ensure consistency in states.
        """
        try:
            self.unit.surface.update_inlet_state()
        except CoolPropError as cpe:
            raise type(cpe)(f"`self.unit.surface.update_inlet_state` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.surface.update_inlet_state` failed"
            ) from err
        try:
            self.unit.surface.stream_interface()
        except CoolPropError as cpe:
            raise type(cpe)(f"`self.unit.surface.stream_interface` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.surface.stream_interface` failed"
            ) from err
        try:
            self.unit.surface.update_outlet_streams()
        except CoolPropError as cpe:
            raise type(cpe)(f"`self.unit.surface.update_outlet_streams` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.surface.update_outlet_streams` failed"
            ) from err
        try:
            self.unit.injection_well.update_inlet_state()
        except CoolPropError as cpe:
            raise type(cpe)(f"`self.unit.injection_well.update_inlet_state` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.injection_well.update_inlet_state` failed"
            ) from err

    def _update_injection_well_inlet_T(self) -> None:
        """Perform local iterations to update the injection well inlet temperature.

        Logic:
        - Updates the inlet temperature of the injection well to minimize the surface temperature difference.
        - Uses a root-finding approach with the Newton-Raphson method.

        Steps:
        - Updates the surface system's inlet and outlet states.
        - Computes the temperature difference (`dT_surface`) between the injection well and the surface outlet.
        - Adjusts the injection well inlet temperature iteratively to achieve convergence.

        Notes:
        - Ensures the temperature does not fall below a minimum threshold (`MIN_INJ_TEMPERATURE`).

        Raises:
            RuntimeError: If Newton-Raphson fails and no valid root is found.

        """
        try:
            self.unit.surface.update_inlet_state()
        except CoolPropError as cpe:
            raise type(cpe)(f"`self.unit.surface.update_inlet_state` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.surface.update_inlet_state` failed"
            ) from err
        try:
            self.unit.surface.stream_interface()
        except CoolPropError as cpe:
            raise type(cpe)(f"`self.unit.surface.stream_interface` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.surface.stream_interface` failed"
            ) from err
        try:
            self.unit.surface.update_outlet_streams()
        except CoolPropError as cpe:
            raise type(cpe)(
                f"`self.unit.surface.update_outlet_streams` failed\n\t{cpe}") from cpe
        except Exception as err:
            raise type(err)(
                "`self.unit.surface.update_outlet_streams` failed"
            ) from err

        dT_surface = self.unit.injection_well.get_del_temperature(
            T=self.unit.surface.outlet_fluid.T
        )
        self.x_lst.append(copy.deepcopy(self.unit.injection_well.get_inlet_temperature_tmp()))
        self.y_lst.append(dT_surface)

        if len(self.x_lst) == 1:  # First iteration
            root = self.unit.surface.outlet_fluid.T
        else:
            try:
                root = newton(self.x_lst, self.y_lst)
            except Exception:
                root = -1.0  # Dummy value
            root = max(root, MIN_INJ_TEMPERATURE)
            self.x_lst.pop(0)
            self.y_lst.pop(0)

        self.unit.injection_well.update_inlet_fluid_state_PT(T=root)
        self.unit.injection_well.update_inlet_temperature_tmp()

    def balanced(self) -> bool:
        """
        Checks if the system is balanced.

        Logic:
            The system is balanced if:
            - Reservoir pressure difference (`dP_reservoir`) is within the convergence criterion.
            - Surface pressure difference (`dP_surface`) is within the convergence criterion.
            - Surface temperature difference (`dT_surface`) is within the convergence criterion.

        Returns:
            bool: True if the system is balanced, False otherwise.
        """
        dP_reservoir = self.unit.reservoir.get_del_pressure()
        dP_surface = self._compute_dP_surface()
        dT_surface = self.unit.injection_well.get_del_temperature(T=self.unit.surface.outlet_fluid.T)

        is_balanced: bool = (
            (np.abs(dP_reservoir) < self._CONVERGENCE_CRIT_DP_RESERVOIR) and
            (np.abs(dP_surface) < self._CONVERGENCE_CRIT_DP_SURFACE) and
            (np.abs(dT_surface) < self._CONVERGENCE_CRIT_DT_SURFACE)
        )
        return is_balanced

    def update(self) -> None:
        """
        Updates unknown variables to balance the system.

        Logic:
            Iteratively calls methods to update pressure, temperature, and production well states
            until the system is balanced or the maximum iteration limit is reached.

        Steps:
            - Updates the injection well inlet pressure.
            - Updates the production well states.
            - Updates the injection well inlet temperature.

        Raises:
            RuntimeError: If the maximum number of iterations is reached without balancing.
        """
        count = 0

        while not self.balanced():
            if self.max_itr_reached(count):
                break
            self._update_injection_well_inlet_P()
            self._update_production_well()
            self._update_injection_well_inlet_T()
            count += 1

    def update_time_dependent_vars(self) -> None:
        """
        Updates time-dependent variables for all system units.

        Logic:
            Clears historical lists of x and y values used in root-finding.
            Updates time-dependent variables, such as dimensionless time and current row indices,
            for reservoir, injection well, production well, and surface systems.

        Steps:
            - Updates:
              - Reservoir pressure and energy extracted.
              - Injection and production wells' dimensionless times.
              - Current row indices for all units.
        """
        self.x_lst.clear()
        self.y_lst.clear()
        self.unit.reservoir.update_pressure_old()
        self.unit.reservoir.update_energy_extracted_old()
        self.unit.injection_well.update_dimensionless_time_old()
        self.unit.production_well.update_dimensionless_time_old()
        self.unit.production_well_pump.update_dimensionless_time_old()
        self.unit.surface.current_row += 1
        self.unit.reservoir.current_row += 1
        self.unit.injection_well.current_row += 1
        self.unit.production_well.current_row += 1
        self.unit.production_well_pump.current_row += 1
