"""
Error methods/functions for use in src/tango/workflows/native_workflow.py
"""

from dataclasses import dataclass
from typing import cast

import numpy as np
import re

from tango.core.errors import (
    CoolPropError,
    ComponentError,
    ProPumpInletFlashError,
    SaturationPressureError,
    P_SAT_ERR_TEST,
)
from tango.core.constants import GRAVITY_ACCELERATION
from tango.core.abstracts.unit import SimplePressureDrop
from tango.core.fluidstate import FluidState
from tango.units.native.well import WellUnitNative
from tango.units.native.surface import SurfaceUnitNative

# define strings for frequently used dict keys to reduce likelihood of typos
injection_well = "injection_well"
reservoir = "reservoir"
production_well = "production_well"
production_well_pump = "production_well_pump"
production_well_upper = "production_well_upper"
production_well_lower = "production_well_lower"
surface = "surface"
ordered_subsurf_outlets = [
    injection_well,
    reservoir,
    production_well,
]
ordered_surface_outlets = [
    production_well_pump,  # included here because outlet is at surface
    surface,
]


@dataclass
class InletBCs:
    """Class for storing pressure and temperature used as inlet BCs

    # Attributes
    # - `p`: pressure at inlet for current module
    # - `te`: temperature at inlet for current module
    """

    p: float
    te: float


