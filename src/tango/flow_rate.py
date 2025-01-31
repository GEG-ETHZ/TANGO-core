import math

class FlowRateCalculator():
    def __init__(self, injection_well_class, production_well_class, production_well_pump_class, reservoir_class, surface_class):
        self.inj_well = injection_well_class
        self.pro_well = production_well_class
        self.pro_well_pump = production_well_pump_class
        self.reservoir = reservoir_class
        self.surface = surface_class

    def prr(self):
        print(self.inj_well.__class__.__name__)
        print(self.pro_well.__class__.__name__)
        print(self.pro_well_pump.__class__.__name__)
        print(self.reservoir.__class__.__name__)
        print(self.surface.__class__.__name__)
        # print(self.well.outlet_fluid.T - 273.15, self.well.outlet_fluid.P/1000000)
        # self.well.update_inlet_fluid_state_PT(P=6000000)
        # self.well.mass_rate = 40
        # self.well.stream_interface()
        # print(self.well.outlet_fluid.P)
        # print(self.well.inlet_fluid.P)

    def fracing_flow(self):
        # print(self.reservoir.specs.thickness)
        # print(self.reservoir.specs.permeability)
        # print(self.reservoir.specs.hydro_static_pressure)
        # print(self.reservoir.specs.well_spacing / 2.0)
        # print(self.reservoir.specs.over_pressure_percentage)
        # print(self.well._specs.diameter)
        # print(self.reservoir.inlet_fluid.mu)
        # print(self.reservoir.inlet_fluid.rho)

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

        # print(self.reservoir.specs.bc_iteration['check_fracing'])
        # print(q, m)

        return m

    # def pressure_finder(self, target_p):
    #     if (self.reservoir.specs.bc_iteration['check_fracing']):
    #         test_p = 10000000
    #
    #         for _ in range(8):
    #
    #             print(_, self.inj_well.inlet_fluid.P, self.inj_well.inlet_fluid.T, self.reservoir.mass_rate)
    #
    #             self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
    #             self.inj_well.stream_interface()
    #             test_p = test_p + (target_p - self.inj_well.outlet_fluid.P) # new pressure
    #
    #             ##################################################################################################
    #
    #             mass_rate = self.fracing_flow() # new mass rate
    #             if (mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']):
    #                 self.reservoir.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate']
    #             else:
    #                 self.reservoir.mass_rate = self.fracing_flow()
    #             self.reservoir.inlet_fluid.updatePT(P=self.inj_well.outlet_fluid.P, T=self.inj_well.outlet_fluid.T)
    #             self.reservoir.stream_interface() # with new mass rate
    #
    #             self.inj_well.mass_rate = self.reservoir.mass_rate
    #
    #             ##################################################################################################
    #
    #             self.pro_well.mass_rate = self.reservoir.mass_rate
    #             self.pro_well.inlet_fluid.updatePT(P=self.reservoir.outlet_fluid.P, T=self.reservoir.outlet_fluid.T)
    #             self.pro_well.stream_interface()
    #
    #             ##################################################################################################
    #
    #             if (self.pro_well.outlet_fluid.P < self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8):
    #                 pump_dp = self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8 - self.pro_well.outlet_fluid.P
    #             else:
    #                 pump_dp = 0.0
    #
    #             # print('eyb', pump_dp)
    #
    #             for i in range(5):
    #                 self.pro_well_pump.mass_rate = self.reservoir.mass_rate
    #                 # print(_, 'p_in', self.pro_well.outlet_fluid.P + pump_dp)
    #                 self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P + pump_dp, T=self.pro_well.outlet_fluid.T)
    #                 self.pro_well_pump.stream_interface()
    #                 # print(_, 'p_out', self.pro_well_pump.outlet_fluid.P)
    #
    #                 print(i, self.pro_well_pump.outlet_fluid.P, self.pro_well_pump.inlet_fluid.P)
    #
    #                 if ((pump_dp == 0.0) and (self.pro_well_pump.outlet_fluid.P - 4000000.0 > 0)):
    #                     break
    #
    #                 # pump_dp = self.pro_well_pump.outlet_fluid.P - self.inj_well.inlet_fluid.P
    #
    #                 pump_dp += (4000000.0 - self.pro_well_pump.outlet_fluid.P)
    #                 # print(_, 'pump_dp', pump_dp)
    #
    #             # self.pro_well_pump.mass_rate = self.reservoir.mass_rate
    #             # self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P, T=self.pro_well.outlet_fluid.T)
    #             # self.pro_well_pump.stream_interface()
    #
    #             ##################################################################################################
    #
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #             print(self.surface.__class__.__name__)
    #             self.surface.power_plant.iterative_inj_pressure = test_p
    #             self.surface.inlet_fluid.updatePT(P=self.pro_well_pump.outlet_fluid.P, T=self.pro_well_pump.outlet_fluid.T)
    #             self.surface.stream_interface() # with new inlet P, T, and m. Its outlet was already set!
    #
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #
    #     else:
    #         pass

    # def pressure_finder(self, target_p):
    #     print('self.pro_well_pump', self.pro_well_pump)
    #     if (self.reservoir.specs.bc_iteration['check_fracing']):
    #         test_p = 10000000
    #
    #         for _ in range(7):
    #
    #             print(_, self.inj_well.inlet_fluid.P, self.inj_well.inlet_fluid.T, self.reservoir.mass_rate)
    #
    #             print('problem', test_p, self.surface.outlet_fluid.T, target_p)
    #
    #             self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
    #             self.inj_well.stream_interface()
    #             test_p = test_p + (target_p - self.inj_well.outlet_fluid.P) # new pressure
    #
    #             ##################################################################################################
    #
    #             mass_rate = self.fracing_flow() # new mass rate
    #             if (mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']):
    #                 self.reservoir.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate']
    #             else:
    #                 self.reservoir.mass_rate = self.fracing_flow()
    #             self.reservoir.inlet_fluid.updatePT(P=self.inj_well.outlet_fluid.P, T=self.inj_well.outlet_fluid.T)
    #             self.reservoir.stream_interface() # with new mass rate
    #
    #             self.inj_well.mass_rate = self.reservoir.mass_rate
    #
    #             ##################################################################################################
    #
    #             self.pro_well.mass_rate = self.reservoir.mass_rate
    #             self.pro_well.inlet_fluid.updatePT(P=self.reservoir.outlet_fluid.P, T=self.reservoir.outlet_fluid.T)
    #             self.pro_well.stream_interface()
    #
    #             ##################################################################################################
    #
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #             print(self.surface.__class__.__name__)
    #             self.surface.power_plant.iterative_inj_pressure = test_p
    #             self.surface.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P, T=self.pro_well.outlet_fluid.T)
    #             self.surface.stream_interface() # with new inlet P, T, and m. Its outlet was already set!
    #
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #
    #     else:
    #         pass

    # def pressure_finder(self, target_p):
    #     if (self.reservoir.specs.bc_iteration['check_fracing']):
    #         test_p = 10000000
    #
    #         for _ in range(8):
    #
    #             print(_, self.inj_well.inlet_fluid.P, self.inj_well.inlet_fluid.T, self.reservoir.mass_rate)
    #
    #             self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
    #             self.inj_well.stream_interface()
    #             test_p = test_p + (target_p - self.inj_well.outlet_fluid.P) # new pressure
    #
    #             ##################################################################################################
    #
    #             mass_rate = self.fracing_flow() # new mass rate
    #             if (mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']):
    #                 self.reservoir.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate']
    #             else:
    #                 self.reservoir.mass_rate = self.fracing_flow()
    #             self.reservoir.inlet_fluid.updatePT(P=self.inj_well.outlet_fluid.P, T=self.inj_well.outlet_fluid.T)
    #             self.reservoir.stream_interface() # with new mass rate
    #
    #             self.inj_well.mass_rate = self.reservoir.mass_rate
    #
    #             ##################################################################################################
    #
    #             self.pro_well.mass_rate = self.reservoir.mass_rate
    #             self.pro_well.inlet_fluid.updatePT(P=self.reservoir.outlet_fluid.P, T=self.reservoir.outlet_fluid.T)
    #             self.pro_well.stream_interface()
    #
    #             ##################################################################################################
    #
    #             if (self.pro_well.outlet_fluid.P < self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8):
    #                 pump_dp = self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8 - self.pro_well.outlet_fluid.P
    #             else:
    #                 pump_dp = 0.0
    #
    #             # print('eyb', pump_dp)
    #
    #             for i in range(5):
    #                 self.pro_well_pump.mass_rate = self.reservoir.mass_rate
    #                 # print(_, 'p_in', self.pro_well.outlet_fluid.P + pump_dp)
    #                 self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P + pump_dp, T=self.pro_well.outlet_fluid.T)
    #                 self.pro_well_pump.stream_interface()
    #                 # print(_, 'p_out', self.pro_well_pump.outlet_fluid.P)
    #
    #                 print(i, self.pro_well_pump.outlet_fluid.P, self.pro_well_pump.inlet_fluid.P)
    #
    #                 if ((pump_dp == 0.0) and (self.pro_well_pump.outlet_fluid.P - 4000000.0 > 0)):
    #                     break
    #
    #                 # pump_dp = self.pro_well_pump.outlet_fluid.P - self.inj_well.inlet_fluid.P
    #
    #                 pump_dp += (4000000.0 - self.pro_well_pump.outlet_fluid.P)
    #                 # print(_, 'pump_dp', pump_dp)
    #
    #             ##################################################################################################
    #
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #             print(self.surface.__class__.__name__)
    #             self.surface.power_plant.iterative_inj_pressure = test_p
    #             self.surface.inlet_fluid.updatePT(P=self.pro_well_pump.outlet_fluid.P, T=self.pro_well_pump.outlet_fluid.T)
    #             self.surface.stream_interface() # with new inlet P, T, and m. Its outlet was already set!
    #
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #
    #     else:
    #         pass

    # def pressure_finder(self, target_p):
    #     if self.reservoir.specs.bc_iteration['check_fracing']:
    #         test_p = 10000000
    #         iterations = 8 if self.pro_well_pump else 7
    #
    #         for _ in range(iterations):
    #             print(_, self.inj_well.inlet_fluid.P, self.inj_well.inlet_fluid.T, self.reservoir.mass_rate)
    #             print('problem', test_p, self.surface.outlet_fluid.T, target_p)
    #
    #             self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
    #             self.inj_well.stream_interface()
    #             test_p += (target_p - self.inj_well.outlet_fluid.P)
    #
    #             # Update mass rate
    #             mass_rate = self.fracing_flow()
    #             if mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']:
    #                 self.reservoir.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate']
    #             else:
    #                 self.reservoir.mass_rate = mass_rate
    #
    #             self.reservoir.inlet_fluid.updatePT(P=self.inj_well.outlet_fluid.P, T=self.inj_well.outlet_fluid.T)
    #             self.reservoir.stream_interface()
    #             self.inj_well.mass_rate = self.reservoir.mass_rate
    #
    #             # Update production well
    #             self.pro_well.mass_rate = self.reservoir.mass_rate
    #             self.pro_well.inlet_fluid.updatePT(P=self.reservoir.outlet_fluid.P, T=self.reservoir.outlet_fluid.T)
    #             self.pro_well.stream_interface()
    #
    #             # If pump exists, apply pump logic
    #             if self.pro_well_pump:
    #                 pump_dp = max(0.0, self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8 - self.pro_well.outlet_fluid.P)
    #
    #                 for i in range(5):
    #                     self.pro_well_pump.mass_rate = self.reservoir.mass_rate
    #                     self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P + pump_dp, T=self.pro_well.outlet_fluid.T)
    #                     self.pro_well_pump.stream_interface()
    #
    #                     print(i, self.pro_well_pump.outlet_fluid.P, self.pro_well_pump.inlet_fluid.P)
    #
    #                     if pump_dp == 0.0 and self.pro_well_pump.outlet_fluid.P - 6000000.0 > 0:
    #                         break
    #
    #                     pump_dp += (6000000.0 - self.pro_well_pump.outlet_fluid.P)
    #
    #                 outlet_pressure = self.pro_well_pump.outlet_fluid.P
    #                 outlet_temperature = self.pro_well_pump.outlet_fluid.T
    #             else:
    #                 outlet_pressure = self.pro_well.outlet_fluid.P
    #                 outlet_temperature = self.pro_well.outlet_fluid.T
    #
    #             # Update surface
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #             print(self.surface.__class__.__name__)
    #             self.surface.power_plant.iterative_inj_pressure = test_p
    #             self.surface.inlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)
    #             self.surface.stream_interface()
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #     else:
    #         pass

    # def pressure_finder(self, target_p):
    #     if self.reservoir.specs.bc_iteration['check_fracing']:
    #         test_p = 10000000
    #
    #         while True:
    #             prev_test_p = test_p
    #             print(self.inj_well.inlet_fluid.P, self.inj_well.inlet_fluid.T, self.reservoir.mass_rate)
    #             print('problem', test_p, self.surface.outlet_fluid.T, target_p)
    #
    #             self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
    #             self.inj_well.stream_interface()
    #             test_p += (target_p - self.inj_well.outlet_fluid.P)
    #
    #             # Stop iteration if pressure change is below threshold
    #             if abs(test_p - prev_test_p) < 50000.0:
    #                 break
    #
    #             # Update mass rate
    #             mass_rate = self.fracing_flow()
    #             if mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']:
    #                 self.reservoir.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate']
    #             else:
    #                 self.reservoir.mass_rate = mass_rate
    #
    #             self.reservoir.inlet_fluid.updatePT(P=self.inj_well.outlet_fluid.P, T=self.inj_well.outlet_fluid.T)
    #             self.reservoir.stream_interface()
    #             self.inj_well.mass_rate = self.reservoir.mass_rate
    #
    #             # Update production well
    #             self.pro_well.mass_rate = self.reservoir.mass_rate
    #             self.pro_well.inlet_fluid.updatePT(P=self.reservoir.outlet_fluid.P, T=self.reservoir.outlet_fluid.T)
    #             self.pro_well.stream_interface()
    #
    #             # If pump exists, apply pump logic
    #             if self.pro_well_pump:
    #                 pump_dp = max(0.0, self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8 - self.pro_well.outlet_fluid.P)
    #
    #                 for i in range(5):
    #                     self.pro_well_pump.mass_rate = self.reservoir.mass_rate
    #                     self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P + pump_dp, T=self.pro_well.outlet_fluid.T)
    #                     self.pro_well_pump.stream_interface()
    #
    #                     print(i, self.pro_well_pump.outlet_fluid.P, self.pro_well_pump.inlet_fluid.P)
    #
    #                     if pump_dp == 0.0 and self.pro_well_pump.outlet_fluid.P - 6000000.0 > 0:
    #                         break
    #
    #                     pump_dp += (6000000.0 - self.pro_well_pump.outlet_fluid.P)
    #
    #                 outlet_pressure = self.pro_well_pump.outlet_fluid.P
    #                 outlet_temperature = self.pro_well_pump.outlet_fluid.T
    #             else:
    #                 outlet_pressure = self.pro_well.outlet_fluid.P
    #                 outlet_temperature = self.pro_well.outlet_fluid.T
    #
    #             # Update surface
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #             print(self.surface.__class__.__name__)
    #             self.surface.power_plant.iterative_inj_pressure = test_p
    #             self.surface.inlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)
    #             self.surface.stream_interface()
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #     else:
    #         pass

    def pressure_finder(self, target_p):
        if self.reservoir.specs.bc_iteration['check_fracing']:
            test_p = 10000000

            while True:
                prev_test_p = test_p
                print(self.inj_well.inlet_fluid.P, self.inj_well.inlet_fluid.T, self.reservoir.mass_rate)
                print('problem', test_p, self.surface.outlet_fluid.T, target_p)

                self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
                self.inj_well.stream_interface()
                test_p += (target_p - self.inj_well.outlet_fluid.P)

                # Stop iteration if pressure change is below threshold
                if abs(test_p - prev_test_p) < 50000.0:
                    break

                # Update mass rate
                mass_rate = self.fracing_flow()
                if mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']:
                    self.reservoir.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate']
                else:
                    self.reservoir.mass_rate = mass_rate

                self.reservoir.inlet_fluid.updatePT(P=self.inj_well.outlet_fluid.P, T=self.inj_well.outlet_fluid.T)
                self.reservoir.stream_interface()
                self.inj_well.mass_rate = self.reservoir.mass_rate

                # Update production well
                self.pro_well.mass_rate = self.reservoir.mass_rate
                self.pro_well.inlet_fluid.updatePT(P=self.reservoir.outlet_fluid.P, T=self.reservoir.outlet_fluid.T)
                self.pro_well.stream_interface()

                # If pump exists, apply pump logic
                if self.pro_well_pump:
                    pump_dp = max(0.0, self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8 - self.pro_well.outlet_fluid.P)

                    for i in range(20):
                        self.pro_well_pump.mass_rate = self.reservoir.mass_rate
                        self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P + pump_dp, T=self.pro_well.outlet_fluid.T)
                        self.pro_well_pump.stream_interface()

                        print(i, self.pro_well_pump.outlet_fluid.P, self.pro_well_pump.inlet_fluid.P)

                        if pump_dp == 0.0 and self.pro_well_pump.outlet_fluid.P - 6000000.0 > 0:
                            break

                        if abs(6000000.0 - self.pro_well_pump.outlet_fluid.P) < 50000:
                            break

                        pump_dp += (6000000.0 - self.pro_well_pump.outlet_fluid.P)

                    outlet_pressure = self.pro_well_pump.outlet_fluid.P
                    outlet_temperature = self.pro_well_pump.outlet_fluid.T
                else:
                    outlet_pressure = self.pro_well.outlet_fluid.P
                    outlet_temperature = self.pro_well.outlet_fluid.T

                # Update surface
                self.surface.mass_rate = self.reservoir.mass_rate
                print(self.surface.__class__.__name__)
                self.surface.power_plant.iterative_inj_pressure = test_p
                self.surface.inlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)
                self.surface.stream_interface()
                self.surface.mass_rate = self.reservoir.mass_rate
        else:
            pass

    def _compute_dP_surface(self) -> float:
        """
        Computes the surface pressure difference (`dP_surface`).

        Formula:
            dP_surface = P_outlet_production_pump - P_inlet_injection_well - dP_pipe

        Returns:
            float: Surface pressure difference.
        """
        return self.unit.production_well_pump.outlet_fluid.P \
             - self.unit.injection_well.inlet_fluid.P \
             - self.unit.surface.dP_pipe
