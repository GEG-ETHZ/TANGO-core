import math
import pandas as pd

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
    def __init__(self, specs, injection_well_class, production_well_class, production_well_pump_class, reservoir_class, surface_class):
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
        self.specs = specs
        self.inj_well = injection_well_class
        self.pro_well = production_well_class
        self.pro_well_pump = production_well_pump_class
        self.reservoir = reservoir_class
        self.surface = surface_class
        self.mass_rate_test = 50.0
        self.surface._m_dot_mult = 1
        self.surface.system_external = True
        self.tp = []
        self.time_step = 0

        if (self.reservoir.specs.mass_rate['type'] == 'manual'):
            self.test_p = self.surface.specs.injection_pressure
        else:
            if (self.surface._fluid_name == 'CO2'):
                self.test_p = 9100000
            else:
                self.test_p = 7000000.0

        if (self.reservoir.specs.well_pattern == 'DOUBLET'):
            self.scaling_factor = 1.0
        elif (self.reservoir.specs.well_pattern == 'INVERTED_5SPOT'):
            self.scaling_factor = 4.0
        else:
            raise ValueError(f"well_pattern: {self.reservoir.specs.well_pattern} is not supported.")

        if self.specs.get('bc_iteration', {}).get('controlled_power_generation') == 'yes':
            self.processor = PowerReader()
            self.processor.process_geothermal_data(
                specs['power_raw_data'],
                specs['power_avg'],
                specs['averaging_window']
            )

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

    def iterator(self, target_p, inlet_flow, funcs):
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
        self.time_step += 1
        if (self.surface.__class__.__name__ == 'SurfaceUnitFlexiblePP'):
            self.surface.power_plant.funcs = funcs

        iterations = 200

        tolerance = 0.0001
        prev_test_p = None
        prev_mass_rate = None
        prev_inlet_p = None
        converged = False

        for _ in range(iterations):

            # Update injection well
            if(self.reservoir.__class__.__name__ == 'ReservoirFileReaderUnit'):
                self.inj_well.mass_rate = inlet_flow
            else:
                self.inj_well.mass_rate = self.mass_rate_test
            self.inj_well.update_inlet_fluid_state_PT(P=self.test_p, T=self.surface.outlet_fluid.T)
            self.inj_well.stream_interface()

            if (self.reservoir.specs.mass_rate['type'] != 'manual'):
                self.test_p += (target_p - self.inj_well.outlet_fluid.P)
            else:
                if (self.inj_well.outlet_fluid.P < target_p):
                    pass
                else:
                    self.test_p += (target_p - self.inj_well.outlet_fluid.P)

            if hasattr(self.surface, 'condensation_pressure'):
                self.test_p = max(self.test_p, self.surface.condensation_pressure)

            if(self.reservoir.__class__.__name__ != 'ReservoirFileReaderUnit'):
                # Update reservoir
                if (self.reservoir.specs.mass_rate['type'] == 'automatic'):
                    if self.specs.get('bc_iteration', {}).get('controlled_power_generation') == 'yes':
                        for node_name, node in self.surface.power_plant.nodes.items():
                            if self.surface.power_plant.config.get(node_name, {}).get('Subtype') == 'DH_component':
                                print(f'{node_name} (DH_component) Q: {node.Q.val} W')
                                prev_thermal_power = -node.Q.val/1000000.0
                        mass_rate = self.mass_rate_test * self.processor.averaged_df.loc[self.time_step - 1, 'value'] / prev_thermal_power * 30
                    else:
                        mass_rate = self.fracing_flow()
                elif (self.reservoir.specs.mass_rate['type'] == 'manual'):
                    mass_rate = self.reservoir.specs.mass_rate['value']
                    if (self.reservoir.specs.bc_iteration['check_fracing']):
                        if (mass_rate > self.fracing_flow()):
                            mass_rate = self.fracing_flow()
                elif (self.reservoir.specs.mass_rate['type'] == 'manual_func'):
                    mass_rate = funcs[self.reservoir.specs.mass_rate['function']] # funcs[self.reservoir.specs.mass_rate['function']]
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
            pro_P_test = max(self.reservoir.outlet_fluid.P, self.pro_well._specs.well_length * 900 * 9.8)

            if pro_P_test == self.pro_well._specs.well_length * self.reservoir.outlet_fluid.rho * 9.8:
                self.test_p += -(self.reservoir.outlet_fluid.P - self.pro_well._specs.well_length * 900 * 9.8)

            self.pro_well.mass_rate = self.reservoir.mass_rate
            self.pro_well.inlet_fluid.updatePT(P=pro_P_test, T=self.reservoir.outlet_fluid.T)
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
                self.surface.power_plant.iterative_inj_pressure = self.test_p
            else:
                self.surface.iterative_inj_pressure = self.test_p
            self.surface.inlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)
            self.surface.stream_interface()
            self.mass_rate_test = self.surface.mass_rate

            if prev_test_p is not None and prev_mass_rate is not None and prev_inlet_p is not None:
                rel_tol_test_p = abs(self.test_p - prev_test_p) / max(abs(prev_test_p), 1e-8)
                rel_tol_mass_rate = abs(self.inj_well.mass_rate - prev_mass_rate) / max(abs(prev_mass_rate), 1e-8)
                rel_tol_inlet_p = abs(self.inj_well.inlet_fluid.P - prev_inlet_p) / max(abs(prev_inlet_p), 1e-8)

                if rel_tol_test_p < tolerance and rel_tol_mass_rate < tolerance and rel_tol_inlet_p < tolerance:
                    converged = True
                    break

            prev_test_p = self.test_p
            prev_mass_rate = self.inj_well.mass_rate
            prev_inlet_p = self.inj_well.inlet_fluid.P

        if not converged:
            raise RuntimeError(
                f"Convergence not reached after {iterations} iterations. "
                f"Final relative differences: test_p={rel_tol_test_p:.6f}, "
                f"mass_rate={rel_tol_mass_rate:.6f}, inlet_p={rel_tol_inlet_p:.6f}"
            )

        if self.pro_well_pump:
            self.surface.prod_pump_aux = -(self.pro_well_pump.inlet_fluid.H - self.pro_well.outlet_fluid.H) * self.pro_well_pump.mass_rate
            self.surface.prod_pump_w_list.append(self.surface.prod_pump_aux)


