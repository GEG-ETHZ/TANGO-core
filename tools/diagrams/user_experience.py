"""How you use TANGO: pick a model for each part, wire them into a workflow, run, read the results; who drives it.

Prints draw.io XML; ``build.py`` exports it to ``docs/diagrams/user-experience.drawio.svg``.
"""

from drawio import HAIR, INK, INK2, MUTED, ROLE, Doc
from parts import CONNECTOR, PARTS
from system_key import draw_key

TOP, CARD_H = 24, 540
W, H = 1600, TOP + CARD_H + 24
d = Doc(W, H)
d.frame()

GAP = 44
cols = [
    (580, "1", "Pick a model for each part", "components/<type>  ·  variant  →  registry.py"),
    (300, "2", "Wire into a workflow", "workflows/  ·  orchestrators/"),
    (244, "3", "Run it", "tango_core  ·  applications/"),
    (248, "4", "Read the results", "results_export.py"),
]
x = 48
xs = []
for i, (w, num, title, entry) in enumerate(cols):
    xs.append((x, w))
    d.rect(x, TOP, w, CARD_H, fill="#FFFFFF", stroke=HAIR, r=16)
    d.tab(x, TOP, w)
    d.badge(x + 24, TOP + 36, 34, num)
    d.text(x + 70, TOP + 39, title, 18, INK, bold=True, w=w - 94, h=28)
    d.rect(x + 24, TOP + CARD_H - 52, w - 48, 1, fill=HAIR, stroke="none", r=0)
    d.text(x + 24, TOP + CARD_H - 40, entry, 11, MUTED, mono=True, w=w - 48, h=24)
    if i < len(cols) - 1:
        ax = x + w
        d.gradient_arrow(ax + 6, TOP + CARD_H / 2 - 11, GAP - 12, direction="right")
    x += w + GAP

# ---- step 1: a miniature of the system: external simulators, connectors, the tiles with their models
x1, w1 = xs[0]
RAIL = x1 + 24 + 118  # the external simulators' dashed rail
KS = 0.92
pos = draw_key(d, RAIL + 96, TOP + 86, KS, detail=False, variants={k: b[0] for k, b, _ in PARTS if b})
CW = 80
for kind, _, external in PARTS:
    if not external:
        continue
    yc = pos[kind]
    color = ROLE[kind][0]
    d.chip(pos["stack_x"] - CW + 16, yc - 11, CONNECTOR, "neutral", w=CW, h=22, size=11)
    d.edge([(pos["stack_x"] - CW + 14, yc), (RAIL, yc)], color=color, sw=1.5, end="none", dashed=True)
    # two chips per row, right-aligned to the rail
    rows = [external[i : i + 2] for i in range(0, len(external), 2)]
    step = 24
    top = yc - (step * len(rows) - 4) / 2
    if len(rows) > 1:
        d.edge(
            [(RAIL, top + 10), (RAIL, top + step * (len(rows) - 1) + 10)],
            color=color,
            sw=1.5,
            end="none",
            dashed=True,
        )
    for r, row in enumerate(rows):
        cy = top + step * r
        d.edge([(RAIL - 8, cy + 10), (RAIL, cy + 10)], color=color, sw=1.5, end="none", dashed=True)
        cx = RAIL - 10
        for s_ in reversed(row):
            cw = round(len(s_) * 10 * 0.62 + 18)
            cx -= cw
            d.chip(cx, cy, s_, kind, dashed=True, w=cw, h=20, size=10)
            cx -= 6
d.text(x1 + 24, TOP + 86, "External\nsimulators", 11, MUTED, bold=True, w=100, h=30, valign="top")
d.text(
    x1 + 24,
    pos["bottom"] + 10,
    "Each part is one YAML entry: a type and a variant. A connector is TANGO's adapter for an\n"
    "external simulator; the simulators themselves are outside TANGO.",
    12,
    MUTED,
    w=w1 - 48,
    h=36,
    valign="top",
)

# ---- step 2: the circuit, solved every timestep; economics to the right, once at the end
x2, w2 = xs[1]
d.text(
    x2 + 24,
    TOP + 86,
    "The config wires the parts into one\ncircuit. Every timestep it is solved\nuntil the returning temperature\nsettles; economics runs once at\nthe end.",
    13,
    MUTED,
    w=w2 - 48,
    h=92,
    valign="top",
)
nodes = [
    ("Injection well", "well"),
    ("Reservoir", "reservoir"),
    ("Production well", "well"),
    ("Surface plant", "surface"),
]
ny, nh, nw = TOP + 196, 36, 130
nx = x2 + 40
ys = []
for k, (s_, kind) in enumerate(nodes):
    yy = ny + k * (nh + 30)
    ys.append(yy)
    stroke, fill, ink = ROLE[kind]
    d.rect(
        nx,
        yy,
        nw,
        nh,
        fill=fill,
        stroke=stroke,
        r=10,
        label=s_,
        fontSize=13,
        fontColor=ink,
        align="center",
        verticalAlign="middle",
    )
    if k:
        d.edge([(nx + nw / 2, yy - 30 + 2), (nx + nw / 2, yy - 2)], color="#80868B", sw=2, size=8)
