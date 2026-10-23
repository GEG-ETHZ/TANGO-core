"""The shared system pictogram: surface plant, wells and reservoir around the fluid loop, plus economics.

The same drawing, in the same four colors, opens every diagram and sits in the banner and the hero,
so a reader meets one system and then sees it at different depths. draw_key(d, x, y, s) draws it
natively into a Doc (editable in draw.io); at s=1 it is 360 x 320. It returns the y-centers of the
three boxes and the economics box's frame, so callers can hang chips next to each part.
"""

from drawio import MUTED, ROLE, Doc
from loop import LOOP_SVG

KEY_W, KEY_H = 360, 320
SLIDE_X0, SLIDE_Y0, SLIDE_W = 40, 40, 490
BOXES = {"surface": (40, 270), "well": (278, 510), "reservoir": (518, 760)}
CENTER = {"surface": 155, "well": 394, "reservoir": 639}


def draw_key(
    d: Doc,
    x: float,
    y: float,
    s: float = 1.0,
    detail: bool = True,
    econ: bool = True,
    variants: dict[str, str] | None = None,
) -> dict[str, float]:
    """Draw the pictogram at (x, y) and scale s; return the parts' y-centers, the stack and the economics frame.

    ``variants`` maps a part to the chip drawn inside its tile, for example ``{"well": "numerical"}``.
    """
    k = 200 / SLIDE_W * s  # slide -> key scale

    def px(v: float) -> float:
        return round(x + 12 * s + (v - SLIDE_X0) * k, 1)

    def py(v: float) -> float:
        return round(y + 12 * s + (v - SLIDE_Y0) * k, 1)

    bw = round(490 * k, 1)
    for kind, (y0, y1) in BOXES.items():
        stroke, fill, _ = ROLE[kind]
        d.rect(px(40), py(y0), bw, round((y1 - y0) * k, 1), fill=fill, stroke=stroke, sw=1.5, r=round(10 * s))
    d.svg_image(px(40), py(150), bw, round(490 * k, 1), LOOP_SVG)

    t = 13 if s >= 0.85 else 12
    d.text(px(40), py(56), "Surface plant", t, ROLE["surface"][0], bold=True, align="center", w=bw, h=t + 6)
    d.text(
        px(130),
        py(338),
        "Wells",
        t,
        ROLE["well"][0],
        bold=True,
        align="center",
        w=round(310 * k),
        h=t + 6,
    )
    d.text(px(40), py(640), "Reservoir", t, ROLE["reservoir"][0], bold=True, align="center", w=bw, h=t + 6)

    if variants:
        slots = {"surface": (40, 490, 56), "well": (130, 310, 338), "reservoir": (40, 490, 640)}
        for kind, (lx, lw, ly) in slots.items():
            if kind in variants:
                cw = round(len(variants[kind]) * 11 * 0.62 + 20)
                d.chip(px(lx) + (lw * k - cw) / 2, py(ly) + t + 12, variants[kind], kind, size=11, h=22, w=cw)
    out = {kind: py(v) for kind, v in CENTER.items()}
    out.update(stack_x=px(40), stack_w=bw, stack_right=px(40) + bw, right=x + KEY_W * s, bottom=y + KEY_H * s)
    if not econ:
        return out
    # economics: reads the wells and the surface plant, never the reservoir
    ex = px(530) + 28 * s
    ew = x + KEY_W * s - 8 * s - ex
    ey0, ey1 = py(110), py(470)
    stroke, fill, ink = ROLE["economic"]
    d.rect(ex, ey0, ew, ey1 - ey0, fill=fill, stroke=stroke, sw=1.5, r=round(10 * s))
    ty = ey0 + 10 * s
    d.text(ex + 8, ty, "Economics", t, ink, bold=True, w=ew - 16, h=t + 6)
    body = (
        "prices the wells\nand the surface\nplant, once after\nthe last timestep"
        if detail
        else "once, after\nthe last\ntimestep"
    )
    d.text(ex + 8, ty + t + 12, body, 10, MUTED, w=ew - 16, h=13 * (body.count("\n") + 1), valign="top")
    for kind in ("surface", "well"):
        yy = out[kind]
        d.edge([(px(530) + 2, yy), (ex - 2, yy)], color=ROLE[kind][0], sw=1.5, size=5)
    out.update(econ_x=ex, econ_w=ew, econ_top=ey0, econ_bottom=ey1)
    return out


if __name__ == "__main__":
    doc = Doc(KEY_W, KEY_H)
    doc.frame()
    draw_key(doc, 0, 0, 1.0)
    print(doc.xml("system-key"))
