import math

class FlowRateCalculator():
    def __init__(self, injection_well_class, production_well_class, production_well_pump_class, reservoir_class, surface_class):
        self.inj_well = injection_well_class
        self.pro_well = production_well_class
        self.pro_well_pump = production_well_pump_class
        self.reservoir = reservoir_class
        self.surface = surface_class
        self.mass_rate_test = 50.0

    def prr(self):
        pass
        # print(self.inj_well.__class__.__name__)
        # print(self.pro_well.__class__.__name__)
        # print(self.pro_well_pump.__class__.__name__)
        # print(self.reservoir.__class__.__name__)
        # print(self.surface.__class__.__name__)

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

    def pressure_finder(self, target_p):
        if (self.reservoir.specs.well_pattern == 'DOUBLET'):
            self.scaling_factor = 1.0
        elif (self.reservoir.specs.well_pattern == 'INVERTED_5SPOT'):
            self.scaling_factor = 4.0
        else:
            raise ValueError(f"well_pattern: {self.reservoir.specs.well_pattern} is not supported.")
        print(self.scaling_factor)
        # print('mass_rate_', self.reservoir.specs.mass_rate)
        if self.reservoir.specs.bc_iteration['check_fracing']:
            test_p = 10000000
            iterations = 8 if self.pro_well_pump else 7

            print('self.surface.mass_rate', self.surface.mass_rate)

            for _ in range(iterations):
                # print(_, self.inj_well.inlet_fluid.P, self.inj_well.inlet_fluid.T, self.reservoir.mass_rate)
                # print('problem', test_p, self.surface.outlet_fluid.T, target_p)
                # print(_, self.surface.mass_rate, '1')
                # self.inj_well.mass_rate = self.reservoir.mass_rate
                # self.inj_well.mass_rate = self.surface.mass_rate
                self.inj_well.mass_rate = self.mass_rate_test
                print(_, self.inj_well.mass_rate, '1 inj', self.inj_well.inlet_fluid.P, self.inj_well.inlet_fluid.T)
                self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
                self.inj_well.stream_interface()
                print(_, self.inj_well.mass_rate, '2 inj')
                test_p += (target_p - self.inj_well.outlet_fluid.P)

                # Update mass rate
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

                print(_, self.reservoir.mass_rate, '1 res')
                self.reservoir.inlet_fluid.updatePT(P=self.inj_well.outlet_fluid.P, T=self.inj_well.outlet_fluid.T)
                self.reservoir.stream_interface()
                # self.inj_well.mass_rate = self.reservoir.mass_rate
                print(_, self.reservoir.mass_rate, '2 res')

                # Update production well
                self.pro_well.mass_rate = self.reservoir.mass_rate
                print(_, self.pro_well.mass_rate, '1 pro_well')
                self.pro_well.inlet_fluid.updatePT(P=self.reservoir.outlet_fluid.P, T=self.reservoir.outlet_fluid.T)
                self.pro_well.stream_interface()
                print(_, self.pro_well.mass_rate, '2 pro_well')

                # If pump exists, apply pump logic
                if self.pro_well_pump:
                    pump_dp = max(0.0, self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8 - self.pro_well.outlet_fluid.P)

                    for i in range(5):
                        self.pro_well_pump.mass_rate = self.reservoir.mass_rate
                        self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P + pump_dp, T=self.pro_well.outlet_fluid.T)
                        self.pro_well_pump.stream_interface()

                        print(i, self.pro_well_pump.outlet_fluid.P, self.pro_well_pump.inlet_fluid.P)

                        if pump_dp == 0.0 and self.pro_well_pump.outlet_fluid.P - 7000000.0 > 0:
                            break

                        pump_dp += (7000000.0 - self.pro_well_pump.outlet_fluid.P)

                    outlet_pressure = self.pro_well_pump.outlet_fluid.P
                    outlet_temperature = self.pro_well_pump.outlet_fluid.T
                else:
                    outlet_pressure = self.pro_well.outlet_fluid.P
                    outlet_temperature = self.pro_well.outlet_fluid.T

                # Update surface
                self.surface.mass_rate = self.reservoir.mass_rate * self.scaling_factor
                print(_, self.surface.mass_rate, '1 surface')
                self.surface.power_plant.iterative_inj_pressure = test_p
                self.surface.inlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)
                self.surface.stream_interface()
                print(_, self.surface.mass_rate, '2 surface', self.surface.outlet_fluid.P, self.surface.outlet_fluid.T)
                # print(self.pro_well.specs.mass_flow_rate)
                self.mass_rate_test = self.surface.mass_rate
                # self.surface.mass_rate = self.reservoir.mass_rate
                # print(_, self.inj_well.inlet_fluid.P, self.inj_well.inlet_fluid.T, self.reservoir.mass_rate)
                # print('problem', test_p, self.surface.outlet_fluid.T, target_p)
                # print(_, self.inj_well.mass_rate, self.reservoir.mass_rate, self.pro_well.mass_rate, self.pro_well_pump.mass_rate, self.surface.mass_rate)
            if self.pro_well_pump:
                self.surface.prod_pump_aux = -(self.pro_well_pump.inlet_fluid.H - self.pro_well.outlet_fluid.H) * self.pro_well_pump.mass_rate
                self.surface.prod_pump_w_list.append(self.surface.prod_pump_aux)
                # print('list', self.surface.prod_pump_w_list)
        else:
            pass

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
    #                 for i in range(20):
    #                     self.pro_well_pump.mass_rate = self.reservoir.mass_rate
    #                     self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P + pump_dp, T=self.pro_well.outlet_fluid.T)
    #                     self.pro_well_pump.stream_interface()
    #
    #                     print(i, self.pro_well_pump.outlet_fluid.P, self.pro_well_pump.inlet_fluid.P)
    #
    #                     if pump_dp == 0.0 and self.pro_well_pump.outlet_fluid.P - 7000000.0 > 0:
    #                         break
    #
    #                     if abs(7000000.0 - self.pro_well_pump.outlet_fluid.P) < 50000:
    #                         break
    #
    #                     pump_dp += (7000000.0 - self.pro_well_pump.outlet_fluid.P)
    #
    #                 outlet_pressure = self.pro_well_pump.outlet_fluid.P
    #                 outlet_temperature = self.pro_well_pump.outlet_fluid.T
    #             else:
    #                 outlet_pressure = self.pro_well.outlet_fluid.P
    #                 outlet_temperature = self.pro_well.outlet_fluid.T
    #
    #             print('pro_well', self.pro_well.outlet_fluid.P, self.pro_well.outlet_fluid.T)
    #             print('pro_well_pum', self.pro_well_pump.inlet_fluid.P, self.pro_well_pump.inlet_fluid.T)
    #             # Update surface
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #             print(self.surface.__class__.__name__)
    #             self.surface.power_plant.iterative_inj_pressure = test_p
    #             self.surface.inlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)
    #             self.surface.stream_interface()
    #             self.surface.mass_rate = self.reservoir.mass_rate
    #         self.surface.prod_pump_aux = -(self.pro_well_pump.inlet_fluid.H - self.pro_well.outlet_fluid.H) * self.pro_well_pump.mass_rate
    #         self.surface.prod_pump_list.append(self.surface.prod_pump_aux)
    #         print('list', self.surface.prod_pump_list)
    #     else:
    #         pass

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
