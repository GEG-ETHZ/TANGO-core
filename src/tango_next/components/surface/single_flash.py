"""TESPy-backed Single-Flash surface / power-plant component for tango_next.

SingleFlashSurface wraps a full TESPy single-flash thermodynamic cycle
(valve → droplet separator → [turbine branch + pump2 liquid branch] → mixer →
outlet) to compute injection temperature, outlet pressure, and net power from
first principles.

TESPy network topology (hardcoded for single-flash)
----------------------------------------------------
    Source → Valve → DropletSeparator ─┬─(vapor)→ Turbine → Condenser → Pump ─┐
                                        └─(liquid)→ Pump2 ──────────────────────┤
                                                                                 └→ Merge → Sink

TESPy objects (Network, Connection, component handles) are built in init() and
stored as private Python attributes.  They are NOT Pydantic fields, so they are
excluded from model_dump().  Save/restore works by serializing only the numeric
fields (state, history) and calling init() again on restore to rebuild TESPy.

Unit conventions (TESPy network created with p_unit="bar", T_unit="C")
-----------------------------------------------------------------------
  - YAML p_out_megapascals → bar via × 10 (1 MPa = 10 bar)
  - Temperatures: K → °C for TESPy input, TESPy °C → K for output
  - Pressures:    Pa → bar for TESPy input, bar → Pa for output
  - Power:        TESPy node.P.val in W (SI), regardless of h_unit="kJ/kg" display setting

Cooling tower parasitic (BAC regression — WET or DRY mode)
------------------------------------------------------------
  f_parasitic = a/ΔT_approach + b·T_amb + c·T_amb/ΔT_approach + d/(ΔT_approach + ΔT_range)
  W_cooling_tower = Q_condenser × f_parasitic

References
----------
  - old tango: src/tango/units/native/surface/flexible_pp.py (PowerPlant class)
  - Adams, B.M. et al. (2015) — geothermal well thermal model (BAC coefficients)

"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field

from tango_next.components.surface.base import SurfaceComponent
from tango_next.core.fluid_utils import (
    friction_factor_haaland,
    mean_velocity,
    pressure_drop_friction,
    reynolds_number,
    water_density,
    water_viscosity,
)
from tango_next.core.locked_state import LockedState

_PA_TO_BAR: float = 1e-5
_BAR_TO_PA: float = 1e5
_K_TO_C: float = -273.15
_C_TO_K: float = 273.15

# BAC regression coefficients — (a, b, c, d) tuples
# Source: old tango PowerPlant.compute_cooler_condenser_power()
_BAC_COEFFS: dict[str, dict[str, list[float]]] = {
    "WET": {
        "cooler": [1.2, 0.0, -3.79e-3, 1.95e-2],
        "condenser": [1.65, -6.24e-6, -5.03e-3, 0.0],
    },
    "DRY": {
        "cooler": [7.65e-1, 0.0, 0.0, 1.28e-1],
        "condenser": [0.619, 0.0, 0.0, 0.0],
    },
}


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


def _ls() -> LockedState[float]:
    ls: LockedState[float] = LockedState(float("nan"))
    ls.mark_stale()
    return ls


@dataclass(frozen=True)
class SingleFlashSurfaceState:
    """Full simulation state for one surface plant solve step.

    All fields are ``LockedState[float]`` — writable exactly once per timestep.
    Call ``mark_all_stale()`` at the start of each ``solve()``.
    """

    # Inlet conditions (hot production fluid from production well)
    T_inlet: LockedState[float] = field(default_factory=_ls)
    P_inlet: LockedState[float] = field(default_factory=_ls)
    mass_rate: LockedState[float] = field(default_factory=_ls)

    # Surface pipe (wellhead → plant)
    dP_pipe: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Friction pressure drop across the surface pipe (Pa)."""
    P_tespy_inlet: LockedState[float] = field(default_factory=_ls)
    """Pressure passed to TESPy inlet = P_inlet − dP_pipe (Pa)."""

    # Flash diagnostics
    T_flash_K: LockedState[float] = field(default_factory=_ls)
    """Saturation temperature at flash valve outlet (K)."""
    P_flash_Pa: LockedState[float] = field(default_factory=_ls)
    """Flash pressure after valve (Pa)."""
    steam_fraction: LockedState[float] = field(default_factory=_ls)
    """Vapor quality (mass fraction steam) after the droplet separator."""

    # Power breakdown (all in W)
    gross_turbine_power_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Gross turbine shaft power (positive = production)."""
    pump_power_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Condensate pump parasitic (positive = consumption)."""
    pump2_power_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Separator liquid pump2 parasitic (positive = consumption)."""
    cooling_tower_power_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Cooling-tower fan/circulator parasitic (positive = consumption)."""
    gross_power_watts: LockedState[float] = field(default_factory=_ls)
    """Alias for gross_turbine_power_W — used by existing tests and demo plots."""
    net_power_W: LockedState[float] = field(default_factory=_ls)  # noqa: N815
    """Net electrical power = gross − pump1 − pump2 − cooling tower (W)."""

    # Outlet conditions (injection stream)
    T_outlet: LockedState[float] = field(default_factory=_ls)
    P_outlet: LockedState[float] = field(default_factory=_ls)
    rho: LockedState[float] = field(default_factory=_ls)
    mu: LockedState[float] = field(default_factory=_ls)

    def mark_all_stale(self) -> None:
        """Mark every field stale — call at the start of each ``solve()``."""
        for f in dataclasses.fields(self):
            getattr(self, f.name).mark_stale()


