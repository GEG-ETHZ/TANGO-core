import math

class FlowRateCalculator():
    """
    A class that calculates flow rate and pressure for a geothermal system involving injection wells,
    production wells, reservoir, and surface facilities. This class supports dynamic adjustment of mass
    flow rates based on reservoir specifications and conditions, including fracking flow calculations.

    Attributes:
        inj_well (object): Injection well instance.
        pro_well (object): Production well instance.
        pro_well_pump (object): Production well pump instance.
        reservoir (object): Reservoir instance.
        surface (object): Surface unit instance.
        mass_rate_test (float): Initial mass flow rate for testing.
        scaling_factor (float): Scaling factor for mass flow rate based on well pattern.
        tp (list): List to store thermal power values for later analysis.
    """
    def __init__(self, injection_well_class, production_well_class, production_well_pump_class, reservoir_class, surface_class):
        """
        Initializes the FlowRateCalculator class with instances of different system components.

        Args:
            injection_well_class (object): Instance of the injection well class.
            production_well_class (object): Instance of the production well class.
            production_well_pump_class (object): Instance of the production well pump class.
            reservoir_class (object): Instance of the reservoir class.
            surface_class (object): Instance of the surface unit class.

        Raises:
            ValueError: If the reservoir's well pattern is unsupported.
        """
        self.inj_well = injection_well_class
        self.pro_well = production_well_class
        self.pro_well_pump = production_well_pump_class
        self.reservoir = reservoir_class
        self.surface = surface_class
        self.mass_rate_test = 50.0
        self.surface._m_dot_mult = 1
        self.surface.system_external = True
        self.tp = []

        if (self.reservoir.specs.well_pattern == 'DOUBLET'):
            self.scaling_factor = 1.0
        elif (self.reservoir.specs.well_pattern == 'INVERTED_5SPOT'):
            self.scaling_factor = 4.0
        else:
            raise ValueError(f"well_pattern: {self.reservoir.specs.well_pattern} is not supported.")

    def fracing_flow(self):
        """
        Calculates the fracking mass flow rate based on reservoir specifications.

        Returns:
            float: Calculated fracking mass flow rate in kg/s.

        Formula:
            .. math::
                q = \frac{2 \pi h k \Delta P}{\mu \ln(r_e / r_w)}

            Where:
                - \( h \): Reservoir thickness (m)
                - \( k \): Permeability (m²)
                - \( \Delta P \): Over-pressure percentage of the hydrostatic pressure (Pa)
                - \( r_e \): Effective reservoir radius (m)
                - \( r_w \): Wellbore radius (m)
                - \( \mu \): Fluid viscosity (Pa·s)
                - \( \rho \): Fluid density (kg/m³)
        """
        h = self.reservoir.specs.thickness
        k = self.reservoir.specs.permeability
        p = self.reservoir.specs.hydro_static_pressure
        re = self.reservoir.specs.well_spacing / 2.0
        op = self.reservoir.specs.over_pressure_percentage
        rw = self.inj_well._specs.diameter
        mu = self.inj_well.outlet_fluid.mu
        rho = self.inj_well.outlet_fluid.rho

        q = (2 * math.pi * h * k * op / 100.0 * p) / (mu * math.log(re / rw))
        m = rho * q

        return m

    def pressure_finder(self, target_p):
        """
        Iteratively adjusts the pressure in the injection well to reach a target extraction pressure.

        Args:
            target_p (float): The target extraction pressure in Pascals.

        Process:
            - Updates the injection well pressure iteratively.
            - Calculates mass flow rate based on reservoir conditions.
            - Updates the reservoir and production well with new fluid states.
            - Adjusts the surface unit and production well pump (if applicable).

        Notes:
            - Supports both automatic and manual mass rate control.
            - Prevents mass rates from exceeding fracking thresholds.
            - Handles pump logic for production wells.
        """
        if self.reservoir.specs.bc_iteration['check_fracing']:
            test_p = 10000000
            iterations = 7
            print(self.reservoir.__class__.__name__, 'class name')

            for _ in range(iterations):

                # Update injection well
                self.inj_well.mass_rate = self.mass_rate_test
                self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
                self.inj_well.stream_interface()
                test_p += (target_p - self.inj_well.outlet_fluid.P)

                if(self.reservoir.__class__.__name__ != 'ReservoirFileReaderUnit'):
                    # Update reservoir
                    if (self.reservoir.specs.mass_rate['type'] == 'automatic'):
                        mass_rate = self.fracing_flow()
                    elif (self.reservoir.specs.mass_rate['type'] == 'manual'):
                        mass_rate = self.reservoir.specs.mass_rate['value']
                        if (self.reservoir.specs.bc_iteration['check_fracing']):
                            if (mass_rate > self.fracing_flow()):
                                mass_rate = self.fracing_flow()

                    if mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']:
                        self.reservoir.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate'] / self.scaling_factor
                    else:
                        self.reservoir.mass_rate = mass_rate / self.scaling_factor

                    if (self.scaling_factor == 4.0):
                        self.reservoir.m_dot_mult = 1.0

                self.reservoir.inlet_fluid.updatePT(P=self.inj_well.outlet_fluid.P, T=self.inj_well.outlet_fluid.T)
                self.reservoir.stream_interface()
                print(self.reservoir.mass_rate, 'flow1')

                # Update production well
                self.pro_well.mass_rate = self.reservoir.mass_rate
                self.pro_well.inlet_fluid.updatePT(P=self.reservoir.outlet_fluid.P, T=self.reservoir.outlet_fluid.T)
                self.pro_well.stream_interface()

                # If pump exists, apply pump logic
                if self.pro_well_pump:
                    pump_dp = max(0.0, self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8 - self.pro_well.outlet_fluid.P)

                    for i in range(5):
                        self.pro_well_pump.mass_rate = self.reservoir.mass_rate
                        self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P + pump_dp, T=self.pro_well.outlet_fluid.T)
                        self.pro_well_pump.stream_interface()

                        if pump_dp == 0.0 and self.pro_well_pump.outlet_fluid.P - self.surface.specs.target_extraction_pressure > 0:
                            break

                        pump_dp += (self.surface.specs.target_extraction_pressure - self.pro_well_pump.outlet_fluid.P)

                    outlet_pressure = self.pro_well_pump.outlet_fluid.P
                    outlet_temperature = self.pro_well_pump.outlet_fluid.T
                else:
                    outlet_pressure = self.pro_well.outlet_fluid.P
                    outlet_temperature = self.pro_well.outlet_fluid.T

                # Update surface
                self.surface.mass_rate = self.reservoir.mass_rate * self.scaling_factor
                if (self.surface.__class__.__name__ == 'SurfaceUnitFlexiblePP'):
                    self.surface.power_plant.iterative_inj_pressure = test_p
                else:
                    self.surface.iterative_inj_pressure = test_p
                self.surface.inlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)
                self.surface.stream_interface()
                self.mass_rate_test = self.surface.mass_rate

                print(self.inj_well.mass_rate, self.reservoir.mass_rate, self.pro_well.mass_rate, self.surface.mass_rate)

            if self.pro_well_pump:
                self.surface.prod_pump_aux = -(self.pro_well_pump.inlet_fluid.H - self.pro_well.outlet_fluid.H) * self.pro_well_pump.mass_rate
                self.surface.prod_pump_w_list.append(self.surface.prod_pump_aux)

            # self.tp.append(self.surface.power_plant.thermal_power)
            # print(self.tp)

        else:
            pass
