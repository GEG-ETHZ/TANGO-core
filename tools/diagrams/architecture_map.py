"""How the code is organized: the tango package, the clients that can connect to it from outside, and,
below it, the libraries it uses and the external simulators a connector would reach.

Prints draw.io XML; ``build.py`` exports it to ``docs/diagrams/architecture-map.drawio.svg``.

Color rule: component types carry their identity color; every other module is neutral. What is drawn
outside the TANGO core box is not part of TANGO. Every arrow runs straight, as a gradient shape.
"""

from drawio import GRADIENT, HAIR, INK, INK2, MUTED, ROLE, Doc
from parts import CONNECTOR, PARTS
from system_key import draw_key

W = 1280
AT, AS = 14, 4  # arrow thickness and shaft
d = Doc(W, 1500)
d.frame()

WORDMARK = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="34" viewBox="0 0 120 34">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0">'
    f'<stop offset="0" stop-color="{GRADIENT[0]}"/><stop offset="0.5" stop-color="#7D4FB0"/>'
    f'<stop offset="1" stop-color="{GRADIENT[1]}"/></linearGradient></defs>'
    '<text x="0" y="27" font-family="Helvetica, Arial, sans-serif" font-size="28" font-weight="800" '
    'letter-spacing="-0.5" fill="url(#g)">TANGO</text></svg>'
)


def pill(x: float, y: float, w: float, h: float, name: str, desc: str, mono_name: bool = True) -> None:
    """A neutral module pill with its name and one description."""
    d.rect(x, y, w, h, fill="#FFFFFF", stroke=HAIR, sw=1, r=12)
    d.text(x + 16, y + 12, name, 15, INK, bold=True, mono=mono_name, w=w - 32, h=20)
    d.text(x + 16, y + 38, desc, 12, INK2, w=w - 32, h=16 * (desc.count("\n") + 1), valign="top")


def outside(x: float, y: float, w: float, h: float, title: str, desc: str) -> None:
    """A dashed box for something that is not part of TANGO."""
    d.rect(x, y, w, h, fill="#FFFFFF", stroke="#9AA0A6", sw=1.5, r=12, dashed=True)
    d.text(x + 16, y + 12, title, 15, INK, bold=True, w=w - 32, h=20)
    d.text(x + 16, y + 38, desc, 12, MUTED, w=w - 32, h=16 * (desc.count("\n") + 1), valign="top")


def down(x: float, y0: float, y1: float, label: str = "") -> None:
    """A gradient arrow straight down from y0 to y1, centered on x, with an optional label beside it."""
    d.gradient_arrow(x - AT / 2, y0, y1 - y0, direction="down", thickness=AT, shaft=AS)
    if label:
        d.text(x + AT / 2 + 8, (y0 + y1) / 2 - 10, label, 12, INK2, bold=True, w=160, h=20)


# ---- what can connect from outside: a web app, an assistant, a data store
M = 48
OY, OH = 24, 86
CW3 = (W - 2 * M - 2 * 24) / 3
CLIENTS = [
    ("Web app", "a web front end that drives TANGO"),
    ("AI assistant", "drives TANGO through its command line\nor its Python API, like any other client"),
    ("Data store", "data for TANGO, such as reservoir\nconfigurations, proprietary or open"),
]
for k, (title, desc) in enumerate(CLIENTS):
    outside(M + k * (CW3 + 24), OY, CW3, OH, title, desc)

# ---- the package: rows from the entry points down to core, each arrow straight
CX, CY, CBW = M, OY + OH + 56, W - 2 * M
IX, IW = CX + 24, CBW - 48
AY, AH = CY + 72, 76  # entry points
BY, BH = AY + AH + 40, 72  # workflows
OY2, OH2 = BY + BH + 40, 72  # orchestrators
KY = OY2 + OH2 + 40  # components
PH, PG = 72, 12
KH = 48 + 3 * PH + 2 * PG + 16
DY, DH = KY + KH + 40, 72  # core
CB = DY + DH + 24
d.rect(CX, CY, CBW, CB - CY, fill="#F8F9FA", stroke="#3C4043", sw=1.5, r=20)
d.tab(CX, CY, CBW, r=20)
d.svg_image(CX + 24, CY + 24, 120, 34, WORDMARK)
d.text(CX + 136, CY + 28, "core", 22, INK, bold=True, w=80, h=28)
d.text(CX + 210, CY + 34, "src/tango  ·  this repository", 12, MUTED, mono=True, w=300, h=18)
for k in range(3):
    down(M + k * (CW3 + 24) + CW3 / 2, OY + OH + 2, CY - 2)

A2 = (IW - 36) / 2
pill(IX, AY, A2, AH, "tango_cli", "command line: run · validate · init; writes the results (results_export)")
pill(
    IX + A2 + 36,
    AY,
    A2,
    AH,
    "pymoo_api",
    "optimization: NSGA-II over full runs",
)
pill(IX, BY, IW, BH, "workflows", "Workflow: reads the config, builds the components, runs them")
pill(
    IX,
    OY2,
    IW,
    OH2,
    "orchestrators",
    "SystemDirect: one pass per timestep  ·  SystemBCIteration: the solver loop",
)
down(IX + A2 / 2, AY + AH + 2, BY - 2)
down(IX + A2 + 36 + A2 / 2, AY + AH + 2, BY - 2)
down(IX + IW / 2, BY + BH + 2, OY2 - 2)

