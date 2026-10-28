# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Interactive demo: tango flexible Single-Flash system.

Runs ``templates/hydro_sf_electric.yml`` and generates four figures that
``tango_core`` itself does not produce (see the section "What running the YAML alone
gets you" below):

  1. Temperature vs axial position parameterized by timestep
       - Injection well: full spatial profile (NumericalInjectionWell)
       - Production well: inlet/outlet only — lumped model, flat profile
         (TODO: replace with a spatially-resolved production well model)
  2. Reservoir inlet and outlet temperature vs elapsed time
  3. Gross power, production-pump power, and net power vs time
       (injection-pump power isn't wired to the economic layer yet —
       shown as a zero placeholder)
  4. Cumulative net energy, injection-pump energy, and production-pump energy vs time

Run from the repo root::

    uv run python applications/demo_hydro_sf_electric/demo_hydro_sf_electric.py

Default: writes PNGs to this script's own ``outputs/`` directory without
opening windows. Pass ``--show`` for interactive windows instead (nothing
is saved in that mode).

What running the YAML alone gets you
-------------------------------------
``tango_core run templates/hydro_sf_electric.yml --save-dir DIR`` (or
``Workflow.from_file(...).run()`` directly, with no further code) runs the
same simulation but produces none of the plots above: the CLI writes the
results files (``.results.yml``, ``.smry.csv``, ``.econ.csv``) and the
phase diagrams, and ``--no-save`` writes nothing at all. Every figure above comes from this script reading the completed
``Workflow``'s own ``history`` state after ``run()`` returns and plotting
it with matplotlib -- that's this demo's whole job, not something the YAML
run does on its own.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Path setup — allow running from anywhere in the repo
# ---------------------------------------------------------------------------

HERE = Path(__file__).parent
_REPO_ROOT = Path(__file__).parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from tango_core.workflows.workflow import Workflow  # noqa: E402

# hydro_sf_electric.yml lives in templates/ (configs only, shared
# with tests/regtest/test_lcoe_regression.py's own dedicated coverage, run
# via `just test --templates`/`--all`) — not colocated with this
# script, unlike the old templates/ layout.
YAML_PATH = _REPO_ROOT / "templates" / "hydro_sf_electric.yml"
SAVE_DIR = HERE / "outputs"
SAVE_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Run simulation
# ---------------------------------------------------------------------------


def run_simulation() -> Workflow:
    """Load and run the flexible Single-Flash YAML config; return the completed Workflow."""
    print(f"Running: {YAML_PATH.relative_to(_REPO_ROOT)}")
    wf = Workflow.from_file(YAML_PATH)
    start = time.time()
    wf.run()
    end = time.time()
    print(f"Time taken {end - start}")
    print("Simulation complete.")
    return wf


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------


def extract_data(wf: Workflow) -> dict:
    """Pull per-timestep state from all components after a completed run.

    Returns a flat dict of numpy arrays ready for plotting.
    """
    # _orchestrator.components is a dict keyed by the component names defined
    # in the YAML.  We unpack into locals here so the plotting code below reads
    # as plain names rather than repeated dict lookups.
    c = wf._orchestrator.components
    surface = c["surface"]
    inj = c["injection_well"]
    res = c["reservoir"]
    prod_lower = c["production_well_lower"]  # NumericalProductionWell — full cell profile
    prod_upper = c["production_well_upper"]  # LumpedProductionWell — has the production pump

    dt_years: float = wf._orchestrator.dt_years  # type: ignore[attr-defined]
    n_tsteps = len(surface.history.net_power_W)
    years = np.arange(n_tsteps) * dt_years

    # ------------------------------------------------------------------ wells
    # Injection well: spatial profiles, shape (n_tsteps, num_cells + 1) --
    # one value per axial NODE (node 0 = inlet, node num_cells = outlet),
    # not one per cell.
    inj_depth_m = np.linspace(0.0, inj.well_length, inj.num_cells + 1)
    T_inj = np.array(inj.history.T_cells)  # K
    P_inj = np.array(inj.history.P_cells)  # Pa

    # Production well lower: NumericalProductionWell — full spatial profile.
    # Depth axis runs from bottom (reservoir end) to surface end of lower segment.
    prod_depth_m = np.linspace(prod_lower.well_length, 0.0, prod_lower.num_cells + 1)
    T_prod_lower = np.array(prod_lower.history.T_cells)  # K, shape (n_tsteps, num_cells + 1)

    # ------------------------------------------------------------ reservoir
    res_T_in = np.array(res.history.T_inlet)  # K — from injection well BH
    res_T_out = np.array(res.history.T_outlet)  # K — to production well BH

    # ----------------------------------------------------------------- power
    # GraphSurface's history field is `net_power_W` (sum of -P.val over
    # role=net_electric TESPy nodes — already nets out the plant's own
    # internal turbine/pump balance), not `gross_power_watts` (an older
    # SingleFlashSurface field name that no longer exists). Kept the local
    # variable name `gross_MW` since well-level pump parasitics are still
    # subtracted from it below, same as before.
    gross_MW = np.array(surface.history.net_power_W) / 1e6
    prod_pump_MW = np.array(prod_upper.history.pump_power_watts) / 1e6
    inj_pump_MW = np.array(inj.history.pump_power_watts) / 1e6
    net_MW = gross_MW - prod_pump_MW - inj_pump_MW

    # ------------------------------------------------------ cumulative energy
    HOURS_PER_YEAR = 8760.0
    to_gwh = dt_years * HOURS_PER_YEAR  # MW·yr → GWh: MW × hr/yr × yr = MWh; /1e3 = GWh
    to_gwh /= 1e3
    cum_net_GWh = np.cumsum(net_MW) * to_gwh
    cum_prod_pump_GWh = np.cumsum(prod_pump_MW) * to_gwh
    cum_inj_pump_GWh = np.cumsum(inj_pump_MW) * to_gwh

    return {
        "years": years,
        "dt_years": dt_years,
        "n_tsteps": n_tsteps,
        "inj_depth_m": inj_depth_m,
        "T_inj": T_inj,
        "P_inj": P_inj,
        "prod_depth_m": prod_depth_m,
        "T_prod_lower": T_prod_lower,
        "res_T_in": res_T_in,
        "res_T_out": res_T_out,
        "gross_MW": gross_MW,
        "inj_pump_MW": inj_pump_MW,
        "prod_pump_MW": prod_pump_MW,
        "net_MW": net_MW,
        "cum_net_GWh": cum_net_GWh,
        "cum_prod_pump_GWh": cum_prod_pump_GWh,
        "cum_inj_pump_GWh": cum_inj_pump_GWh,
    }


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _timestep_cmap(n: int, name: str = "plasma"):
    cmap = plt.get_cmap(name, n)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=0, vmax=n - 1))
    sm.set_array([])
    return cmap, sm


