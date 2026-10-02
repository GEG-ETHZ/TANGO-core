# Well Pattern Analytic Impedance ``tango/components/reservoir/wellpattern_impedance.py``
Created a class ``WellPattern(StrEnum)`` which has a function ``.impedance()`` to calcuate analytical impedance of a reservoir with a doublet, five spot or inverted five spot based on [Birdsell, D.T., Adams, B.M., Deb, P., Ogland-Hand, J.D., Bielicki, J.M., Fleming, M.R., & Saar, M.O. (2024). Analytical solutions to evaluate the geothermal energy generation potential from sedimentary-basin reservoirs. Geothermics, 116, 102843.](https://doi.org/10.1016/j.geothermics.2023.102843) (previously misattributed as "Adams et al. (2020)" — corrected 2026-09-21, see `wellpattern_impedance.py`'s own docstring for the same correction). This can be found in ``src/tango/components/reservoir/wellpattern_impedance.py``
Originally the equation for the Doublet was hardcoded into ``LumpedReservoir``
python
```
L = self.well_spacing
D = self.well_eff_diameter
b_eff = self.thickness * self.net_to_gross_ratio

Z = mu * (math.log(L / (math.e * D)) + D / L) / (rho * self.permeability * b_eff * math.pi)
```
Now the class ``WellPatterm`` is imported into lumped and the function for the well pattern type is called with ``WellPattern.impedance()``.
python
```
wp = WellPattern(well_pattern_name: str)

Z = wp.impedance(
    mu=mu,
    rho=rho,
    permeability=self.permeability,
    thickness=self.thickness,
    net_to_gross_ratio=self.net_to_gross_ratio,
    well_spacing=self.well_spacing,
    well_eff_diameter=self.well_eff_diameter,
)
```
I wrote some tests to check the parity with old tango, check undefined well-patterns do not run (they return an error message) and to check a file with an undefined well pattern defaults to doublet. These tests are written in ``tests/regtest/test_well_pattern.py``
