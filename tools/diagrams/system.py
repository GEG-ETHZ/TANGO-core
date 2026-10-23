"""What TANGO models: sweeps and optimization around one simulation, one simulation around the system,
what each part takes in and gives out, and, in a box of their own, the external simulators a connector
could reach.

Prints draw.io XML; ``build.py`` exports it to ``docs/diagrams/tango-couples-every-model.drawio.svg``.

Inputs and outputs follow the config keys and the recorded histories (example_configs/hydro_sf_electric.yml,
core/specs.py, the *History classes, economic/doublet.py), checked 2026-10-21.
"""

from pathlib import Path

from drawio import GRADIENT, HAIR, INK, INK2, MUTED, ROLE, Doc
from loop import LOOP_SVG
from parts import CONNECTOR, PARTS
from system_key import BOXES, CENTER, SLIDE_X0, SLIDE_Y0

HERE = Path(__file__).parent
PLANT, WELLS, RES = ROLE["surface"][0], ROLE["well"][0], ROLE["reservoir"][0]
GREYED, BUS = "#9AA0A6", "#80868B"
W = 1600
TEXT = 13
LINE = 19


WORDMARK = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="34" viewBox="0 0 120 34">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0">'
    f'<stop offset="0" stop-color="{GRADIENT[0]}"/><stop offset="0.5" stop-color="#7D4FB0"/>'
    f'<stop offset="1" stop-color="{GRADIENT[1]}"/></linearGradient></defs>'
    '<text x="0" y="27" font-family="Helvetica, Arial, sans-serif" font-size="28" font-weight="800" '
    'letter-spacing="-0.5" fill="url(#g)">TANGO</text></svg>'
)


def box(
    d: Doc,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    sub: str,
    fill: str,
    stroke: str,
    sw: float = 1.0,
    mono_sub: bool = True,
    dashed: bool = False,
    tab: bool = False,
) -> None:
    """A labelled container; the label sits in its top-left corner, under the gradient tab if it has one."""
    d.rect(x, y, w, h, fill=fill, stroke=stroke, sw=sw, r=16, dashed=dashed)
    if tab:
        d.tab(x, y, w, fill=fill)
    dy = 14 if tab else 0
    d.text(x + 18, y + 10 + dy, title, 14, INK, bold=True, w=240, h=20)
    d.text(x + 18 + len(title) * 9 + 10, y + 12 + dy, sub, 11, MUTED, mono=mono_sub, w=460, h=18)


# ---- geometry, from the outside in
EX, EY0, EW = 48, 24, 196  # external simulators, in a box of their own
OX, OY, OR = EX + EW + 30, 24, 1552  # sweeps and optimization
IX, IY, IR = OX + 18, OY + 58, OR - 18  # one simulation
SX, SY = IX + 18, IY + 44  # the system

S = 0.62
STACK_X, STACK_TOP = SX + 16, SY + 44
OXS, OYS = STACK_X - SLIDE_X0 * S, STACK_TOP - SLIDE_Y0 * S
BW = round(490 * S)


def sx(v: float) -> float:
    """Slide x to canvas x."""
    return round(OXS + v * S, 1)


def sy(v: float) -> float:
    """Slide y to canvas y."""
    return round(OYS + v * S, 1)


STACK_R = sx(40) + BW
ECON_X, ECON_W = STACK_R + 48, 176  # economics, to the right of the stack
ECON_Y0, ECON_Y1 = sy(110), sy(470)
TYPES_Y = sy(760) + 64  # system types, set apart underneath
TW = 100
TH = round(TW * 179 / 240)
SR = ECON_X + ECON_W + 16
SB = TYPES_Y + TH + 28

TX0 = SR + 28  # the table, to the right of the system
COL_W = (IR - 16 - TX0 - 24) / 2
IN_X, OUT_X = TX0, TX0 + COL_W + 24
# what goes in and what comes out, in broad categories; dots name the parts each one touches
TAKES_IN = [
    (
        "Subsurface",
        ["reservoir", "well"],
        "temperature and pressure at depth, rock and fluid\nproperties, well depth and layout",
    ),
    ("Surface", ["surface"], "plant design, ambient conditions,\ninjection pressure"),
    ("Economics", ["economic"], "discount rate, project maturity, cost models"),
    ("Run", [], "timesteps, mass rate, injection mode"),
]
GIVES_OUT = [
    ("Energy", ["surface"], "net electric and thermal power\nover the project life"),
    ("Fluid", ["well", "reservoir"], "temperature, pressure and flow, every part,\nevery timestep"),
    ("Economics", ["economic"], "CAPEX by category, OPEX, LCOE or LCOH"),
    ("Files", [], "a per-timestep CSV, the solved config"),
]
IB = SB + 24
BAND_Y, BAND_H = IB + 44, 100
OB = BAND_Y + BAND_H + 18
H = OB + 24

d = Doc(W, H)
d.frame()