# the return: the plant's outlet is the injection well's inlet on the next pass
rail = nx - 18
d.edge(
    [(nx - 2, ys[-1] + nh / 2), (rail, ys[-1] + nh / 2), (rail, ys[0] + nh / 2), (nx - 4, ys[0] + nh / 2)],
    color="#80868B",
    sw=2,
    size=8,
    dashed=True,
)
d.text(nx - 18, ys[-1] + nh + 12, "repeat until converged", 11, MUTED, w=nw + 36, h=18, align="center")
# economics to the right: reads the wells and the surface plant through one rail
es, ef, ei = ROLE["economic"]
ew_, eh_ = 86, 66
ex_ = x2 + w2 - 24 - ew_
ey = (ys[0] + ys[-1] + nh) / 2 - eh_ / 2
erail = nx + nw + 16
d.rect(ex_, ey, ew_, eh_, fill=ef, stroke=es, r=10)
d.text(ex_, ey + 8, "Economics", 12, ei, bold=True, align="center", w=ew_, h=18)
d.text(ex_, ey + 28, "once, after\nthe last step", 10.5, ei, align="center", w=ew_, h=30, valign="top")
for k, kind in ((0, "well"), (2, "well"), (3, "surface")):
    yy = ys[k] + nh / 2
    d.edge([(nx + nw + 2, yy), (erail, yy)], color=ROLE[kind][0], sw=2, end="none", dashed=True)
d.edge([(erail, ys[0] + nh / 2), (erail, ys[-1] + nh / 2)], color="#80868B", sw=2, end="none", dashed=True)
d.edge([(erail, ey + eh_ / 2), (ex_ - 2, ey + eh_ / 2)], color=ei, sw=2, size=8, dashed=True)

# ---- step 3: three ways to run
x3, w3 = xs[2]
runs = [
    ("Single run", "tango_core run config.yml"),
    ("Sweep", "applications/run_* · DVC"),
    ("Optimization", "pymoo_api · NSGA-II"),
]
ry = TOP + 92
for title, code in runs:
    hh = 84 if "\n" in code else 68
    d.rect(x3 + 24, ry, w3 - 48, hh, fill="#FFFFFF", stroke=HAIR, r=12)
    d.text(x3 + 40, ry + 12, title, 14, INK, bold=True, w=w3 - 80, h=20)
    d.text(
        x3 + 40,
        ry + 36,
        code,
        11,
        INK2,
        mono=True,
        w=w3 - 80,
        h=16 * (code.count("\n") + 1),
        valign="top",
    )
    ry += hh + 16
d.text(
    x3 + 24,
    ry + 4,
    "A sweep or an optimization runs\nthe workflow once per design,\nin parallel.",
    12,
    MUTED,
    w=w3 - 48,
    h=56,
    valign="top",
)

# ---- step 4: what comes out, tagged with the part it comes from
x4, w4 = xs[3]
outs = [
    ("LCOE, CAPEX, OPEX", ["economic"], "csv"),
    ("Net power and heat", ["surface"], ""),
    ("T, P, mass rate\nper timestep", ["well", "reservoir", "surface"], "csv"),
    ("The solved config", [], "yml"),
]
oy = TOP + 92
for title, kinds, ext in outs:
    hh = 80 if "\n" in title else 64
    d.rect(x4 + 24, oy, w4 - 48, hh, fill="#FFFFFF", stroke=HAIR, r=12)
    d.text(
        x4 + 40,
        oy + 8,
        title,
        12.5,
        INK,
        bold=True,
        w=w4 - 80,
        h=18 * (title.count("\n") + 1),
        valign="top",
    )
    dx = x4 + 40
    if len(kinds) == 1:
        d.rect(dx, oy + hh - 20, 10, 10, fill=ROLE[kinds[0]][0], stroke="none", r=5)
        d.text(dx + 14, oy + hh - 26, kinds[0], 11, ROLE[kinds[0]][2], mono=True, w=100, h=20)
    elif kinds:
        for kind in kinds:
            d.rect(dx, oy + hh - 20, 10, 10, fill=ROLE[kind][0], stroke="none", r=5)
            dx += 14
        d.text(dx + 2, oy + hh - 26, "every part", 11, MUTED, w=96, h=20)
    else:
        d.text(dx, oy + hh - 26, "reloadable", 11, MUTED, w=100, h=20)
    if ext:
        d.doc(x4 + w4 - 40 - 26, oy + hh - 36, 26, 30, ext)
    oy += hh + 12

print(d.xml("user-experience"))