class PowerReader:
    def __init__(self):
        self.averaged_df = None

    def process_geothermal_data(self, input_file, output_file, window_size):
        """
        Extract geothermal data, handle duplicates, and create averaged output.
        """
        print("Reading Excel file...")
        df = pd.read_excel(input_file)

        geothermal_filter = (df['heat generator'].str.contains('geothermal', case=False, na=False)) & \
                           (df['topic'].str.contains('Thermal Power Energymix', case=False, na=False))
        geothermal_data = df[geothermal_filter]

        print(f"Found {len(geothermal_data)} rows with geothermal data")
        print(f"Unique time values: {geothermal_data['time'].nunique()}")
        print(f"Time range: {geothermal_data['time'].min()} to {geothermal_data['time'].max()}")

        duplicate_times = geothermal_data[geothermal_data.duplicated(subset=['time'], keep=False)]
        if len(duplicate_times) > 0:
            print(f"Found {len(duplicate_times)} rows with duplicate time values")
            print("\nSample duplicate entries:")
            print(duplicate_times[['time', 'topic', 'heat generator', 'value']].head(10))
            print("\nRemoving duplicates (keeping first occurrence)...")
            geothermal_data = geothermal_data.drop_duplicates(subset=['time'], keep='first')
            print(f"After removing duplicates: {len(geothermal_data)} rows")

        geothermal_data = geothermal_data.sort_values('time').reset_index(drop=True)
        print(f"Calculating {window_size}-point average...")

        averaged_rows = []
        for i in range(0, len(geothermal_data), window_size):
            chunk = geothermal_data.iloc[i:i+window_size]
            if len(chunk) > 0:
                avg_row = {}
                for col in geothermal_data.columns:
                    if col == 'value':
                        avg_row[col] = chunk[col].mean()
                    elif col == 'time':
                        avg_row[col] = chunk[col].iloc[len(chunk)//2]
                    else:
                        avg_row[col] = chunk[col].iloc[0]
                averaged_rows.append(avg_row)

        self.averaged_df = pd.DataFrame(averaged_rows)
        self.averaged_df.to_excel(output_file, index=False)
        print(f"Averaged data saved to: {output_file} ({len(self.averaged_df)} rows)")

        return self.averaged_df
