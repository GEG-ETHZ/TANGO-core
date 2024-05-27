import math

def calculate_injection_rate(h, k, u, Pw, Pe, rw, re):
    """
    Calculate the injection rate using the given parameters in SI units.

    Parameters:
    h  : float : Height of the cylindrical area (meters)
    k  : float : Permeability (square meters)
    u  : float : Fluid viscosity (Pascal-seconds)
    Pw : float : Pressure at the wellbore (Pascals)
    Pe : float : Pressure at the reservoir boundary (Pascals)
    rw : float : Radius of the wellbore (meters)
    re : float : Radius of the reservoir boundary (meters)

    Returns:
    float : Injection rate (liter per second)
    """
    # Calculate injection rate using the formula
    q = (2 * math.pi * h * k * (Pw - Pe)) / (u * math.log(re / rw))
    print('Hi', h, k, u, Pw, Pe, rw, re)

    return q*1000.0

# # Example usage with sample values
# h = 100.0          # Height in meters
# print(specs)
# k = 1e-13         # Permeability in square meters (1 Darcy ≈ 9.869233e-13 m²)
# u = 0.001         # Fluid viscosity in Pascal-seconds (1 centipoise = 0.001 Pa·s)
# Pw = 46e6          # Pressure at the wellbore in Pascals (1 MPa = 1e6 Pa)
# Pe = 40e6          # Pressure at the reservoir boundary in Pascals (0.5 MPa = 5e5 Pa)
# rw = 0.2          # Radius of the wellbore in meters
# re = 500.0        # Radius of the reservoir boundary in meters
#
# injection_rate = calculate_injection_rate(h, k, u, Pw, Pe, rw, re)
# print(f"The allowed injection rate is {injection_rate*1000:.6e} liter per second")