def get_dp_and_flow_res(
    unit,
    p_simple_inst_dict: dict[str, SimplePressureDrop],
    mdot: float,
    state_ad_hoc: FluidState
) -> tuple[dict[str, float], dict[str, float], dict[str, InletBCs], dict[str, InletBCs | None]]:
    """Get module-wise estimated pressure drop for a given mass flow rate

    # Returns
    # - estimated pressure drop for each module
    # - optimal inlet BCs for each module to check for individual model excess flow resistance
    # - minimal inlet BCs for each module to avoid saturation
    """
    # dictionary of module names and corresponding pressure drops [Pa]
    dp_dict: dict[str, float] = {}

    flow_res_dict: dict[str, float] = {}

    # dictionary of module names and corresponding optimal BCs to use in calculating outlet pressure
    opt_inlet_bcs: dict[str, InletBCs] = {}
    # dictionary of module names and corresponding BCs from whatever portion of TANGO successfully
    # simulated
    act_inlet_bcs: dict[str, InletBCs | None] = {}

    # NOTE: these values will be approximate because they're not using numerical simulations, but
    # they'll be guaranteed to work even if the simulation has failed before completing the loop
    # Also, they'll work reasonably well for liquids with minimal property dependence on pressure and
    # may not work as well for gases
    #
    # Determine temperatue and pressure to be used in calculating properties for calculating dP for each
    # module in TANGO loop
    for k, v in p_simple_inst_dict.items():
        if k == injection_well:
            te = v.fluid_state_init.T
            # averaged over inlet and outlet for property calculations
            p = 0.5 * (
                v.fluid_state_init.P
                    + unit.reservoir.specs.hydro_static_pressure
            )
            dp_dict[k] = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            flow_res_dict[k] = v.get_flow_res_per_dx(
                te=te,
                p=p,
                mdot=mdot,
            )
            opt_inlet_bcs[k] = InletBCs(
                te=te,
                # this gets updated after an iteration, but if it fails before one iteration is
                # complete, then there's not a clear best choice for assuming an optimum inlet
                # pressure here
                p=v.fluid_state_init.P
            )
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as _err:
                act_inlet_bcs[k] = None

        ### for all other cases, the temperature and pressure must be approximated because the
        # state may not yet be available

        elif k == reservoir:
            depth_for_temp = p_simple_inst_dict[k].specs.reservoir_depth
            # this overestimates temperature for pressure drop calculation but is
            # reasonable for saturation pressure calclulation
            te = (
                p_simple_inst_dict[surface].specs.surface_temperature
                    + (p_simple_inst_dict[k].specs.thermal_gradient * depth_for_temp)
            )
            # NOTE: This assumes minimal pressure drop in the injection well.
            # This assumption is reasonable for calculating fluid properties
            # of fluids with viscosity and density that are pressure insensitive.
            p = unit.reservoir.specs.hydro_static_pressure
            dp_dict[k] = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            # reservoir is intentionally left out because we want to prioritize having the user adjust pipe
            # parameters
            # flow_res_dict[k] = v.get_flow_res_per_dx(
            #     te=te,
            #     p=p,
            #     mdot=mdot,
            # )
            opt_inlet_bcs[k] = InletBCs(
                te=te,
                # this assumes the injection well head pressure and resistances are high enough and
                # low enough, respectively, to feed the reservoir its maximum allowed inlet pressure
                p=unit.reservoir.specs.hydro_static_pressure * (
                    1.0 + unit.reservoir.specs.over_pressure_percentage
                )
            )
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as err:
                act_inlet_bcs[k] = None
        elif k in (production_well, production_well_lower):
            # NOTE: assumes that production well bottom is always at same depth as injection
            # well bottom
            depth_for_temp = p_simple_inst_dict['injection_well']._well_length
            # NOTE: this assumes fluid temperature is equilibrated with reservoir and that
            # reservoir temperature has not decreased over time
            te = (
                p_simple_inst_dict[surface].specs.surface_temperature
                    + (p_simple_inst_dict['production_well']._specs.thermal_gradient * depth_for_temp)
            )
            # NOTE: This assumes no pressure drop in the injection well or reservoir, which
            # will overestimate the pressure. This assumption is reasonable for hydrothermal
            # systems but needs reassessment for CPG systems.
            # averaged over inlet (reservoir depth) and outlet (production_well_pump length) for property
            # calculation
            p = 0.5 * (
                unit.reservoir.specs.hydro_static_pressure
                    + p_simple_inst_dict['production_well_pump']._well_length * GRAVITY_ACCELERATION
                        * state_ad_hoc.rho
            )
            dp_dict[k] = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            flow_res_dict[k] = v.get_flow_res_per_dx(
                te=te,
                p=p,
                mdot=mdot,
            )
            opt_inlet_bcs[k] = InletBCs(
                te=te,
                # this assumes the injection well head pressure and resistances are high enough and
                # low enough, respectively, to feed the reservoir its maximum allowed inlet pressure
                p=unit.reservoir.specs.hydro_static_pressure * (
                    1.0 + unit.reservoir.specs.over_pressure_percentage
                )
            )
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as err:
                act_inlet_bcs[k] = None
        elif k in (production_well_pump, production_well_upper):
            # NOTE: this assumes no temperature decrease has occurred from the reservoir
            # temperature, which will overestimate the actual temperature, and it's a good
            # idea to revisit the assumption in the future
            # This also assumes that injection well length and reservoir length are the same, which is
            # usually the case but may need future revision
            depth_for_temp = p_simple_inst_dict['injection_well']._well_length
            te = (
                p_simple_inst_dict[surface].specs.surface_temperature
                    + (p_simple_inst_dict['production_well_pump']._specs.thermal_gradient * depth_for_temp)
            )
            # averaged over inlet (production_well_pump length) and outlet (surface)
            p = 0.5 * (
                unit.reservoir.specs.hydro_static_pressure
            )
            dp_dict[k] = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            flow_res_dict[k] = v.get_flow_res_per_dx(
                te=te,
                p=p,
                mdot=mdot,
            )
            opt_inlet_bcs[k] = InletBCs(
                p=unit.reservoir.specs.hydro_static_pressure - (
                    unit.production_well.specs['well_length']
                        - unit.production_well_pump.specs['well_length']
                ) * GRAVITY_ACCELERATION * state_ad_hoc.rho,
                te=te,
            )
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as _err:
                act_inlet_bcs[k] = None
        elif k == surface:
            # NOTE: this assumes no temperature decrease has occurred from the reservoir
            # temperature, which will overestimate the actual temperature, and it's a good
            # idea to revisit the assumption in the future
            depth = p_simple_inst_dict[production_well_pump]._well_length
            te = (
                p_simple_inst_dict[surface].specs.surface_temperature
                    + (p_simple_inst_dict[reservoir].specs.thermal_gradient * depth)
            )
            p = unit.reservoir.specs.hydro_static_pressure
            p_out_pro_well_pump = unit.production_well_pump.specs["target_extraction_pressure"]
            dp_dict[k] = v.get_dp_simple(
                te=te,
                p=p,
                mdot=mdot,
            )
            flow_res_dict[k] = v.get_flow_res_per_dx(
                te=te,
                p=p,
                mdot=mdot,
            )
            opt_inlet_bcs[surface] = InletBCs(p=p_out_pro_well_pump, te=te)
            del te, p
            try:
                act_inlet_bcs[k] = InletBCs(
                    te=v.inlet_fluid.T,
                    # this gets updated after an iteration, but if it fails before one iteration is
                    # complete, then there's not a clear best choice for assuming an optimum inlet
                    # pressure here
                    p=v.inlet_fluid.P
                )
            except Exception as _err:
                act_inlet_bcs[k] = None
        else:
            # should be unreachable
            raise ValueError(f"Invalid k: {k}.  Report this to the TANGO team.")

    return dp_dict, flow_res_dict, opt_inlet_bcs, act_inlet_bcs


