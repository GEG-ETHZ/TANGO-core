import math

def calculate_injection_rate(h, k, u, Pw, Pe, rw, re):
    """
    Calculates the fracing volumetric flow rate.

    This function computes the rate of fluid injection into a reservoir using parameters such
    as permeability, viscosity, pressures, and geometrical properties of the wellbore and reservoir.
    The result is given in cubic meter per second.

    Parameters:
        h (float): The height of the cylindrical area (in meters).
        k (float): The permeability of the reservoir (in square meters).
        u (float): The fluid viscosity (in Pascal-seconds).
        Pw (float): The pressure at the wellbore (in Pascals).
        Pe (float): The pressure at the reservoir boundary (in Pascals).
        rw (float): The radius of the wellbore (in meters).
        re (float): The radius of the reservoir boundary (in meters).

    Returns:
        float: The calculated injection rate (in cubic meter per second).

    Example:
        .. code-block:: python

            h = 100.0          # Height in meters
            k = 1e-13          # Permeability in square meters (1 Darcy ≈ 9.869233e-13 m²)
            u = 0.001          # Fluid viscosity in Pascal-seconds (1 centipoise = 0.001 Pa·s)
            Pw = 46e6          # Pressure at the wellbore in Pascals (46 MPa)
            Pe = 40e6          # Pressure at the reservoir boundary in Pascals (40 MPa)
            rw = 0.2           # Radius of the wellbore in meters
            re = 500.0         # Radius of the reservoir boundary in meters

            injection_rate = calculate_injection_rate(h, k, u, Pw, Pe, rw, re)
            print(f"The allowed injection rate is {injection_rate:.6f} cubic meter per second")

    Notes:
        The formula used to calculate the injection rate is:

        .. math::
            q = \\frac{2 \\pi h k (P_w - P_e)}{u \\ln(\\frac{r_e}{r_w})}

        Where:
            - `q` is the injection rate (in cubic meters per second)
            - `h` is the height of the cylindrical area (in meters)
            - `k` is the permeability (in square meters)
            - `u` is the fluid viscosity (in Pascal-seconds)
            - `Pw` is the pressure at the wellbore (in Pascals)
            - `Pe` is the pressure at the reservoir boundary (in Pascals)
            - `rw` is the radius of the wellbore (in meters)
            - `re` is the radius of the reservoir boundary (in meters)

        The resulting rate can be converted to liters per second by multiplying the output by 1000.
    """
    # Calculate injection rate using the formula
    q = (2 * math.pi * h * k * (Pw - Pe)) / (u * math.log(re / rw))

    return q
