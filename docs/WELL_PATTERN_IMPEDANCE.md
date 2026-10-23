# Well-Pattern Impedance

The analytic hydraulic impedance of a doublet, five-spot or inverted
five-spot well pattern, as implemented in
`src/tango/components/reservoir/wellpattern_impedance.py` and used by
`LumpedReservoir`. Status: available.

## The `WellPattern` enum

`WellPattern(StrEnum)` lists the supported well patterns. Its
`.impedance()` method returns the analytic hydraulic impedance `Z`
(Pa·s/kg), which relates mass flow rate to pressure drop: `ΔP = ṁ · Z`.
The formulas follow
[Birdsell, D.T., Adams, B.M., Deb, P., Ogland-Hand, J.D., Bielicki, J.M., Fleming, M.R., & Saar, M.O. (2024). Analytical solutions to evaluate the geothermal energy generation potential from sedimentary-basin reservoirs. Geothermics, 116, 102843.](https://doi.org/10.1016/j.geothermics.2023.102843)

With `L` the well spacing, `D` the effective well diameter, `k` the
permeability, `b_eff = thickness · net_to_gross_ratio`, `μ` the viscosity
and `ρ` the density:

| Pattern (`layout.well_pattern`) | Member | Impedance `Z` | Status |
|---|---|---|---|
| `DOUBLET` | `WellPattern.Doublet` | `μ · (ln(L / (e·D)) + D/L) / (ρ · k · b_eff · π)` | available |
| `5SPOT` | `WellPattern.FiveSpot` | `μ / (4 · ρ · k · b_eff) · ln(4L / (π·D))` | available |
| `INVERTED_5SPOT` | `WellPattern.InvertedFiveSpot` | `μ / (ρ · k · b_eff) · ln(4L / (π·D))` | available |
| `AGS_DOUBLET` | `WellPattern.AGSDoublet` | none; raises `NotImplementedError` | planned |

Names are case-insensitive: `WellPattern("doublet")` and
`WellPattern("DOUBLET")` are the same member.

## Use in `LumpedReservoir`

`LumpedReservoir` (`src/tango/components/reservoir/lumped.py`) holds the
configured pattern and defaults to `WellPattern.Doublet` when
`layout.well_pattern` is absent. Each solve evaluates the impedance with the
fluid properties at the current state:

```python
Z = self.wp.impedance(
    mu=mu,
    rho=rho,
    permeability=self.permeability,
    thickness=self.thickness,
    net_to_gross_ratio=self.net_to_gross_ratio,
    well_spacing=self.well_spacing,
    well_eff_diameter=self.well_eff_diameter,
)

dp = mdot * Z
```

The doublet formula is the same expression that was previously written
inline in `LumpedReservoir`; moving it into `WellPattern` added the
five-spot patterns without changing doublet results.

## Tests

`tests/regtest/test_config_validation.py` covers the config side:

| Config | Result |
|---|---|
| `undefined_well_pattern.yml`: a name that matches no pattern | `ConfigError` |
| `well_pattern_not_implemented.yml`: `AGS_DOUBLET` | `NotImplementedError` |
| `no_well_pattern.yml`: no `well_pattern` key | A warning; the reservoir uses `DOUBLET` |
