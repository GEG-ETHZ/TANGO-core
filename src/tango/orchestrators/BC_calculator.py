import math
import pandas as pd

from tango.core.errors import P_SAT_ERR_TEST, CoolPropError, SaturationPressureError

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
        self.mass_rate_test = 0.1
        self.surface._m_dot_mult = 1
        self.surface.system_external = True
        self.tp = []
        self.time_step = 0

        self.ones_count = 0
        if self.specs.get('time', {}).get('type') == 'HotmapsDispatchDT':
            for component in self.specs['dt_list']:
                if component == 1:
                    self.ones_count += 1
                else:
                    break

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
                specs['averaging_window'],
                specs['bypass_file_generation'],
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
            - Supports HotmapsDispatchDT time type with list-based mass rate control.
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

            try:
                self.inj_well.update_inlet_fluid_state_PT(P=self.test_p, T=self.surface.outlet_fluid.T)
            except CoolPropError as cpe:
                raise type(cpe)(
                    f"`self.inj_well.update_inlet_fluid_state_PT` failed\n\t{cpe}",
                ) from cpe
            except Exception as err:
                raise type(err)(
                    "`self.inj_well.update_inlet_fluid_state_PT` failed"
                ) from err

            try:
                self.inj_well.stream_interface()
            except CoolPropError as cpe:
                raise type(cpe)(
                    f"`self.inj_well.stream_interface` failed\n\t{cpe}",
                ) from cpe
            except Exception as err:
                raise type(err)(
                    "`self.inj_well.stream_interface` failed"
                ) from err

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
                    if self.specs.get('time', {}).get('type') == 'HotmapsDispatchDT':
                        if self.time_step <= len(self.specs['dt_list']):
                            
                            if self.time_step <= self.ones_count:
                                mass_rate = self.reservoir.specs.mass_rate['value']
                                if (self.reservoir.specs.bc_iteration['check_fracing']):
                                    if (mass_rate > self.fracing_flow()):
                                        mass_rate = self.fracing_flow()
                            else:
                                if self.specs.get('bc_iteration', {}).get('controlled_power_generation') == 'yes':
                                    max_iterations = 200
                                    tolerance = 0.0001
                                    
                                    mass_rate_guess = self.mass_rate_test * max(
                                        self.processor.averaged_df.loc[
                                            self.time_step - 1 - self.ones_count,
                                            'value',
                                        ],
                                        self.specs["min_thermal_power"],
                                    ) / 1.0
                                    
                                    for iter_count in range(max_iterations):
                                        self.surface.mass_rate = mass_rate_guess * self.scaling_factor
                                        try:
                                            self.surface.inlet_fluid.updatePT(
                                                P=self.pro_well.outlet_fluid.P,
                                                T=self.pro_well.outlet_fluid.T,
                                            )
                                        except CoolPropError as cpe:
                                            raise type(cpe)(
                                                "`self.surface.inlet_fluid.updatePT` failed",
                                            ) from cpe
                                        except Exception as err:
                                            raise type(err)(
                                                "`self.surface.inlet_fluid.updatePT` failed"
                                            ) from err
                                        try:
                                            self.surface.stream_interface()
                                        except CoolPropError as cpe:
                                            raise type(cpe)(
                                                f"`self.surface.stream_interface` failed\n\t{cpe}"
                                            ) from cpe
                                        except Exception as err:
                                            raise type(err)(
                                                "`self.surface.stream_interface` failed"
                                            ) from err
                                        
                                        prev_thermal_power = 0.0
                                        for node_name, node in self.surface.power_plant.nodes.items():
                                            if self.surface.power_plant.config.get(node_name, {}).get('Subtype') == 'DH_component':
                                                prev_thermal_power += -node.Q.val/1000000.0
                                                # break
                                        
                                        if prev_thermal_power > 0.0001:  # Small positive threshold
                                            target_mass_rate = self.mass_rate_test * max(
                                                self.processor.averaged_df.loc[
                                                    self.time_step - 1 - self.ones_count,
                                                    "value",
                                                ],
                                                self.specs["min_thermal_power"],
                                            ) / prev_thermal_power
                                            
                                            if abs(target_mass_rate - mass_rate_guess) / max(abs(mass_rate_guess), 0.000001) < tolerance:
                                                mass_rate = target_mass_rate
                                                break
                                            
                                            # Update guess with relaxation
                                            mass_rate_guess = 0.5 * mass_rate_guess + 0.5 * target_mass_rate
                                        else:
                                            # Thermal power is negative or too small, increase mass_rate
                                            mass_rate_guess *= 1.5
                                    
                                    # If loop didn't converge, use the last guess
                                    if iter_count == max_iterations - 1:
                                        mass_rate = mass_rate_guess
                                    
                                else:
                                    mass_rate = self.fracing_flow()
                        else:
                            raise ValueError(
                                f"Time step {self.time_step} exceeds dt_list length "
                                    + f"{len(self.specs['dt_list'])}. Cannot access dt_list[{self.time_step - 1}]")
                    else:
                        if self.specs.get('bc_iteration', {}).get('controlled_power_generation') == 'yes':
                            max_iterations = 10
                            tolerance = 0.001
                            
                            mass_rate_guess = self.mass_rate_test * max(self.processor.averaged_df.loc[self.time_step - 1, 'value'], self.specs["min_thermal_power"]) / 1.0
                            
                            for iter_count in range(max_iterations):
                                self.surface.mass_rate = mass_rate_guess * self.scaling_factor
                                try:
                                    self.surface.inlet_fluid.updatePT(
                                        P=self.pro_well.outlet_fluid.P,
                                        T=self.pro_well.outlet_fluid.T,
                                    )
                                except CoolPropError as cpe:
                                    raise type(cpe)(
                                        "`self.surface.inlet_fluid.updatePT` failed",
                                    ) from cpe
                                except Exception as err:
                                    raise type(err)(
                                        "`self.surface.inlet_fluid.updatePT` failed"
                                    ) from err
                                try:
                                    self.surface.stream_interface()
                                except CoolPropError as cpe:
                                    raise type(cpe)(
                                        f"`self.surface.stream_interface` failed\n\t{cpe}",
                                    ) from cpe
                                except Exception as err:
                                    raise type(err)(
                                        "`self.surface.stream_interface` failed"
                                    ) from err
                                
                                prev_thermal_power = 0.0
                                for node_name, node in self.surface.power_plant.nodes.items():
                                    if self.surface.power_plant.config.get(node_name, {}).get('Subtype') == 'DH_component':
                                        prev_thermal_power = -node.Q.val/1000000.0
                                        break
                                
                                # Check if thermal power is positive
                                if prev_thermal_power > 0.001:
                                    target_mass_rate = self.mass_rate_test * max(
                                        self.processor.averaged_df.loc[self.time_step - 1, 'value'],
                                        self.specs["min_thermal_power"],
                                    ) / prev_thermal_power
                                    
                                    if abs(target_mass_rate - mass_rate_guess) / max(abs(mass_rate_guess), 0.001) < tolerance:
                                        mass_rate = target_mass_rate
                                        break
                                    
                                    # Update guess with relaxation
                                    mass_rate_guess = 0.7 * mass_rate_guess + 0.3 * target_mass_rate
                                else:
                                    # Thermal power is negative or too small, increase mass_rate
                                    mass_rate_guess *= 1.5
                            
                            # If loop didn't converge, use the last guess
                            if iter_count == max_iterations - 1:
                                mass_rate = mass_rate_guess
                        else:
                            mass_rate = self.fracing_flow()
                elif (self.reservoir.specs.mass_rate['type'] == 'manual'):
                    mass_rate = self.reservoir.specs.mass_rate['value']
                    if (self.reservoir.specs.bc_iteration['check_fracing']):
                        if (mass_rate > self.fracing_flow()):
                            mass_rate = self.fracing_flow()
                elif (self.reservoir.specs.mass_rate['type'] == 'manual_func'):
                    mass_rate = funcs[self.reservoir.specs.mass_rate['function']]
                    if (self.reservoir.specs.bc_iteration['check_fracing']):
                        if (mass_rate > self.fracing_flow()):
                            mass_rate = self.fracing_flow()

                if mass_rate >= self.reservoir.specs.bc_iteration['max_mass_rate']:
                    self.reservoir.mass_rate = self.reservoir.specs.bc_iteration['max_mass_rate'] / self.scaling_factor
                else:
                    self.reservoir.mass_rate = mass_rate / self.scaling_factor

                if (self.scaling_factor == 4.0):
                    self.reservoir.m_dot_mult = 1.0

            try:
                self.reservoir.inlet_fluid.updatePT(
                    P=self.inj_well.outlet_fluid.P,
                    T=self.inj_well.outlet_fluid.T,
                )
            except CoolPropError as cpe:
                raise type(cpe)(
                    "`self.reservoir.inlet_fluid.updatePT` failed",
                ) from cpe
            except Exception as err:
                raise type(err)(
                    "`self.reservoir.inlet_fluid.updatePT` failed"
                ) from err
            try:
                self.reservoir.stream_interface()
            except CoolPropError as cpe:
                raise type(cpe)(
                    f"`self.reservoir.stream_interface` failed\n\t{cpe}",
                ) from cpe
            except Exception as err:
                raise type(err)(
                    "`self.reservoir.stream_interface` failed"
                ) from err

            # Update production well
            print(
                "Updating production well to satisfy BCs",
                f"\tself.reservoir.mass_rate: {self.reservoir.mass_rate},",
                f"\tself.reservoir.outlet_fluid.P: {self.reservoir.outlet_fluid.P},",
                f"\tself.reservoir.outlet_fluid.T: {self.reservoir.outlet_fluid.T},",
                f"\tself.reservoir.outlet_fluid.H: {self.reservoir.outlet_fluid.H}",
                sep="\n",
            )
            self.pro_well.mass_rate = self.reservoir.mass_rate
            try:
                self.pro_well.inlet_fluid.updatePT(
                    P=self.reservoir.outlet_fluid.P,
                    T=self.reservoir.outlet_fluid.T,
                )
            except ValueError as cpe:
                if P_SAT_ERR_TEST.search(str(cpe)) is not None:
                    raise self.get_p_sat_err_for_pump(cpe) from cpe
                else:
                    raise cpe
            try:
                self.pro_well.stream_interface()
            except CoolPropError as cpe:
                raise type(cpe)(
                    f"\n\tUnable to solve production well stream interface\n\t{cpe}",
                ) from cpe
            except Exception as err:
                raise type(err)(
                    "\n\tUnable to solve production well stream interface"
                ) from err

            # If pump exists, apply pump logic
            if self.pro_well_pump:
                pump_dp_raw = (
                    self.pro_well_pump._specs.well_length * self.pro_well.outlet_fluid.rho * 9.8
                        - self.pro_well.outlet_fluid.P
                )
                pump_dp = max(
                    0.0,
                    pump_dp_raw,
                )

                self.pro_well_pump.mass_rate = self.reservoir.mass_rate
                # TODO: why is this hardcoded to 5? seems like this should really be a while loop
                num_dp_iter = 5
                for i in range(num_dp_iter):
                    try:
                        self.pro_well_pump.inlet_fluid.updatePT(
                            P=self.pro_well.outlet_fluid.P + pump_dp,
                            T=self.pro_well.outlet_fluid.T,
                        )
                    except CoolPropError as cpe:
                        if (P_SAT_ERR_TEST.search(str(cpe)) is not None) and (pump_dp != 0.0):
                            if i == num_dp_iter - 1:
                                # if it's the last iteration, this error will not be solved
                                raise SaturationPressureError(
                                    "Error in final iteration of pump pressure delta calculation",
                                ) from cpe
                            # increment `pump_dp` because it may prevent this error in the next iter
                            pump_dp += (
                                self.surface.specs.target_extraction_pressure
                                    - self.pro_well_pump.outlet_fluid.P
                            )
                            continue  # to the next iteration
                        else:
                            # if `pump_dp` is zero, this will not be solved in the next iteration
                            if (P_SAT_ERR_TEST.search(str(cpe)) is not None):
                                raise self.get_p_sat_err_for_pump(cpe) from cpe
                            else:
                                raise cpe

                    # Solve pump in streamwise direction
                    try:
                        self.pro_well_pump.stream_interface()
                    except CoolPropError as cpe:
                        raise type(cpe)(
                            f"\n\tProduction well pump `stream_interface` calculation failed\n\t{cpe}",
                        ) from cpe
                    except Exception as err:
                        raise type(err)(
                            "\n\tProduction well pump `stream_interface` calculation failed"
                        ) from err

                    if (
                        (pump_dp == 0.0)
                        and (
                            self.pro_well_pump.outlet_fluid.P
                                - self.surface.specs.target_extraction_pressure > 0
                        )
                    ):
                        # pump has exceeded target extraction pressure
                        break

                    pump_dp += (
                        self.surface.specs.target_extraction_pressure
                            - self.pro_well_pump.outlet_fluid.P
                    )

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
            try:
                self.surface.inlet_fluid.updatePT(P=outlet_pressure, T=outlet_temperature)
            except CoolPropError as cpe:
                raise type(cpe)(
                    "`self.surface.inlet_fluid.updatePT` failed"
                ) from cpe
            except Exception as err:
                raise type(err)(
                    "`self.surface.inlet_fluid.updatePT` failed"
                ) from err
            try:
                self.surface.stream_interface()
            except CoolPropError as cpe:
                raise type(cpe)(
                    f"`self.surface.stream_interface` failed\n\t{cpe}"
                ) from cpe
            except Exception as err:
                raise type(err)(
                    "`self.surface.stream_interface` failed"
                ) from err
            self.mass_rate_test = self.surface.mass_rate

            if prev_test_p is not None and prev_mass_rate is not None and prev_inlet_p is not None:
                rel_tol_test_p = abs(self.test_p - prev_test_p) / max(abs(prev_test_p), 1e-8)
                rel_tol_mass_rate = abs(self.inj_well.mass_rate - prev_mass_rate) / max(abs(prev_mass_rate), 1e-8)
                rel_tol_inlet_p = abs(self.inj_well.inlet_fluid.P - prev_inlet_p) / max(abs(prev_inlet_p), 1e-8)

                if (
                        (rel_tol_test_p < tolerance)
                        and (rel_tol_mass_rate < tolerance)
                        and (rel_tol_inlet_p < tolerance)
                    ):
                    converged = True
                    break

            prev_test_p = self.test_p
            prev_mass_rate = self.inj_well.mass_rate
            prev_inlet_p = self.inj_well.inlet_fluid.P

        if not converged:
            raise RuntimeError(
                f"Convergence not reached after {iterations} iterations. "
                f"Final relative differences: test_p={rel_tol_test_p:.6f}, "
                f"mass_rate={rel_tol_mass_rate:.6f}, inlet_p={rel_tol_inlet_p:.6f}",
            )

        if self.pro_well_pump:
            self.surface.prod_pump_aux = -(
                self.pro_well_pump.inlet_fluid.H
                    - self.pro_well.outlet_fluid.H
            ) * self.pro_well_pump.mass_rate
            self.surface.prod_pump_w_list.append(self.surface.prod_pump_aux)

    def get_p_sat_err_for_pump(self, err):
        """Get formatted saturation pressure error for pump inlet

        # Arguments
        - `err`: original error from CoolProp
        """
        return PumpInletFlashError(
            f"""\n\tProduction well pump inlet is at vaporization threshold.
        Original CoolProp message:
        "{err}"
        """,  # noqa: E501
        # TODO: make this conditional based on whether mass flow rate is manual or automatic
        # - reduce mass flow rate (note: this will reduce total power output and should only be
        #     used if the other steps don't work)
        # TODO:
        # make sure the system is robust enough that this recommendation will work
        # `- try removing the production well pump because the thermosiphon effect is sufficient`
        # TODO: propagate this out so mass_rate type is accessible
        # ```
        # Troubleshooting steps:
        # - check for flow restrictions
        # - if mass_rate type is manual, reduce mass flow rate (note: this will
        #   reduce total power output and should only be used if the other steps don't work)
        # ```
        )


class PumpInletFlashError(SaturationPressureError):
    """Error indicating that liquid is hitting saturating threshold at pump inlet"""

    pass


class PowerReader:
    def __init__(self):
        self.averaged_df = None

    def process_geothermal_data(self, input_file, output_file, window_size, bypass_processing):
        """
        Extract geothermal data, handle duplicates, and create averaged output.
        
        Args:
            input_file: Input Excel file path
            output_file: Output Excel file path
            window_size: Window size for averaging
            bypass_processing: If True, skip all processing and just load existing output_file
        """
        if bypass_processing == 'yes':
            print(f"Bypassing processing - loading existing file: {output_file}")
            self.averaged_df = pd.read_excel(output_file)
            print(f"Loaded {len(self.averaged_df)} rows from existing file")
            return self.averaged_df
        
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
