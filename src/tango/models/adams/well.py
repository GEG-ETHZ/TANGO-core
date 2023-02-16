from tango.models.base import *
from tango.model import ModelState
from tango.core.constants import YEAR_TO_SECOND, GRAVITY_ACCELERATION
from dataclasses import dataclass
import numpy as np


@dataclass
class WellSpecsAdams(WellSpecs):
    """The well specs based on Adams et al. (2015)."""
    vertical_deviation: float = 0.0    # the vertical deviation angle defined in degrees
    diameter: float = 0.14    # the well diameter (m)
    epsilon: float = 0.01    # roughness of the well (m)
    mass_rate: float = 25    # the mass flow rate (kg/s)
    num_cells: int = 100    # number of cells that is used for discretization


class WellStateAdams(WellState):
    """The well state model"""

    def __init__(self, specs: dict) -> None:
        WellState.__init__(self)
        self.fluidname = specs['fluid']['name']
        self.thermal_gradient = specs['reservoir']['thermal_gradient']
        self.surface_temperature = specs['reservoir']['surface_temperature']
        self.surface_pressure = specs['reservoir']['surface_pressure']
        self.reservoir_depth = specs['reservoir']['depth']


class WellModelAdams(WellModel):
    """The well model based on Adams et al. (2015)."""

    def __init__(self, specs: WellSpecs, state: WellStateAdams) -> None:
        self.specs = WellSpecsAdams(**specs)
        self.state = state

        D = self.specs.diameter
        num_cells = self.specs.num_cells
        g = GRAVITY_ACCELERATION
        vertical_deviation_rad = np.deg2rad(self.specs.vertical_deviation)
        well_length = self.state.reservoir_depth / np.cos(vertical_deviation_rad)

        dL = well_length/num_cells
        dz = self.state.reservoir_depth/num_cells
        self.zspace = np.linspace(0.0, self.state.reservoir_depth, num_cells+1)
        self.zspace = (self.zspace[1:] + self.zspace[:-1]) * 0.5 # the depth at cell centers

        self.P = np.zeros(num_cells)  # pressure (Pa)
        self.h = np.zeros(num_cells)  # specific enthalpy (J/kg)
        self.rho = np.zeros(num_cells)  # fluid density (kg/m3)
        self.u = np.zeros(num_cells)  # flow velocity (m/s)
        self.T_f = np.zeros(num_cells)  # fluid temperature (K)
        self.T_r = np.zeros(num_cells)  # rock temperature (K)

    def set_boundary_condition(self, boundary):
        if boundary=='inlet':
            fluid = self.state.inlet_fluid
        elif boundary=='outlet':
            fluid = self.state.outlet_fluid
        else:
            raise ValueError("The valid inputs are 'inlet' or 'outlet'.")

        self.P[0] = fluid.P
        self.h[0] = fluid.H
        self.rho[0] = fluid.rho

    @staticmethod
    def well_permeability(D, shape_factor=8.0):
        return 0.25*D**2/shape_factor

    @staticmethod
    def friction_factor(eps, D, rho, mu, u):
        """Returns the friction factor calculated using the Haaland equation (1983).

        Args:
            eps (float): the well roughness (m)
            D (float): the well diameter (m)
            rho (float): the fluid density (kg/m3)
            mu (float): the dynamic viscosity (Pa s)
            u (float): the flow velocity (m/s)

        Returns:
            float: the friction factor
        """
        Re = rho*u*D / mu  # Reynolds number
        r = eps/D  # relative roughness

        return (-1.8*np.log10((r/3.7)**1.11 + 6.9/Re))**-2.0

    def execute(self, state: ModelState) -> None:
        pass