def handle_convergence_err(self, cpe: CoolPropError):
    """Handle convergence error to provide troubleshooting context"""
    unit = self.orchestrator.unit
    # dictionary of module names and corresponding instances that inhherit `SimplePressureDrop`
    p_simple_inst_dict: dict[str, SimplePressureDrop] = {
        k: v for (k, v) in unit.__dict__.items()
        if isinstance(v, SimplePressureDrop)
    }

    # NOTE: check if `self.specs['schedule']['mass_flow_rate']` will work for a case where
    # `self.specs['schedule']['mass_rate']['type']` is not "manual"
    mdot = self.specs["schedule"]["mass_flow_rate"]

    # fractional margin above saturation pressure at which error is triggered
    # NOTE: this should eventually be configurable
    p_sat_frac_margin = 1.0

    # state for ad hoc calculations
    state_ad_hoc = FluidState.copy(
        p_simple_inst_dict[injection_well].fluid_state_init,
    )
    if not state_ad_hoc.rho > 0.0:
        # should not be reachable
        raise ValueError(
            "`state_ad_hoc` should have been updated.  Report this error to TANGO team.",
        )

    check_complex_err(
        unit,
        p_simple_inst_dict,
        mdot,
        state_ad_hoc,
        cpe,
        p_sat_frac_margin,
    )


