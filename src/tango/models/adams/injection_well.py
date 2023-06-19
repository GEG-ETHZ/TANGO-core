from tango.models.base import *
from tango.models.adams import WellModelAdams
from tango.core.constants import YEAR_TO_SECOND

class InjectionWellModelAdams(WellModelAdams):
    """
    The well model that uses pressure and temperature as state variables.
    Assumes constant temperature within the well.
    """

    def __init__(self, specs: WellSpecs) -> None:
        WellModelAdams.__init__(self, specs)

    def update(self, *args) -> None:
        self.initialize_state()
        self.t_d += self.t_scaling_factor * self.specs.dt * YEAR_TO_SECOND

        for i in range(1, self.specs.num_cells):
            ff = self.friction_factor(self.rho[i-1], self.mu[i-1], self.u[i-1])
            self.P[i] = self.P[i-1] - self.rho[i-1]*self.g*self.dz \
                        - self.f_dir*self.delta_P_loss(ff, self.rho[i-1], self.u[i-1])

            self.fluid_state_tmp.updatePT(self.P[i], self.T_f[0])

            self.rho[i] = self.fluid_state_tmp.rho
            self.mu[i] = self.fluid_state_tmp.mu
            self.u[i] = self.m_dot / self.cross_section_area / self.rho[i]