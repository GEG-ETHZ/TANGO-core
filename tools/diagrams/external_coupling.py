# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""How TANGO drives an external model, with RAFT as the example: the boundary conditions each way, trial
and accept, RAFT's own steps inside a sync interval, and how RAFT's state becomes TANGO state.

Prints draw.io XML; ``build.py`` exports it to ``docs/diagrams/external-coupling.drawio.svg``, shown on
``docs/runtime/external-coupling.md``.

Color rule: the well component and RAFT, which stands in for it, carry the well's purple; everything else
is neutral. RAFT is outside TANGO, so it is dashed and reached through the ``RaftWrapper`` connector chip.
"""

from drawio import HAIR, INK, INK2, MUTED, ROLE, Doc

W, H = 900, 540
M = 24
d = Doc(W, H)
d.frame()

PURPLE, LILAC, _ = ROLE["well"]
TITLE, BODY, SMALL = 18, 15, 14

# ---- columns
L, LW = M, 340  # TANGO side
RX = 610  # RAFT box
RW = W - M - RX
d.text(L, 10, "IN TANGO", 13, MUTED, bold=True, w=200, h=20)
d.text(RX, 10, "OUTSIDE TANGO", 13, MUTED, bold=True, w=200, h=20)


def tile(
    y: float,
    h: float,
    name: str,
    desc: str,
    fill: str = "#FFFFFF",
    stroke: str = HAIR,
    ink: str = INK,
) -> None:
    """A TANGO-side card: a monospaced name over a short description."""
    d.tile(L, y, LW, h, fill=fill, stroke=stroke, sw=1.5 if stroke != HAIR else 1, r=14)
    d.text(L + 18, y + 14, name, TITLE - 1, ink, bold=True, mono=True, w=LW - 36, h=24)
    lines = desc.count("\n") + 1
    d.text(L + 18, y + 46, desc, BODY, INK2, w=LW - 36, h=21 * lines, valign="top")


def down(x: float, y0: float, y1: float, label: str) -> None:
    """A plain arrow straight down with a label to its right."""
    d.edge([(x, y0), (x, y1)], color=MUTED, sw=2)
    d.text(x + 10, y0 + 6, label, SMALL, INK2, w=150, h=40, valign="top")


# ---- TANGO side: the orchestrator, the component, its state
AY, AH = 40, 100
BY, BH = 220, 110
CY, CH = 420, 100
tile(AY, AH, "SystemBCIteration", "re-solves each sync interval until\n|Δh| < 1 kJ/kg and |ΔP| < 1 kPa")
down(L + 70, AY + AH, BY, "each pass:\nsolve()")
down(L + 220, AY + AH, BY, "once converged:\naccept()")
tile(
    BY,
    BH,
    "RaftGroupedSubsurface",
    "grouped_subsurface · raft\nkeeps_external_state: one\nstep per sync interval",
    fill=LILAC,
    stroke=PURPLE,
    ink=PURPLE,
)
down(L + 70, BY + BH, CY, "record()")
tile(CY, CH, "RaftWrapperState", "one LockedState per field, into\nthe history and results.yml/smry.csv")

# ---- the connector on the component's edge
PW, PH = 128, 32
PX = L + LW - PW / 2
BCY = BY + BH / 2
d.chip(PX, BCY - PH / 2, "RaftWrapper", "neutral", w=PW, h=PH, size=SMALL)

# ---- boundary conditions across the interface
AX0, AX1 = PX + PW + 6, RX - 6
GAP = AX1 - AX0
d.text(
    AX0,
    BCY - 66,
    "ṁ, T at the inlet\nP at the outlet",
    SMALL,
    INK,
    bold=True,
    w=GAP,
    h=40,
    align="center",
)
d.gradient_arrow(AX0, BCY - 24, GAP, direction="right", thickness=16, shaft=5)
d.gradient_arrow(AX0, BCY + 8, GAP, direction="left", thickness=16, shaft=5)
d.text(
    AX0,
    BCY + 30,
    "P at the inlet\nT, ṁ at the outlet",
    SMALL,
    INK,
    bold=True,
    w=GAP,
    h=40,
    align="center",
)

# ---- what RAFT exposes, into TANGO state
SY = CY + CH / 2
d.edge([(RX - 2, SY), (L + LW + 4, SY)], color=MUTED, sw=2)
d.text(
    L + LW + 12,
    SY - 48,
    "copied into\nTANGO state",
    SMALL,
    INK,
    bold=True,
    w=RX - L - LW - 24,
    h=40,
    align="center",
)

# ---- RAFT, outside TANGO
d.rect(RX, AY, RW, CY + CH - AY, fill="#FFFFFF", stroke=PURPLE, sw=1.5, r=16, dashed=True)
d.text(RX + 18, AY + 14, "RAFT", TITLE + 2, PURPLE, bold=True, w=80, h=26)
d.text(RX + 18, AY + 44, "wells and rock, 3D finite elements", SMALL, MUTED, w=RW - 36, h=20)

# trial and accept: every trial starts from the accepted state; get_fresh() keeps the last one
TY = AY + 120
d.text(RX + 18, TY - 34, "TRIAL AND ACCEPT", 12, MUTED, bold=True, w=RW - 36, h=18)
S0 = (RX + 34, TY + 30)
S1 = (RX + RW - 34, TY + 30)
for dy in (-26, 0, 26):
    d.edge([(S0[0] + 10, S0[1]), (RX + RW / 2 + 10, S0[1] + dy)], color=PURPLE, sw=2, dashed=True, size=9)
d.edge([(RX + RW / 2 + 22, S0[1] + 26), (S1[0] - 10, S1[1])], color=PURPLE, sw=2, size=9)
for (cx, cy), label in ((S0, "accepted"), (S1, "t_end")):
    d.rect(cx - 8, cy - 8, 16, 16, fill=PURPLE, stroke="none", r=8)
    d.text(cx - 50, cy + 14, label, SMALL, INK2, w=100, h=20, align="center")
d.text(RX + RW / 2 - 20, TY - 14, "trials", SMALL, INK2, w=60, h=18, align="center")
d.text(
    RX + 18,
    TY + 82,
    "every solve() starts from the\naccepted state; get_fresh()\nkeeps the last trial",
    SMALL,
    INK2,
    w=RW - 36,
    h=62,
    valign="top",
)

# RAFT's own clock: adaptive steps that land on t_end
KY = BY + BH + 18
d.text(RX + 18, KY - 22, "OWN STEPS", 12, MUTED, bold=True, w=RW - 36, h=18)
X0, X1 = RX + 30, RX + RW - 30
d.edge([(X0, KY + 14), (X1, KY + 14)], color=INK2, sw=2, end="none")
for f in (0.0, 0.06, 0.14, 0.26, 0.42, 0.62, 0.82, 1.0):
    x = X0 + f * (X1 - X0)
    tall = f in (0.0, 1.0)
    d.rect(
        x - 1,
        KY + (2 if tall else 7),
        2,
        24 if tall else 14,
        fill=PURPLE if not tall else INK,
        stroke="none",
        r=0,
    )
d.text(X0 - 30, KY + 30, "t_start", SMALL, INK2, w=60, h=20, align="center")
d.text(X1 - 30, KY + 30, "t_end", SMALL, INK2, w=60, h=20, align="center")
d.text(RX + 18, KY + 56, "adaptive, clamped to t_end", SMALL, INK2, w=RW - 36, h=20)

# what RAFT exposes through its API, beside the arrow that carries it into TANGO state
d.text(RX + 18, SY - 30, "EXPOSES", 12, MUTED, bold=True, w=RW - 36, h=18)
d.text(RX + 18, SY - 8, "solve_stats, well_profiles()", SMALL, INK2, w=RW - 36, h=20)

print(d.xml("external-coupling"))