# ---------------------------------------------------------------------------
# History dataclass
# ---------------------------------------------------------------------------


@dataclass
class SingleFlashSurfaceHistory:
    """Per-timestep history of surface-plant scalar state."""

    T_inlet: list[float] = field(default_factory=list)
    T_outlet: list[float] = field(default_factory=list)
    P_outlet: list[float] = field(default_factory=list)
    gross_power_watts: list[float] = field(default_factory=list)
    net_power_W: list[float] = field(default_factory=list)  # noqa: N815
    steam_fraction: list[float] = field(default_factory=list)

    def record(self, state: SingleFlashSurfaceState) -> None:
        """Append a snapshot of ``state`` as one timestep entry."""
        self.T_inlet.append(state.T_inlet.get_fresh())
        self.T_outlet.append(state.T_outlet.get_fresh())
        self.P_outlet.append(state.P_outlet.get_fresh())
        self.gross_power_watts.append(state.gross_power_watts.get_fresh())
        self.net_power_W.append(state.net_power_W.get_fresh())
        self.steam_fraction.append(state.steam_fraction.get_fresh())


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


class SingleFlashSurface(SurfaceComponent):
    """TESPy-backed Single-Flash surface / power plant.

    The BC variable is ``injection_pressure``, which SystemBCIteration updates
    each convergence pass via ``set_injection_pressure()``.

    TESPy network is built once in ``init()`` and reused across timesteps.
    The network is NOT serialized — on restore, call ``init()`` again after
    ``from_config(skip_init=True)`` to rebuild it.

    Parity target: ``src/tango/units/native/surface/flexible_pp.py``
    (PowerPlant class + SurfaceUnitFlexiblePP.process_stream()).
    """

    power_plant: dict[str, Any] = Field(default_factory=dict)
    """Sub-block of the YAML describing the single-flash power plant topology
    and component configuration (valve pressure, turbine efficiency, condenser
    mode, etc.).  Parsed by init() to build the TESPy network.
    """
    well_spacing: float = 707.0
    """Injector-to-producer distance (m), used as surface pipe length.
    Matches src/tango/'s SurfaceUnitFlexiblePP which uses well_spacing as L
    in the Darcy-Weisbach pipe pressure drop before passing to TESPy.
    Populated from layout.well_spacing in the merged config.
    """

    # ---- Runtime state / history ----
    state: SingleFlashSurfaceState = Field(default_factory=SingleFlashSurfaceState)
    history: SingleFlashSurfaceHistory = Field(default_factory=SingleFlashSurfaceHistory)

    # ------------------------------------------------------------------
    # Lifecycle: build TESPy network
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Build TESPy single-flash network from the power_plant config block."""
        from tespy.components import (  # noqa: PLC0415 (late import — TESPy is heavy)
            Compressor,
            DropletSeparator,
            Merge,
            SimpleHeatExchanger,
            Sink,
            Source,
            Turbine,
            Valve,
        )
        from tespy.connections import Connection
        from tespy.networks import Network

        pp = self.power_plant

        # --- TESPy components (labels must match old tango for parity) ---
        src = Source("inlet")
        valve = Valve("valve")
        sep = DropletSeparator("droplet_separator")
        turb = Turbine("turbine")
        cond = SimpleHeatExchanger("condenser")
        pump = Compressor("pump")
        pump2 = Compressor("pump2")
        mixer = Merge("mixer")
        sink = Sink("outlet")

        # --- Fixed single-flash topology ---
        # Indices used in solve() to set BCs:
        #  [0] src   → valve   : inlet BCs (T, p, m, fluid)
        #  [1] valve → sep     : flash pressure
        #  [2] sep   → pump2   : liquid branch (out1)
        #  [3] sep   → turb    : vapor branch (out2)
        #  [4] turb  → cond    : turbine exhaust pressure
        #  [5] cond  → pump    : condenser outlet (p + x)
        #  [6] pump  → mixer   : condensate (in1)
        #  [7] pump2 → mixer   : separator liquid (in2)
        #  [8] mixer → sink    : outlet / injection pressure BC
        conns = [
            Connection(src, "out1", valve, "in1"),  # [0]
            Connection(valve, "out1", sep, "in1"),  # [1]
            Connection(sep, "out1", pump2, "in1"),  # [2]
            Connection(sep, "out2", turb, "in1"),  # [3]
            Connection(turb, "out1", cond, "in1"),  # [4]
            Connection(cond, "out1", pump, "in1"),  # [5]
            Connection(pump, "out1", mixer, "in1"),  # [6]
            Connection(pump2, "out1", mixer, "in2"),  # [7]
            Connection(mixer, "out1", sink, "in1"),  # [8]
        ]

        net = Network(p_unit="bar", T_unit="C", h_unit="kJ / kg", iterinfo=False)
        net.add_conns(*conns)

        # --- Component-level attributes from config ---
        turb_cfg = pp.get("turbine", {})
        pump_cfg = pp.get("pump", {})
        pump2_cfg = pp.get("pump2", {})

        if "efficiency" in turb_cfg:
            turb.set_attr(eta_s=float(turb_cfg["efficiency"]))
        if "efficiency" in pump_cfg:
            pump.set_attr(eta_s=float(pump_cfg["efficiency"]))
        if "efficiency" in pump2_cfg:
            pump2.set_attr(eta_s=float(pump2_cfg["efficiency"]))

        # --- Pre-compute fixed BC values (don't change between timesteps) ---
        valve_cfg = pp.get("valve", {})
        cond_cfg = pp.get("condenser", {})

        # Convert p_out_megapascals → bar (1 MPa = 10 bar)
        self._valve_p_bar: float = float(valve_cfg.get("p_out_megapascals", 0.05)) * 10.0
        self._turb_p_bar: float = float(turb_cfg.get("p_out_megapascals", 0.005)) * 10.0
        self._cond_p_bar: float = float(cond_cfg.get("p_out_megapascals", 0.005)) * 10.0
        self._cond_x_out: float = float(cond_cfg.get("vapor_mass_fraction_out", 0))
        self._cond_tower_mode: str = str(cond_cfg.get("cooling_tower_mode", "WET")).upper()
        self._cond_subtype: str = str(cond_cfg.get("subtype", "condenser")).lower()

        # --- Store references needed by solve() ---
        self._network: Network = net
        self._conns: list[Any] = conns
        self._turbine: Turbine = turb
        self._pump: Compressor = pump
        self._pump2: Compressor = pump2
        self._condenser: SimpleHeatExchanger = cond

    # ------------------------------------------------------------------
    # BC variable accessor — SystemBCIteration calls this each iteration
    # ------------------------------------------------------------------

    def set_injection_pressure(self, P: float) -> None:
        """Update the injection pressure BC variable (Pa)."""
        self.injection_pressure = P

    def get_injection_pressure(self) -> float:
        """Return the current injection pressure BC variable (Pa)."""
        return self.injection_pressure

    # ------------------------------------------------------------------
    # record / solve
    # ------------------------------------------------------------------

    def record(self, timestep: int) -> None:
        """Append state to history if save_interval permits."""
        if self.save_interval is None:
            return
        if timestep % self.save_interval == 0:
            self.history.record(self.state)

    def solve(self) -> None:
        """Solve TESPy single-flash network and extract outlet conditions + power."""
        s = self.state
        s.mark_all_stale()

        s.T_inlet.update(self.inlet.T)
        s.P_inlet.update(self.inlet.P)
        s.mass_rate.update(self.inlet.mass_rate)

        T_in = s.T_inlet.get_fresh()
        P_in = s.P_inlet.get_fresh()
        mdot = s.mass_rate.get_fresh()

        conns = self._conns

        # ---- Surface pipe friction drop (wellhead → plant) ----
        # Matches src/tango/ SurfaceUnitFlexiblePP._update_state_pipe():
        # Haaland friction over well_spacing length, evaluated at inlet conditions.
        rho_in = water_density(T_in, P_in)
        mu_in = water_viscosity(T_in, P_in)
        u_in = mean_velocity(mdot, rho_in, self.pipe_diameter)
        Re_in = reynolds_number(mdot, self.pipe_diameter, mu_in)
        ff_in = friction_factor_haaland(Re_in, self.pipe_diameter, self.pipe_roughness)
        dp_pipe = pressure_drop_friction(ff_in, self.well_spacing, self.pipe_diameter, rho_in, u_in)
        P_tespy_in = P_in - dp_pipe
        s.dP_pipe.update(dp_pipe)
        s.P_tespy_inlet.update(P_tespy_in)

        # ---- Inlet connection: T (°C), p (bar), m (kg/s), fluid ----
        conns[0].set_attr(
            fluid={self.inlet.fluid_name: 1},
            m=mdot,
            T=T_in + _K_TO_C,
            p=P_tespy_in * _PA_TO_BAR,
        )

        # ---- Fixed component pressures ----
        conns[1].set_attr(p=self._valve_p_bar)  # flash valve outlet
        conns[4].set_attr(p=self._turb_p_bar)  # turbine exhaust
        conns[5].set_attr(p=self._cond_p_bar, x=self._cond_x_out)  # condenser outlet

        # ---- Outlet / injection pressure BC ----
        conns[8].set_attr(p=self.injection_pressure * _PA_TO_BAR)

        # ---- Solve ----
        self._network.solve("design")

        # ---- Extract outlet conditions ----
        T_out = conns[8].T.val + _C_TO_K
        P_out = conns[8].p.val * _BAR_TO_PA
        s.T_outlet.update(T_out)
        s.P_outlet.update(P_out)

        # ---- Flash diagnostics (from valve → separator connection) ----
        s.P_flash_Pa.update(conns[1].p.val * _BAR_TO_PA)
        s.T_flash_K.update(conns[1].T.val + _C_TO_K)

        # Steam fraction = vapor mass flow / total mass flow at separator
        # sep.out2 (vapor) mass / total
        if mdot > 0:
            # TESPy connection [3] carries the vapor stream
            s.steam_fraction.update(conns[3].m.val / mdot)
        else:
            s.steam_fraction.update(float("nan"))

        # ---- Power balance (TESPy P.val in Watts; turbine P < 0, compressor P > 0) ----
        # TESPy stores power in SI (W) regardless of h_unit="kJ/kg" display setting.
        gross_W = -self._turbine.P.val  # negate: turbine produces power (P < 0 in TESPy)
        pump_W = self._pump.P.val  # positive: compressor consumes power
        pump2_W = self._pump2.P.val
        cooling_W = self._compute_cooling_tower_parasitic()

        s.gross_turbine_power_W.update(gross_W)
        s.pump_power_W.update(pump_W)
        s.pump2_power_W.update(pump2_W)
        s.cooling_tower_power_W.update(cooling_W)
        s.gross_power_watts.update(gross_W)  # alias for tests/plots
        s.net_power_W.update(gross_W - pump_W - pump2_W - cooling_W)

        # ---- Fluid properties for injection stream ----
        rho_out = water_density(T_out, P_out)
        mu_out = water_viscosity(T_out, P_out)
        s.rho.update(rho_out)
        s.mu.update(mu_out)

        self.outlet.T = T_out
        self.outlet.P = P_out
        self.outlet.mass_rate = mdot
        self.outlet.rho = rho_out
        self.outlet.mu = mu_out
        self.outlet.fluid_name = self.inlet.fluid_name

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_cooling_tower_parasitic(self) -> float:
        """Return cooling tower parasitic power (W) via the BAC regression model.

        Matches old tango's PowerPlant.compute_cooler_condenser_power() for the
        single condenser case.  Q_condenser from TESPy is negative (heat rejected);
        negating it gives a positive heat load (W).
        """
        if self._cond_tower_mode not in _BAC_COEFFS:
            raise ValueError(f"Unsupported cooling_tower_mode: {self._cond_tower_mode!r}")

        subtype = self._cond_subtype
        if subtype not in _BAC_COEFFS[self._cond_tower_mode]:
            return 0.0

        coeffs = _BAC_COEFFS[self._cond_tower_mode][subtype]
        f = self._bac_regression(coeffs)
        q_condenser_W = -self._condenser.Q.val  # negate: Q < 0 in TESPy for heat rejection
        return q_condenser_W * f

    def _bac_regression(self, coeffs: list[float]) -> float:
        """BAC parasitic power fraction f (dimensionless).

        f = a/ΔT_approach + b·T_amb + c·T_amb/ΔT_approach + d/(ΔT_approach + ΔT_range)

        T_amb in K, ΔT_approach in K (same as °C for a delta).
        ΔT_range defaults to 0 (not in tango_next config).
        """
        a, b, c, d = coeffs
        T_amb = self.surface_temperature  # K
        dT_app = self.approach_temperature  # K
        dT_range = 0.0
        return a / dT_app + b * T_amb + c * T_amb / dT_app + d / (dT_app + dT_range)
