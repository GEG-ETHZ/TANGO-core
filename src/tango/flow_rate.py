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
    #         test_p = 4000000
    #         for _ in range(5):
    #             mass_rate = self.fracing_flow()
    #             if (mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']):
    #                 self.well.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate']
    #             else:
    #                 self.well.mass_rate = self.fracing_flow()
    #             self.well.update_inlet_fluid_state_PT(P=test_p)
    #             self.well.stream_interface()
    #             test_p = test_p + (target_p - self.well.outlet_fluid.P)
    #             # print(self.well.outlet_fluid.P)
    #     else:
    #         pass

    def pressure_finder(self, target_p):
        if (self.reservoir.specs.bc_iteration['check_fracing']):
            test_p = 10000000

            for _ in range(3):

                self.inj_well.update_inlet_fluid_state_PT(P=test_p, T=self.surface.outlet_fluid.T)
                self.inj_well.stream_interface()
                test_p = test_p + (target_p - self.inj_well.outlet_fluid.P) # new pressure

                ##################################################################################################

                mass_rate = self.fracing_flow() # new mass rate
                if (mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']):
                    self.reservoir.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate']
                else:
                    self.reservoir.mass_rate = self.fracing_flow()
                self.reservoir.inlet_fluid.updatePT(P=self.inj_well.outlet_fluid.P, T=self.inj_well.outlet_fluid.T)
                self.reservoir.stream_interface() # with new mass rate

                self.inj_well.mass_rate = self.reservoir.mass_rate


                ##################################################################################################

                self.pro_well.mass_rate = self.reservoir.mass_rate
                self.pro_well.inlet_fluid.updatePT(P=self.reservoir.outlet_fluid.P, T=self.reservoir.outlet_fluid.T)
                self.pro_well.stream_interface()

                ##################################################################################################

                self.pro_well_pump.mass_rate = self.reservoir.mass_rate
                self.pro_well_pump.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P, T=self.pro_well.outlet_fluid.T)
                self.pro_well_pump.stream_interface()

                ##################################################################################################

                self.surface.mass_rate = self.reservoir.mass_rate
                self.surface.iterative_inj_pressure = test_p
                self.surface.inlet_fluid.updatePT(P=self.pro_well.outlet_fluid.P, T=self.pro_well.outlet_fluid.T)
                self.surface.stream_interface() # with new inlet P, T, and m. Its outlet was already set!

                self.surface.mass_rate = self.reservoir.mass_rate

        else:
            pass