# ---- the boxes
box(
    d,
    OX,
    OY,
    OR - OX,
    OB - OY,
    "Many simulations",
    "a sweep or an optimization calls one simulation per design, in parallel",
    "#FFFFFF",
    HAIR,
    mono_sub=False,
    tab=True,
)
d.svg_image(OR - 24 - 108, OY + 22, 108, 31, WORDMARK)
box(
    d,
    IX,
    IY,
    IR - IX,
    IB - IY,
    "One simulation",
    "Workflow: the config in, the results out  ·  workflows/  ·  orchestrators/",
    "#F8F9FA",
    HAIR,
    mono_sub=False,
)
d.rect(SX, SY, SR - SX, SB - SY, fill="#FFFFFF", stroke="#9AA0A6", sw=1, r=16)
d.text(SX + 16, SY + 10, "The system", 14, INK, bold=True, w=200, h=20)
d.text(SX + 16 + 100, SY + 12, "components/", 11, MUTED, mono=True, w=200, h=18)
box(d, EX, EY0, EW, SB - EY0, "External simulators", "", "#FFFFFF", "#9AA0A6", sw=1.5, dashed=True)
d.text(
    EX + 18,
    EY0 + 34,
    "outside TANGO, reached\nthrough a connector",
    11,
    MUTED,
    w=EW - 36,
    h=32,
    valign="top",
)

# ---- the stack
for kind, (y0, y1) in BOXES.items():
    stroke, fill, _ = ROLE[kind]
    d.rect(sx(40), sy(y0), BW, round((y1 - y0) * S), fill=fill, stroke=stroke, sw=2, r=14)
d.svg_image(sx(40), sy(150), BW, round(490 * S), LOOP_SVG)


def chips_row(xc: float, y: float, items: list[tuple[str, str]]) -> None:
    """Chips centered on xc, each in its role's colors."""
    widths = [round(len(s) * 12 * 0.62 + 22) for s, _ in items]
    cx = xc - (sum(widths) + 8 * (len(widths) - 1)) / 2
    for (s_, role), w in zip(items, widths, strict=True):
        d.chip(cx, y, s_, role, w=w)
        cx += w + 8


built = {kind: b for kind, b, _ in PARTS}
d.text(sx(40), sy(48), "Surface plant", 17, PLANT, bold=True, align="center", w=BW, h=24)
chips_row(sx(40) + BW / 2, sy(48) + 30, [(s, "surface") for s in built["surface"]])
d.text(sx(40), sy(48) + 58, "components/surface", 10, PLANT, mono=True, align="center", w=BW, h=14)
d.text(sx(130), sy(300), "Wells", 17, WELLS, bold=True, align="center", w=round(310 * S), h=24)
chips_row(sx(130) + 310 * S / 2, sy(300) + 30, [(s, "well") for s in built["well"]])
d.text(sx(130), sy(300) + 58, "components/well", 10, WELLS, mono=True, align="center", w=round(310 * S), h=14)
d.text(sx(40), sy(608), "Reservoir", 17, RES, bold=True, align="center", w=BW, h=24)
chips_row(sx(40) + BW / 2, sy(608) + 30, [(s, "reservoir") for s in built["reservoir"]])
d.text(sx(40), sy(608) + 58, "components/reservoir", 10, RES, mono=True, align="center", w=BW, h=14)

# ---- economics to the right: priced from the wells and the surface plant, once at the end
es, ef, ei = ROLE["economic"]
d.rect(ECON_X, ECON_Y0, ECON_W, ECON_Y1 - ECON_Y0, fill=ef, stroke=es, sw=2, r=14)
ty = ECON_Y0 + 18
d.text(ECON_X, ty, "Economics", 17, ei, bold=True, align="center", w=ECON_W, h=24)
d.text(ECON_X, ty + 26, "components/economic", 10, ei, mono=True, align="center", w=ECON_W, h=14)
d.text(
    ECON_X,
    ty + 62,
    "CAPEX · OPEX\nLCOE or LCOH",
    13,
    ei,
    bold=True,
    align="center",
    w=ECON_W,
    h=40,
    valign="top",
)
d.text(
    ECON_X + 12,
    ty + 116,
    "priced from the wells\nand the surface plant,\nonce after the\nlast timestep",
    11.5,
    INK2,
    align="center",
    w=ECON_W - 24,
    h=64,
    valign="top",
)
for kind in ("surface", "well"):
    yy = sy(CENTER[kind])
    d.edge([(STACK_R + 2, yy), (ECON_X - 2, yy)], color=ROLE[kind][0], sw=2.5, size=9)

