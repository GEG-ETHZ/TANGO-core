# Sources

Every published source TANGO relies on for a value, a correlation, or a
model. Code and configs cite these by key, keeping a short author–year name
inline, e.g.

```python
"""Wellbore heat loss per Zhang et al. (2011); see docs/SOURCES.md#zhang2011."""
```

```yaml
efficiency: 0.85   # turbine eta_s, DiPippo (2016) -- see docs/SOURCES.md#dipippo2016
```

Each entry says what TANGO takes from the source and how the citation was
verified. "Verified (Crossref)" or "(DataCite)" means the bibliographic
details were checked against the DOI registry's metadata; "as cited in"
means the value was confirmed in a source that cites it, not in the original
itself. Keep entries alphabetical by key.

## Adams2015

Adams, B.M., Kuehn, T.H., Bielicki, J.M., Randolph, J.B., & Saar, M.O.
(2015). A comparison of electric power output of CO2 Plume Geothermal (CPG)
and brine geothermal systems for varying reservoir conditions. *Applied
Energy*, 140, 365–377. <https://doi.org/10.1016/j.apenergy.2014.11.043>

- **Used for:** the reservoir thermal-depletion fitting function γ(ψ)
  (`components/reservoir/lumped.py`).
- **Verified:** Crossref.

## Adams2020genGEO

Adams, B.M. & Schädle, P. (2020). *genGEO: coupled
reservoir-electricity-cost geothermal simulator*, v0.0.1 [Software].
Zenodo. <https://doi.org/10.5281/zenodo.4383139>

- **Used for:** the doublet reservoir impedance (`components/reservoir/lumped.py`).
- **Verified:** DataCite.

## Adams2021genGEO

Adams, B.M., Ogland-Hand, J.D., Bielicki, J.M., Schädle, P., & Saar, M.O.
(2021). Estimating the geothermal electricity generation potential of
sedimentary basins using genGEO (the generalizable GEOthermal
techno-economic simulator). ChemRxiv preprint.
<https://doi.org/10.26434/chemrxiv.13514440.v1>

- **Used for:** the exact form of the wellbore heat-loss coefficient β
  (Supplemental Information §S6 "Wellbore Model", Eqs. S65–S66), which
  itself follows [Zhang2011](#zhang2011) (`core/fluid_utils.py`).
- **Verified:** Crossref (preprint record). A peer-reviewed journal version
  was not found; cite the journal version instead if one exists.

## Ahmad2023

Ahmad, A.H., Darmanto, P.S., Juangsa, F.B., Al Asy'ari, M.R., Adityatama,
D., & Purba, D. (2023). Thermodynamic and economic comparison of Organic
Rankine Cycle and Kalina Cycle as bottoming unit to utilize exhaust steam
from back pressure turbine geothermal power plant. *Proceedings, 48th
Workshop on Geothermal Reservoir Engineering*, Stanford University,
SGP-TR-224.
<https://pangea.stanford.edu/ERE/db/GeoConf/papers/SGW/2023/Ahmad.pdf>

- **Used for:** the secondary citation for [DiPippo2016](#dipippo2016)'s
  turbine and pump efficiencies ("The isentropic efficiency of turbine is
  85% (DiPippo 2016)"; "The adiabatic efficiency of pump is 75% (DiPippo
  2016)").
- **Verified:** read directly (the quoted sentences and its reference list).

## Birdsell2024

Birdsell, D.T., Adams, B.M., Deb, P., Ogland-Hand, J.D., Bielicki, J.M.,
Fleming, M.R., & Saar, M.O. (2024). Analytical solutions to evaluate the
geothermal energy generation potential from sedimentary-basin reservoirs.
*Geothermics*, 116, 102843.
<https://doi.org/10.1016/j.geothermics.2023.102843>

- **Used for:** the well-pattern impedance factors for doublet, five-spot,
  and inverted five-spot patterns
  (`components/reservoir/wellpattern_impedance.py`).
- **Verified:** Crossref. The DOI's "2023" is the online-first year; the
  issue is 2024.

## Colebrook1939

Colebrook, C.F. (1939). Turbulent flow in pipes, with particular reference
to the transition region between the smooth and rough pipe laws. *Journal
of the Institution of Civil Engineers*, 11(4), 133–156.
<https://doi.org/10.1680/ijoti.1939.13150>

- **Used for:** the implicit friction-factor equation that
  [SwameeJain1976](#swameejain1976) and [Haaland1983](#haaland1983)
  approximate (`core/fluid_utils.py`).
- **Verified:** Crossref.

## DiPippo2016

DiPippo, R. (2016). *Geothermal Power Plants: Principles, Applications,
Case Studies and Environmental Impact*, 4th ed.

- **Used for:** standard component efficiencies in the example configs —
  turbine isentropic efficiency **0.85**; surface pump (feed, circulation)
  efficiency **0.75**.
- **Verified:** as cited in [Ahmad2023](#ahmad2023); the book itself was not
  checked.

## Haaland1983

Haaland, S.E. (1983). Simple and explicit formulas for the friction factor
in turbulent pipe flow. *Journal of Fluids Engineering*, 105(1), 89–90.
<https://doi.org/10.1115/1.3240948>

- **Used for:** the default explicit Darcy friction factor
  (`core/fluid_utils.py`, `core/physics_models.py`).
- **Verified:** Crossref.

## SwameeJain1976

Swamee, P.K. & Jain, A.K. (1976). Explicit equations for pipe-flow
problems. *Journal of the Hydraulics Division, ASCE*, 102(5), 657–664.
<https://doi.org/10.1061/JYCEAJ.0004542>

- **Used for:** the alternative explicit Darcy friction factor
  (`core/fluid_utils.py`, `core/physics_models.py`).
- **Verified:** Crossref.

## vantSpijker2016

van 't Spijker, H. & Ungemach, P. (2016). *Definition of Electrosubmersible
pump (ESP) design and selection workflow*. Kennisagenda Aardwarmte
2015/2016 (Dutch Ministry of Economic Affairs knowledge agenda for
geothermal energy).
<https://geothermie.nl/images/Onderzoeken-en-rapporten/01_07_16_Definitie_ESP/20031_Definition_of_ESP_design-_final_version_20160919-public.pdf>

- **Used for:** the standard downhole pump efficiency **0.55**: the overall
  ESP string efficiency (pump 70% × motor 90% × cable 97% × transformer
  99% × frequency converter 94%), which the report says "should be
  achievable in most configurations". Used rather than the 70% pump-only
  figure because downhole pump power is billed as electricity.
- **Verified:** read directly.

## Zhang2011

Zhang, Y., Pan, L., Pruess, K., & Finsterle, S. (2011). A time-convolution
approach for modeling heat exchange between a wellbore and surrounding
formation. *Geothermics*, 40(4), 261–266.
<https://doi.org/10.1016/j.geothermics.2011.08.003>

- **Used for:** the transient wellbore heat-loss correlation (the two-regime
  coefficient β, Eqs. 1–2) used by the numerical wells
  (`core/fluid_utils.py`, `core/physics_models.py`,
  `components/well/numerical.py`).
- **Verified:** Crossref.