def check_complex_err(
    unit_search,
    p_simple_inst_dict: dict[str, SimplePressureDrop],
    mdot: float,
    state_ad_hoc: FluidState,
    cpe: CoolPropError,
    p_sat_frac_margin: float,
):
    """Check for errors that involve more than one component -- e.g. production well pump inlet flashing
    because of flow restriction in injection well

    # Arguments
    #   saturation pressure
    # - `mdot`: mass flow rate [kg/s]

    """
    if not isinstance(cpe, SaturationPressureError) and P_SAT_ERR_TEST.search(str(cpe)) is not None:
        # Convert CoolPropError to SaturationPressureError while preserving context
        try:
            raise SaturationPressureError(cpe) from cpe
        except SaturationPressureError as spe:
            cpe = spe

    # module names and corresponding pipe diameters
    diameters: dict[str, float] = {}
    for k, v in p_simple_inst_dict.items():
        if k == injection_well:
            diameters[k] = cast(WellUnitNative, v)._specs.diameter
        elif k == reservoir:
            continue
        elif k in (
            production_well,
            production_well_pump,
            production_well_upper,
            production_well_lower,
        ):
            diameters[k] = cast(WellUnitNative, v)._specs.diameter
        elif k == surface:
            diameters[k] = cast(SurfaceUnitNative, v).specs.pipe_diameter
        else:
            # should be unreachable
            raise ValueError(f"Unexpected key: {k}. Report this to the TANGO team")

    d_max_in_sys = max(diameters.values())

    # determine component in which CoolProp error occurred
    if f"unit: {injection_well}" in str(cpe):
        cp_err_inlet = injection_well
    elif f"unit: {production_well_pump}" in str(
        cpe,
    ) or f"unit: {production_well_upper}" in str(cpe):
        # must be checked before "production_well"
        cp_err_inlet = production_well_pump
    elif f"unit: {production_well}" in str(cpe):
        cp_err_inlet = production_well
    elif f"unit: {reservoir}" in str(cpe):
        cp_err_inlet = reservoir
    elif isinstance(cpe, ProPumpInletFlashError):
        cp_err_inlet = production_well
    elif f"unit: {surface}" in str(cpe):
        cp_err_inlet = surface
    else:
        raise type(cpe)(
            "Unable to determine location of failure from previous errors",
        ) from cpe

    if cp_err_inlet in ordered_subsurf_outlets:
        # subset of ordered_subsurf_outlets to check
        mod_subset = ordered_subsurf_outlets
    elif cp_err_inlet in ordered_surface_outlets:
        # subset of all modules in which error can be found
        mod_subset = ordered_surface_outlets
    else:
        raise Exception("Should be unreachable.  Notify TANGO team")

    _dp_dict, flow_res_dict, _opt_inlet_bcs, _act_inlet_bcs = get_dp_and_flow_res(
        unit_search,
        p_simple_inst_dict,
        mdot,
        state_ad_hoc,
    )

    # determine reasonable resistance cutoff to assess resistances of components
    # that can easily change -- this considers any pipes to be suitable
    # modification.  If the reservoir resistance is the limitng factor, well
    # spacing or mass flow rate can be reduced, but these both come with
    # substantial tradeoffs so if there are any components with obviously
    # high resistances compared to the others, these should be prioritized.
    # Basically anything with a well defined diameter is considered fair game
    # for modification.
    flow_res_threshold = np.percentile(
        [v for (k, v) in flow_res_dict.items() if k in mod_subset],
        0.25,
    )
    # find any models with resistance greater than `res_threshold_coeff` times the threshold resistance
    res_threshold_coeff = 5.0
    mods_with_outlier_res = {
        k: v
        for (k, v) in flow_res_dict.items()
        if v > res_threshold_coeff * flow_res_threshold and k in mod_subset
    }

    if len(mods_with_outlier_res) == 1:
        comp_with_narrow_d = next(iter(mods_with_outlier_res.keys()))
        narrow_d = diameters[next(iter(mods_with_outlier_res.keys()))]
        d_curr = narrow_d
        raise ComponentError(
            f"\n\t`{comp_with_narrow_d}` has excessive flow resistance compared to other components."
            + (
                f"\n\tThis could by fixed, for example, by matching the diameter used elsewhere in the system: {d_max_in_sys:.3f} m"
                if d_max_in_sys != d_curr
                else ""
            )
            + "\n\tTry the following"
            + "\n\t- reducing flow resistance, by e.g.:"
            + "\n\t\t- increasing pipe or wellbore diameter"
            + "\n\t\t- reducing pipe or wellbore interior surface roughness, `epsilon`"
            + "\n\t\t- checking that reservoir permeability is typed correctly",
            # + "\n\t- changing (e.g. increasing) `injection_pressure` (initial guess for solver) in `surface`",
        ) from cpe

        # TODO: check target_extraction_pressure w.r.t. to p_sat

    else:
        unit_search = re.search(r"unit: (\w+)", str(cpe))
        if unit_search:
            unit_str = unit_search[1]
        raise type(cpe)(
            f"\n\tThe overall system has a non-specific error arising in:\n\tunit: {unit_str}"
            + "\n\tTry the following"
            + "\n\t- reducing flow resistance of multiple components, by e.g.:"
            + "\n\t\t- increasing pipe or wellbore diameters"
            + "\n\t\t- reducing well spacing"
            + "\n\t\t- reducing pipe interior surface roughness, `epsilon`, in:"
            + "\n\t\t\t- `surface`"
            + "\n\t\t\t- `injection_well`"
            + "\n\t\t\t- `production_well`"
            + "\n\t\t\t- `production_well_pump` (which includes upper production well pipe)"
            + "\n\t\t- checking that reservoir permeability is typed correctly"
            + "\n\t- changing (e.g. increasing) `injection_pressure` (initial guess for solver) in `surface`"
            + "\n\t- changing (e.g. increasing) `hydro_static_pressure` in `reservoir`"
            + "\n\t- reducing the mass flow rate (this will reduce power output and should be avoided)",
        ) from cpe

