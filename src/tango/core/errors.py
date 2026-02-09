"""Module containing custom TANGO errors"""

import logging
import re
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class TangoError(Exception):
    """Base exception for Tango package"""

    pass


class ThermodynamicError(TangoError):
    """Base class for all thermodynamic property evaluation errors.

    Subclasses distinguish error SOURCE:
    - CoolPropError: error originated directly from CoolProp
    - TESPyError: error originated from TESPy (not involving CoolProp)
    - TESPyCoolPropError: error originated from CoolProp via TESPy
    """

    pass


class ConvergenceError(TangoError):
    """TANGO failed to converge on a solution"""


class MassFlowRateError(ConvergenceError):
    """Inappropriate mass flow rate causes convergence issue"""


class ComponentError(ConvergenceError):
    """Specific module/component is likely source of failed convergence"""


class CoolPropError(ThermodynamicError, ValueError):
    """Error originating directly from CoolProp"""

    pass


class PressureError(CoolPropError):
    """Error caused by failed property evaluation involving pressure"""

    pass


class SaturationPressureError(PressureError):
    """Error caused by failed property evaluation due to saturation pressure threshold"""

    pass


class SubzeroStateVarError(CoolPropError):
    """Error caused by failed property evaluation due non-physical negative state variable"""

    pass


class SubzeroPressureError(PressureError):
    """Error caused by failed property evaluation due non-physical negative pressure"""

    pass


class SubzeroTempError(SubzeroStateVarError):
    """Error caused by failed property evaluation due non-physical negative absolute temperature"""

    pass


class SubzeroPandTError(SubzeroPressureError, SubzeroTempError):
    """Error caused by failed property evaluation due non-physical negative pressure and temperature"""

    pass


class InvalidEnthalpyError(SubzeroStateVarError):
    """Error caused by failed property evaluation due non-physical enthalpy"""

    pass


class InvalidPandHError(SubzeroPressureError, InvalidEnthalpyError):
    """Error caused by failed property evaluation due non-physical negative pressure and non-physical
    enthalpy
    """

    pass


class InvalidEntropyError(SubzeroStateVarError):
    """Error caused by failed property evaluation due non-physical entropy"""

    pass


class InvalidPandSError(SubzeroPressureError, InvalidEntropyError):
    """Error caused by failed property evaluation due non-physical negative pressure and entropy"""

    pass


class ProPumpInletFlashError(SaturationPressureError):
    """Error indicating that liquid is hitting saturating threshold at pump inlet"""

    pass


# --- TESPy Error Classes ---
# These represent errors originating from TESPy (not directly from CoolProp)


class TESPyError(ThermodynamicError):
    """Error originating from TESPy solver

    Use this for TESPy-specific solver failures, convergence issues,
    and other TESPy errors
    """

    pass


class TESPyCoolPropError(CoolPropError, TESPyError):
    """Error originating from CoolProp via TESPy.

    Use this when TESPy calls CoolProp internally and CoolProp raises an error.
    The traceback will show the error propagating through TESPy from CoolProp.
    """

    pass


class TESPySubZeroError(TESPyCoolPropError):
    """Error from TESPy solver encountering non-physical negative state variable."""

    pass


class TESPyExcessSMolarError(TESPyCoolPropError):
    """Error from TESPy solver encountering molar entropy."""

    pass


class TangoValueError(TangoError, ValueError):
    """ValueError that needs to be handled"""

    pass


def check_feas_press(p: float) -> str | None:
    """Check that absolute pressure is non-negative

    # Arguments:
    - `p`: absolute pressure
    """
    if p < 0:
        msg = (
            f"Absolute pressure ({p:.5g} Pa) must be greater than or equal to 0.0 Pa"
            # TODO: move this out to a higher level where mass flow rate control
            # can be checked (either manual or automatic)
            # """
            # Troubleshooting steps:
            # - check for flow restrictions
            # - increase the pressure at the injection wellhead (note: this can potentially exceed
            #     fracture pressure limit of the subsurface caprock)
            # - reduce mass flow rate (note: this will reduce total power output and should only be
            #     used if the other steps don't work)
            # """
        )
        return msg
    return None


def check_feas_temp(te: float) -> str | None:
    """Check that absolute temperature is non-negative

    # Arguments:
    - `te`: absolute temperature
    """
    if te < 0:
        return f"Absolute temperature ({te:.5g} K) must be greater than or equal to 0.0 K"
    return None


def check_feas_enthalpy(_h: float) -> str | None:
    """Check that specific enthalpy is non-negative

    # Arguments:
    - `h`: specific enthalpy
    """
    # TODO: determine minimum enthalpy expected in geothermal system based on CoolProp reference state
    # if h < 0:
    #     return f"Specific enthalpy ({h:.5g} J/kg) must be greater than or equal to 0.0 J/kg"
    return None


