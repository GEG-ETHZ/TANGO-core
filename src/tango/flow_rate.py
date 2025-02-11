import math

class FlowRateCalculator():
    def __init__(self, injection_well_class, production_well_class, production_well_pump_class, reservoir_class, surface_class):
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

        if self.reservoir.specs.bc_iteration['check_fracing']:
            test_p = 10000000
            iterations = 7

            for _ in range(iterations):

                # Update injection well
                self.inj_well.mass_rate = self.mass_rate_test
                self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
                self.inj_well.stream_interface()
                test_p += (target_p - self.inj_well.outlet_fluid.P)

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

            if self.pro_well_pump:
                self.surface.prod_pump_aux = -(self.pro_well_pump.inlet_fluid.H - self.pro_well.outlet_fluid.H) * self.pro_well_pump.mass_rate
                self.surface.prod_pump_w_list.append(self.surface.prod_pump_aux)

            # self.tp.append(self.surface.power_plant.thermal_power)
            # print(self.tp)

        else:
            pass