# ---- the four system types underneath
d.rect(SX + 16, sy(760) + 30, SR - SX - 32, 1, fill="#E8EAED", stroke="none", r=0)
d.text(sx(40), TYPES_Y - 24, "System types", 12, MUTED, bold=True, w=200, h=18)
d.text(sx(40) + 110, TYPES_Y - 24, "the same parts, arranged differently", 11, MUTED, w=300, h=18)
for k, name in enumerate(("Hydrothermal", "CPG", "EGS", "AGS")):
    tx = sx(40) + k * (TW + 12)
    d.image(tx, TYPES_Y, TW, TH, HERE / "thumbnails" / f"{name.lower()}.jpg")
    d.rect(
        tx,
        TYPES_Y,
        TW,
        18,
        fill="#FFFFFF",
        stroke="none",
        r=0,
        label=name,
        fontSize=10,
        fontStyle=1,
        fontColor=INK,
        align="center",
        verticalAlign="middle",
    )
    d.rect(tx, TYPES_Y, TW, TH, fill="none", stroke="#3C4043", sw=1.5, r=6)

# ---- the table: what goes in on the left, what comes out on the right
d.text(IN_X, SY + 10, "←  takes in", 15, INK, bold=True, w=COL_W, h=22)
d.text(OUT_X, SY + 10, "gives out  →", 15, INK, bold=True, w=COL_W, h=22)
for x, rows_ in ((IN_X, TAKES_IN), (OUT_X, GIVES_OUT)):
    y = SY + 48
    for name, dots, lines in rows_:
        d.rect(x, y - 10, COL_W, 1, fill="#E8EAED", stroke="none", r=0)
        dx = x
        for kind in dots:
            d.rect(dx, y + 5, 11, 11, fill=ROLE[kind][0], stroke="none", r=6)
            dx += 15
        if not dots:
            d.rect(dx, y + 5, 11, 11, fill="#DADCE0", stroke="none", r=6)
            dx += 15
        d.text(dx + 4, y, name, TEXT, INK, bold=True, w=COL_W - (dx - x) - 4, h=20)
        for i, line in enumerate(lines.split("\n")):
            d.text(x, y + 22 + LINE * i, line, TEXT, INK2, w=COL_W, h=LINE, valign="top")
        if name == "Files":
            d.doc(x + COL_W - 76, y + 16, 30, 34, "csv")
            d.doc(x + COL_W - 38, y + 16, 30, 34, "yml")
        y += 22 + LINE * (lines.count("\n") + 1) + 20

# ---- connectors leave each tile to the left, to the external simulators' box
PW, PH = 92, 24
RAIL = EX + EW - 14
for kind, _, external in PARTS:
    if not external:
        continue
    yc = sy(CENTER[kind])
    color = ROLE[kind][0]
    d.chip(sx(40) - PW + 18, yc - PH / 2, CONNECTOR, "neutral", w=PW, h=PH, size=12)
    d.edge([(sx(40) - PW + 16, yc), (RAIL, yc)], color=color, sw=1.5, end="none", dashed=True)
    n = len(external)
    step = 30
    top = yc - (step * n - 6) / 2
    if n > 1:
        d.edge(
            [(RAIL, top + 12), (RAIL, top + step * (n - 1) + 12)],
            color=color,
            sw=1.5,
            end="none",
            dashed=True,
        )
    for k, s_ in enumerate(external):
        cy = top + step * k
        cw = round(len(s_) * 12 * 0.62 + 24)
        d.edge([(RAIL - 10, cy + 12), (RAIL, cy + 12)], color=color, sw=1.5, end="none", dashed=True)
        d.chip(RAIL - 12 - cw, cy, s_, kind, dashed=True, w=cw, h=PH, size=12)

# ---- the two ways to run many: the cards span the band; a gradient arrow ties each to one simulation
RUNS = [
    ("Sweep", "applications/run_* · DVC"),
    ("Optimization", "pymoo_api · NSGA-II"),
]
CARD_Y = BAND_Y + 16
rx = OX + 18
rw = (OR - 18 - rx - (len(RUNS) - 1) * 24) / len(RUNS)
centers = []
for title, code in RUNS:
    d.rect(rx, CARD_Y, rw, 70, fill="#FFFFFF", stroke=HAIR, r=12)
    d.text(rx + 18, CARD_Y + 10, title, 14, INK, bold=True, w=rw - 36, h=20)
    d.text(rx + 18, CARD_Y + 36, code, 11.5, INK2, mono=True, w=rw - 36, h=16)
    centers.append(rx + rw / 2)
    rx += rw + 24
AW = 22
gap = CARD_Y - IB
d.gradient_arrow(centers[0] - AW / 2, IB, gap, direction="up", thickness=AW)
d.text(centers[0] + AW / 2 + 10, IB + gap / 2 - 10, "sets the inputs", 13, INK2, bold=True, w=160, h=20)
d.gradient_arrow(centers[1] - AW / 2, IB, gap, direction="down", thickness=AW)
d.text(centers[1] + AW / 2 + 10, IB + gap / 2 - 10, "reads the outputs", 13, INK2, bold=True, w=160, h=20)

print(d.xml("tango-couples-every-model"))
