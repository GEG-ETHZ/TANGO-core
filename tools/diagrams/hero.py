# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""The hero: the question TANGO answers, what you describe, the one coupled system, and what you get.

Prints draw.io XML; ``build.py`` exports it to ``docs/diagrams/hero.drawio.svg``. It sits under the banner
in the README and on the docs home. Same recipe as the other GEG heroes: a kicker, a headline, three
columns of tiles with curved connectors, a legend.
"""

from pathlib import Path

from drawio import GRADIENT, HAIR, INK, INK2, MUTED, ROLE, Doc
from system_key import KEY_W, draw_key

HERE = Path(__file__).parent
W, H = 1300, 760
M = 56
d = Doc(W, H)
d.frame()

WORDMARK = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="34" viewBox="0 0 120 34">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0">'
    f'<stop offset="0" stop-color="{GRADIENT[0]}"/><stop offset="0.5" stop-color="#7D4FB0"/>'
    f'<stop offset="1" stop-color="{GRADIENT[1]}"/></linearGradient></defs>'
    '<text x="0" y="27" font-family="Helvetica, Arial, sans-serif" font-size="28" font-weight="800" '
    'letter-spacing="-0.5" fill="url(#g)">TANGO</text></svg>'
)

# ---- kicker, headline, one line under it
d.rect(M, 46, 8, 8, fill=GRADIENT[0], stroke="none", r=4, gradientColor=GRADIENT[1], gradientDirection="east")
d.text(
    M + 18,
    40,
    "TECHNO-ECONOMIC SIMULATION OF GEOTHERMAL ENERGY SYSTEMS",
    12,
    MUTED,
    bold=True,
    w=700,
    h=20,
    spacing=2,
)
d.text(
    M,
    70,
    "What will a geothermal project's electricity or heat cost over its life?",
    31,
    INK,
    bold=True,
    w=W - 2 * M,
    h=48,
)
d.text(
    M,
    124,
    "TANGO models the surface plant, the wells, the reservoir and the economics as one coupled system\n"
    "and solves it over the project's lifetime, for your own site, plant and cost assumptions.",
    15,
    MUTED,
    w=W - 2 * M,
    h=44,
    valign="top",
)

# ---- three columns
LW, RW = 320, 320
CWD = KEY_W + 80  # the pictogram plus its padding, no more
GAP = (W - 2 * M - LW - CWD - RW) / 2
CX = M + LW + GAP
RX = CX + CWD + GAP
HEAD_Y = 192
for x, s_ in ((M, "YOU DESCRIBE"), (CX, "ONE COUPLED SYSTEM"), (RX, "YOU GET")):
    d.text(x, HEAD_Y, s_, 11, MUTED, bold=True, w=300, h=18, spacing=1.5)

# the center tile: the pictogram, the wordmark, the four system types
TY0, TH0 = HEAD_Y + 30, 468
d.tile(CX, TY0, CWD, TH0)
d.svg_image(CX + CWD - 24 - 108, TY0 + 18, 108, 31, WORDMARK)
key_x = CX + (CWD - KEY_W) / 2
pos = draw_key(d, key_x, TY0 + 28, 1.0, detail=True)
TTW = 88
TTH = round(TTW * 179 / 240)
row_w = 4 * TTW + 3 * 12
tx0 = CX + (CWD - row_w) / 2
ty = TY0 + TH0 - 24 - TTH
d.text(tx0, ty - 22, "FOUR SYSTEM TYPES", 11, MUTED, bold=True, w=row_w, h=18, spacing=1.5)
for k, name in enumerate(("Hydrothermal", "CPG", "EGS", "AGS")):
    tx = tx0 + k * (TTW + 12)
    d.image(tx, ty, TTW, TTH, HERE / "thumbnails" / f"{name.lower()}.jpg")
    d.rect(
        tx,
        ty,
        TTW,
        16,
        fill="#FFFFFF",
        stroke="none",
        r=0,
        label=name,
        fontSize=9,
        fontStyle=1,
        fontColor=INK,
        align="center",
        verticalAlign="middle",
    )
    d.rect(tx, ty, TTW, TTH, fill="none", stroke="#3C4043", sw=1.5, r=6)

# the left tiles: what you describe, one per part, in its color
LEFT = [
    (
        "surface",
        "Surface plant",
        "flash, ORC or heat exchanger, as a plant graph;\ninjection pressure, pipes",
    ),
    ("well", "Wells", "length, diameter, roughness, pump"),
    ("reservoir", "Reservoir", "depth, thickness, permeability, temperature"),
    ("economic", "Economics", "discount rate, project maturity, cost models"),
]
TH1, G1 = 84, 14
col_h = len(LEFT) * TH1 + (len(LEFT) - 1) * G1
y = TY0 + (TH0 - col_h) / 2
for kind, title, desc in LEFT:
    stroke, fill, ink = ROLE[kind]
    d.tile(M, y, LW, TH1, fill=fill, stroke=stroke, sw=1.5)
    d.text(M + 18, y + 12, title, 15, ink, bold=True, w=LW - 36, h=22)
    d.text(M + 18, y + 38, desc, 12, INK2, w=LW - 36, h=34, valign="top")
    d.gradient_arrow(M + LW + 2, y + TH1 / 2 - 11, GAP - 4, direction="right")
    y += TH1 + G1

# the right tiles: what you get, tagged with the parts it comes from
RIGHT = [
    ("LCOE or LCOH", "the levelized cost of electricity or heat", ["economic"]),
    ("Net electric and thermal power", "over the project's lifetime", ["surface"]),
    ("Temperature, pressure, flow", "for every part, every timestep", ["well", "reservoir", "surface"]),
    ("The best designs", "from sweeps and optimization", []),
]
y = TY0 + (TH0 - col_h) / 2
for title, desc, dots in RIGHT:
    d.tile(RX, y, RW, TH1)
    dx = RX + 18
    for k2 in dots:
        d.rect(dx, y + 18, 11, 11, fill=ROLE[k2][0], stroke="none", r=6)
        dx += 15
    d.text(dx + (4 if dots else 0), y + 12, title, 15, INK, bold=True, w=RW - (dx - RX) - 18, h=22)
    d.text(RX + 18, y + 38, desc, 12, INK2, w=RW - 36, h=18)
    d.gradient_arrow(CX + CWD + 2, y + TH1 / 2 - 11, GAP - 4, direction="right")
    y += TH1 + G1

# ---- legend
ly = TY0 + TH0 + 30
lx = M
for kind, label in (
    ("surface", "surface plant"),
    ("well", "wells"),
    ("reservoir", "reservoir"),
    ("economic", "economics"),
):
    stroke, fill, _ = ROLE[kind]
    d.rect(lx, ly + 3, 12, 12, fill=fill, stroke=stroke, sw=1.5, r=3)
    d.text(lx + 18, ly, label, 12, INK2, w=120, h=18)
    lx += 18 + len(label) * 6.5 + 28
d.text(
    W - M - 480,
    ly,
    "One color per part, the same in every diagram and in the code.",
    12,
    MUTED,
    w=480,
    h=18,
    align="right",
)
d.rect(0, H - 1, W, 1, fill=HAIR, stroke="none", r=0)

print(d.xml("hero"))