def check_feas_entropy(_s: float) -> str | None:
    """Check that specific entropy is non-negative

    # Arguments:
    - `s`: specific entropy
    """
    # TODO: determine minimum entropy expected in geothermal system based on CoolProp reference state
    # if s < 0:
    #     return f"Specific entropy ({s:.5g} J/(kg*K)) must be greater than or equal to 0.0 J/(kg*K)"
    return None


# TODO: after verifying that quality should be in [0, 1], make a checker


P_SAT_ERR_TEST = re.compile(
    "Saturation pressure \\[.+ Pa\\] corresponding to T \\[.+ K\\] "
    + "is within 1e-4 \\% of given p \\[.+ Pa\\]",
)


# Matches TESPy solver errors with non-physical negative values
# Example: "solver_rho_Tp was unable to find a solution for T=286.818, p=-4.14216e+07,
#           with guess value -17369.7 with error: The molar density of -17369.665904 mol/m3
#           is below the minimum of 0.000000 mol/m3"
SUBZERO_DNSTY_ERR_TEST = re.compile(
    r"solver_rho_Tp was unable to find a solution.*"
    + r"is below the minimum of 0\.0+ mol/m3",
)

EXCESS_SMOLAR_TEST = re.compile(
    "unable to solve 1phase PY flash with Tmin=\\d+\\.\\d*, Tmax=\\d+(\\.\\d*){0,1} due to error: " +
        "HSU_P_flash_singlephase_Brent could not find a solution because Smolar \\[\\d+\\.\\d* J/mol/K] " +
        "is above the maximum value of \\d+\\.\\d* J/mol/K",
)


class ValidationError(ValueError):
    """Error for failed validation"""

    pass


@dataclass
class Validator(ABC):
    """Base class that ensures validation methods

    # Attributes
    # - `val_file`: path to file containing validation data
    #   This file contains key value pairs that get parsed to remove `_warn` or `_err` suffixes
    #   If, for example a parameter `well_length_err: [10, 10_000]` is in the file, a warning will be logged
    #   if the well length exceeds that value
    # - `val_dict`: dictionary containing validation data
    """

    val_file: Path
    val_dict: dict[str, list[float | None]] = field(init=False)

    def __post_init__(self):
        """Load validation data from yml"""
        try:
            with open(self.val_file) as file:
                self.val_dict = yaml.load(file, Loader=yaml.SafeLoader)
        except Exception as e:
            raise RuntimeError(f"Failed to read {self.val_file}") from e
        self.validate()

    def validate(self):
        """Validate parameters"""
        # dictionary to store validation parameters that have been used
        used_dict: dict[str, float] = {}

        warnings: list[str] = []
        errors: list[str] = []
        for vdk in self.val_dict:
            vdv = self.val_dict[vdk]
            assert len(vdv) == 2, vdv
            if vdv[1] is not None and vdv[0] is not None:
                assert vdv[1] > vdv[0], vdv
            used_dict[vdk] = vdv

            if "specs" in self.__dir__():
                if isinstance(self.specs, dict):
                    specs = self.specs
                else:
                    specs = self.specs.__dict__
            elif "_specs" in self.__dir__():
                if isinstance(self.specs, dict):
                    specs = self._specs
                else:
                    specs = self._specs.__dict__
            else:
                raise AttributeError("`self` has neither `specs` nor `_specs`")

            for sk, sv in specs.items():
                if sk.strip("_") == vdk.removesuffix("_warn").removesuffix("_err"):
                    # specs key.as validation key
                    # coerce to float in case it's a string
                    if vdv[0] is not None:
                        vdv[0] = float(vdv[0])
                    if vdv[1] is not None:
                        vdv[1] = float(vdv[1])
                    if (vdv[1] is not None) and (sv > vdv[1]) and ("_err" in vdk):
                        errors.append(f"{sk}: {sv} exceeds max allowed value: {vdv}")
                    if (vdv[0] is not None) and (sv < vdv[0]) and ("_err" in vdk):
                        errors.append(f"{sk}: {sv} is less than min allowed value: {vdv}")
                    if (vdv[1] is not None) and (sv > vdv[1]) and ("_warn" in vdk):
                        warnings.append(f"{sk}: {sv} exceeds max allowed value: {vdv}")
                    if (vdv[0] is not None) and (sv < vdv[0]) and ("_warn" in vdk):
                        warnings.append(f"{sk}: {sv} is less than min allowed value: {vdv}")

        if len(self.val_dict) != len(used_dict):
            raise NameError(
                f"\nInvalid variables in {self.val_file}:" +
                    f"\n{set(self.val_dict.keys()) - set(used_dict.keys())}",
            )

        if len(errors) > 0:
            raise ValidationError(f"\nmodule id: {self.id}\n\t" + "\n\t".join(errors))

        if len(warnings) > 0:
            logging.warning(f"\nmodule id: {self.id}\n\t" + "\n\t".join(warnings))  # noqa: LOG015