# ---------------------------------------------------------------------------
# Figure 1 — Temperature vs axial position
# ---------------------------------------------------------------------------


def fig1_well_temperature_profiles(d: dict, save_path: Path | None = None) -> None:
    """Plot fluid temperature vs depth for injection and production wells, coloured by timestep."""
    n = d["n_tsteps"]
    cmap, sm = _timestep_cmap(n)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        "Well fluid temperature vs depth  (colour = timestep index, early=dark → late=bright)",
        fontsize=11,
    )

    # --- Injection well (full spatial profile) ---
    ax = axes[0]
    depth_km = d["inj_depth_m"] / 1e3
    for i, T_row in enumerate(d["T_inj"]):
        ax.plot(depth_km, T_row - 273.15, color=cmap(i / max(n - 1, 1)), lw=0.9, alpha=0.85)
    fig.colorbar(sm, ax=ax, label="Timestep index")
    ax.set_xlabel("Depth below surface (km)")
    ax.set_ylabel("Fluid temperature (°C)")
    ax.set_title("Injection well\n(NumericalInjectionWell — CoolProp)")
    ax.grid(True, alpha=0.3)

    # --- Production well lower (full spatial profile) ---
    # prod_depth_m runs from well_length (bottom/inlet) → 0 (wellhead/outlet),
    # so cell 0 = reservoir inlet, cell 99 = wellhead outlet.
    # invert_xaxis() puts the inlet (deep end) on the left so left→right = flow direction.
    ax = axes[1]
    cmap2, sm2 = _timestep_cmap(n)
    depth_km_prod = d["prod_depth_m"] / 1e3
    for i, T_row in enumerate(d["T_prod_lower"]):
        ax.plot(depth_km_prod, T_row - 273.15, color=cmap2(i / max(n - 1, 1)), lw=0.9, alpha=0.85)
    fig.colorbar(sm2, ax=ax, label="Timestep index")
    ax.invert_xaxis()  # flow direction: left = reservoir inlet (deep), right = wellhead (surface)
    ax.set_xlabel("Depth below surface (km)  [left = inlet, right = outlet]")
    ax.set_ylabel("Fluid temperature (°C)")
    ax.set_title("Production well (lower segment)\n(NumericalProductionWell — CoolProp)")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    _save_or_skip(fig, save_path)