# components, ordered like the pictogram, economics to the right; the pictogram beside it
KEY_S = 0.7
KW = 780
d.rect(IX, KY, KW, KH, fill="#FFFFFF", stroke="#9AA0A6", sw=1.5, r=14)
d.text(IX + 16, KY + 14, "components", 15, INK, bold=True, mono=True, w=200, h=20)
d.text(IX + 140, KY + 16, "registry.py maps (type, variant) to a class", 12, MUTED, w=400, h=18)
down(IX + KW / 2, OY2 + OH2 + 2, KY - 2)
ECON_W = 250
LEFT_W = KW - 48 - ECON_W - 32
DESC = {
    "surface": "the surface plant, a TESPy network",
    "well": "injection, production and horizontal wells",
    "reservoir": "the reservoir between the wells",
}
built = {kind: b for kind, b, _ in PARTS}
for k, name in enumerate(("surface", "well", "reservoir")):
    sx, sy = IX + 16, KY + 48 + k * (PH + PG)
    stroke, fill, ink = ROLE[name]
    d.rect(sx, sy, LEFT_W, PH, fill=fill, stroke=stroke, sw=1, r=12)
    d.text(sx + 16, sy + 10, name, 15, ink, bold=True, mono=True, w=100, h=20)
    d.text(sx + 110, sy + 12, DESC[name], 12, INK2, w=LEFT_W - 126, h=18)
    cx = sx + 16
    for s in built[name]:
        cx += d.chip(cx, sy + 40, s, name) + 8
    d.chip(cx + 8, sy + 40, CONNECTOR, "neutral", w=86)
    if name != "reservoir":
        d.gradient_arrow(
            sx + LEFT_W + 2,
            sy + PH / 2 - AT / 2,
            28,
            direction="right",
            thickness=AT,
            shaft=AS,
            colors=(stroke, stroke),
        )
ex_, ey_ = IX + 16 + LEFT_W + 32, KY + 48
eh_ = 3 * PH + 2 * PG
stroke, fill, ink = ROLE["economic"]
d.rect(ex_, ey_, ECON_W, eh_, fill=fill, stroke=stroke, sw=1, r=12)
d.text(ex_ + 16, ey_ + 10, "economic", 15, ink, bold=True, mono=True, w=120, h=20)
d.text(
    ex_ + 16,
    ey_ + 36,
    "CAPEX, OPEX, LCOE or LCOH,\nonce after the last timestep",
    12,
    INK2,
    w=ECON_W - 32,
    h=34,
    valign="top",
)
d.text(ex_ + 16, ey_ + 84, "reads", 12, MUTED, w=40, h=22)
d.chip(ex_ + 62, ey_ + 84, "well: geometry, pump power", "well", size=11, h=22, w=170)
d.chip(ex_ + 62, ey_ + 114, "surface: equipment", "surface", size=11, h=22, w=140)
kx = IX + KW + 48
d.text(kx, KY + 2, "One color per component type", 12, MUTED, bold=True, w=240, h=16)
draw_key(d, kx - 4, KY + 22, KEY_S, detail=False)

pill(
    IX,
    DY,
    KW,
    DH,
    "core",
    "Component, Stream, LockedState, config schemas, errors, fluid properties, solvers",
)
down(IX + 200, KY + KH + 2, DY - 2)

# ---- below the package, outside TANGO: the libraries it uses and the simulators a connector would reach
LY, LH = CB + 64, 172
LIB_W = 420
outside(
    IX,
    LY,
    LIB_W,
    LH,
    "TESPy · CoolProp",
    "Libraries used in-process: TESPy solves the\nsurface plant's network, CoolProp supplies\nevery fluid property.",
)
EX = IX + LIB_W + 40
EW = IX + IW - EX
outside(
    EX,
    LY,
    EW,
    LH,
    "External simulators",
    "reached through a connector: TANGO's adapter class, registered as a variant",
)
ry = LY + 72
for kind, _, external in PARTS:
    if not external:
        continue
    cx = EX + 16
    d.text(cx, ry + 2, kind, 12, ROLE[kind][2], bold=True, mono=True, w=80, h=22)
    cx += 90
    for s_ in external:
        cx += d.chip(cx, ry, s_, kind, dashed=True, w=round(len(s_) * 12 * 0.62 + 24), h=24, size=12) + 8
    ry += 30
down(IX + 110, CB + 2, LY - 2, "core → CoolProp")
down(IX + 300, CB + 2, LY - 2, "surface → TESPy")
down(EX + EW / 2, CB + 2, LY - 2, "connector")

d.h = LY + LH + 24
d.cells[0] = d.cells[0].replace('height="1500"', f'height="{d.h}"')
print(d.xml("architecture-map"))
