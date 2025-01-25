

class Flow_rate_calculator():
    def __init__(self, well_class):
        self.well = well_class

    def prr(self):
        print(self.well.__class__.__name__)
        print(self.well.outlet_fluid.T - 273.15, self.well.outlet_fluid.P/1000000)
        # self.well.update_inlet_fluid_state_PT(P=6000000)
        self.well.mass_rate = 40
        self.well.stream_interface()
        print(self.well.outlet_fluid.P)
        # print(self.well.inlet_fluid.P)