# ---------------------------------------------------------------------------
# Figure 2 — Reservoir temperatures vs time
# ---------------------------------------------------------------------------


def fig2_reservoir_temperature(d: dict, save_path: Path | None = None) -> None:
    """Plot reservoir inlet and outlet temperature vs time with a secondary ΔT axis."""
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(
        d["years"],
        d["res_T_in"] - 273.15,
        "b-o",
        ms=4,
        label="Reservoir inlet T  (from injection well BH)",
    )
    ax.plot(
        d["years"],
        d["res_T_out"] - 273.15,
        "r-o",
        ms=4,
        label="Reservoir outlet T  (to production well BH)",
    )
    ax.set_xlabel("Elapsed time (years)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title(
        "Reservoir inlet and outlet temperature vs time\n"
        "(LumpedReservoir — Adams (2015) thermal depletion model)",
    )
    ax.grid(True, alpha=0.3)

    ax2 = ax.twinx()
    delta_T = d["res_T_out"] - d["res_T_in"]
    ax2.plot(d["years"], delta_T, "g-^", ms=4, lw=1.2, alpha=0.8, label="ΔT = outlet − inlet")
    ax2.set_ylabel("ΔT (K)", color="green")
    ax2.tick_params(axis="y", labelcolor="green")

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8)

    fig.tight_layout()
    _save_or_skip(fig, save_path)


# ---------------------------------------------------------------------------
# Figure 3 — Power vs time
# ---------------------------------------------------------------------------


def fig3_power_vs_time(d: dict, save_path: Path | None = None) -> None:
    """Plot gross, parasitic, and net power vs elapsed time."""
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(d["years"], d["gross_MW"], "r-o", ms=4, label="Gross power (surface plant)")
    ax.plot(
        d["years"],
        d["prod_pump_MW"],
        "b--s",
        ms=4,
        label="Production pump parasitic",
    )
    ax.plot(
        d["years"],
        d["inj_pump_MW"],
        "g--^",
        ms=4,
        label="Injection pump (not yet wired to economics — zero placeholder)",
    )
    ax.plot(d["years"], d["net_MW"], "k-D", ms=5, lw=1.8, label="Net power")
    ax.set_xlabel("Elapsed time (years)")
    ax.set_ylabel("Power (MW)")
    ax.set_title("Power vs time")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _save_or_skip(fig, save_path)


# ---------------------------------------------------------------------------
# Figure 4 — Cumulative energy vs time
# ---------------------------------------------------------------------------


def fig4_cumulative_energy(d: dict, save_path: Path | None = None) -> None:
    """Plot cumulative net, production-pump, and injection-pump energy vs elapsed time."""
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(d["years"], d["cum_net_GWh"], "k-D", ms=5, lw=1.8, label="Cumulative net energy")
    ax.plot(
        d["years"],
        d["cum_prod_pump_GWh"],
        "b--s",
        ms=4,
        label="Cumulative production-pump energy",
    )
    ax.plot(
        d["years"],
        d["cum_inj_pump_GWh"],
        "g--^",
        ms=4,
        label="Cumulative injection-pump energy (not yet wired — zero)",
    )
    ax.set_xlabel("Elapsed time (years)")
    ax.set_ylabel("Cumulative energy (GWh)")
    ax.set_title("Cumulative energy vs time")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _save_or_skip(fig, save_path)


def _save_or_skip(fig: plt.Figure, save_path: Path | None) -> None:
    if save_path is not None:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Saved: {save_path.relative_to(_REPO_ROOT)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments, run the simulation, and generate all four figures."""
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open interactive plot windows instead of saving PNGs.",
    )
    args = parser.parse_args()

    if not args.show:
        matplotlib.use("Agg")

    wf = run_simulation()
    d = extract_data(wf)

    print("Generating figures...")

    def _sp(name: str) -> Path | None:
        return None if args.show else SAVE_DIR / name

    fig1_well_temperature_profiles(d, _sp("fig1_well_temperature_profiles.png"))
    fig2_reservoir_temperature(d, _sp("fig2_reservoir_temperature.png"))
    fig3_power_vs_time(d, _sp("fig3_power_vs_time.png"))
    fig4_cumulative_energy(d, _sp("fig4_cumulative_energy.png"))

    if args.show:
        plt.show()
    print("Done.")


if __name__ == "__main__":
    main()
