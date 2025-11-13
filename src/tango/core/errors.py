"""Module containing custom TANGO errors"""

import re


class TangoError(Exception):
    """Base exception for Tango package"""

    pass


class CoolPropError(TangoError, ValueError):
    """Error originating from CoolProp"""

    pass


def check_feas_press(p: float) -> str | None:
    """Check that absolute pressure is non-negative

    # Arguments:
    - `p`: absolute pressure
    """
    if p < 0:
        msg = (
            f"Absolute pressure ({p:.5g} Pa) must be greater than or equal to 0.0 Pa" +
            """
            Troubleshooting steps:
            - check for flow restrictions (e.g. too narrow wellbore diameter upstream of the current
                component, working backwards to the `bc_iteration_checkpoint`)
            - increase the pressure at the injection wellhead (note: this can potentially exceed
                fracture pressure limit of the subsurface caprock)
            - reduce mass flow rate (note: this will reduce total power output and should only be
                used if the other steps don't work)
            - TODO: print out component resistances ranked in decreasing order
            - TODO: include an option for setting up automation
            """
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


def check_feas_enthalpy(h: float) -> str | None:
    """Check that specific enthalpy is non-negative

    # Arguments:
    - `h`: specific enthalpy
    """
    if h < 0:
        return f"Specific enthalpy ({h:.5g} J/kg) must be greater than or equal to 0.0 J/kg"
    return None


def check_feas_entropy(s: float) -> str | None:
    """Check that specific entropy is non-negative

    # Arguments:
    - `h`: specific entropy
    """
    if s < 0:
        return f"Specific entropy ({s:.5g} J/(kg*K)) must be greater than or equal to 0.0 J/(kg*K)"
    return None

# TODO: after verifying that quality should be in [0, 1], make a checker


P_SAT_ERR_TEST = re.compile(
    "Saturation pressure \\[.+ Pa\\] corresponding to T \\[.+ K\\] " +
        "is within 1e-4 \\% of given p \\[.+ Pa\\]",
)
