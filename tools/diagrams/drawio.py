# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""A small builder for draw.io files (mxfile XML) with the diagrams' shared palette.

Every diagram in ``docs/diagrams/`` is written through ``Doc``: rectangles, text, chips, edges and
embedded images, in canvas pixels. ``build.py`` exports the XML with the draw.io command line, so the
result stays editable in draw.io. Text wider than the box it was given is reported on stderr at export.
"""

import base64
import sys
from collections.abc import Sequence
from pathlib import Path
from xml.sax.saxutils import quoteattr

FONT = "Helvetica"
INK, INK2, MUTED, HAIR = "#202124", "#3C4043", "#5F6368", "#DADCE0"
BG, PANEL = "#FFFFFF", "#F8F9FA"
#: The wordmark's gradient, cold surface blue to hot reservoir red; draw.io blends through purple.
GRADIENT = ("#2F6FBF", "#D2402C")
#: (stroke, fill, text) per role. Component types carry their identity color; everything else is neutral.
ROLE = {
    "well": ("#7D4FB0", "#F3EDF9", "#7D4FB0"),
    "reservoir": ("#D2402C", "#FBEAE7", "#D2402C"),
    "surface": ("#2F6FBF", "#E8F0FA", "#2F6FBF"),
    "economic": ("#007B83", "#E0F2F1", "#007B83"),
    "neutral": ("#DADCE0", "#FFFFFF", "#3C4043"),
    "status": ("#3C4043", "#FFFFFF", "#3C4043"),
    "grey": ("#9AA0A6", "#FFFFFF", "#5F6368"),
}
#: A canvas point (x, y) in pixels.
Point = tuple[float, float]


def style(**kw: object) -> str:
    """A draw.io style string from keyword arguments, with the shared font."""
    base: dict[str, object] = {"html": 0, "fontFamily": FONT}
    base.update(kw)
    return ";".join(f"{k}={v}" for k, v in base.items()) + ";"


class Doc:
    """One draw.io page of ``w`` x ``h`` pixels; cells are appended in drawing order."""

    def __init__(self, w: float, h: float) -> None:
        """Start an empty page; set ``crop`` to cut that many pixels from the top at export."""
        self.w, self.h, self.n = w, h, 1
        self.cells: list[str] = []
        self.crop = 0  # pixels cut from the top at export: every y is shifted up by this
        self.warnings: list[str] = []

    def _id(self) -> str:
        self.n += 1
        return f"c{self.n}"

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str = BG,
        stroke: str = HAIR,
        sw: float = 1,
        r: float = 12,
        dashed: bool = False,
        label: str = "",
        **kw: object,
    ) -> str:
        """A rounded rectangle, optionally dashed and labelled; extra keywords go into the style."""
        st: dict[str, object] = {
            "rounded": 1 if r else 0,
            "absoluteArcSize": 1,
            "arcSize": r * 2,
            "fillColor": fill,
            "strokeColor": stroke,
            "strokeWidth": sw,
        }
        if dashed:
            st.update(dashed=1, dashPattern="4 3")
        st.update(kw)
        return self._vertex(x, y, w, h, label, style(**st))

    def tile(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str = BG,
        stroke: str = HAIR,
        sw: float = 1,
        r: float = 12,
    ) -> str:
        """A card with a soft shadow, the hero's building block."""
        return self.rect(x, y, w, h, fill=fill, stroke=stroke, sw=sw, r=r, shadow=1)

    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: float = 14,
        color: str = INK,
        bold: bool = False,
        align: str = "left",
        w: float | None = None,
        h: float | None = None,
        mono: bool = False,
        valign: str = "middle",
        **kw: object,
    ) -> str:
        """A text block; width and height default to an estimate from the text.

        A given width is checked: text estimated to be wider than it is reported at export.
        """
        if w is not None:
            per_char = size * (0.55 if mono else 0.5 if bold else 0.46)
            longest = max(len(line) for line in s.split("\n"))
            if longest * per_char > w + 4:
                self.warnings.append(
                    f"text wider than its box ({longest * per_char:.0f} > {w}): {s.splitlines()[0][:60]!r}",
                )
        w = w if w is not None else max(20, len(s.split("\n")[0]) * size * 0.62)
        h = h if h is not None else size * 1.4 * (s.count("\n") + 1)
        st: dict[str, object] = {
            "strokeColor": "none",
            "fillColor": "none",
            "align": align,
            "verticalAlign": valign,
            "fontSize": size,
            "fontColor": color,
            "fontStyle": 1 if bold else 0,
            "spacing": 0,
        }
        if mono:
            st["fontFamily"] = "Menlo"
        st.update(kw)
        return self._vertex(x, y, w, h, s, "text;" + style(**st))

    def chip(
        self,
        x: float,
        y: float,
        s: str,
        role: str = "neutral",
        planned: bool = False,
        size: float = 12,
        h: float = 24,
        pad: float = 11,
        w: float | None = None,
        dashed: bool = False,
    ) -> float:
        """A pill-shaped chip in a role's colors.

        ``dashed`` keeps the role's stroke and text on a white fill with a dashed border: something
        outside TANGO that belongs to this component type, such as an external simulator. ``planned``
        draws it dashed grey.
        """
        stroke, fill, ink = ROLE["grey"] if planned else ROLE[role]
        if dashed:
            fill = "#FFFFFF"
        w = w if w is not None else round(len(s) * size * 0.62 + 2 * pad)
        self.rect(
            x,
            y,
            w,
            h,
            fill=fill,
            stroke=stroke,
            r=h // 2,
            dashed=planned or dashed,
            label=s,
            fontSize=size,
            fontColor=ink,
            align="center",
            verticalAlign="middle",
            fontStyle=0,
        )
        return w

    def badge(self, x: float, y: float, size: float, label: str) -> str:
        """A numbered circle filled with the wordmark's cold-to-hot gradient, the number in white."""
        st = "ellipse;" + style(
            fillColor=GRADIENT[0],
            gradientColor=GRADIENT[1],
            gradientDirection="east",
            strokeColor="none",
            fontColor="#FFFFFF",
            fontStyle=1,
            fontSize=round(size * 0.47),
            align="center",
            verticalAlign="middle",
        )
        return self._vertex(x, y, size, size, label, st)

    def tab(self, x: float, y: float, w: float, r: float = 16, h: float = 14, fill: str = BG) -> str:
        """A gradient tab across the top of a box of corner radius ``r``: one shape with rounded top corners
        and a flat bottom ``h`` pixels below the top edge, so it sits flush on the box like a browser tab.
        """
        del fill  # kept for callers; the shape needs no cover
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{GRADIENT[0]}"/>'
            f'<stop offset="1" stop-color="{GRADIENT[1]}"/></linearGradient></defs>'
            f'<path d="M 0 {h} V {r} A {r} {r} 0 0 1 {r} 0 H {w - r} A {r} {r} 0 0 1 {w} {r} V {h} Z" fill="url(#g)"/>'
            "</svg>"
        )
        return self.svg_image(x, y, w, h, svg)

    def gradient_arrow(
        self,
        x: float,
        y: float,
        length: float,
        direction: str = "up",
        thickness: float = 22,
        shaft: float = 6,
        colors: tuple[str, str] = GRADIENT,
    ) -> str:
        """An arrow as one filled shape in a two-stop gradient (the wordmark's by default), since draw.io
        cannot put a gradient on a stroke. ``direction`` is ``up``, ``down`` or ``right``; (x, y) is the
        top-left of its box.
        """
        head = min(16, length / 2)
        c = thickness / 2
        half = shaft / 2
        if direction == "right":
            w, h = length, thickness
            path = f"M 0 {c - half} H {length - head} V 0 L {length} {c} L {length - head} {thickness} V {c + half} H 0 Z"
            axis = 'x1="0" y1="0" x2="1" y2="0"'
        else:
            w, h = thickness, length
            axis = 'x1="0" y1="0" x2="0" y2="1"'
            if direction == "up":
                path = f"M {c} 0 L {thickness} {head} H {c + half} V {length} H {c - half} V {head} H 0 Z"
            else:
                path = (
                    f"M {c - half} 0 H {c + half} V {length - head} H {thickness} L {c} {length} "
                    f"L 0 {length - head} H {c - half} Z"
                )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<defs><linearGradient id="g" {axis}><stop offset="0" stop-color="{colors[0]}"/>'
            f'<stop offset="1" stop-color="{colors[1]}"/></linearGradient></defs>'
            f'<path d="{path}" fill="url(#g)"/></svg>'
        )
        return self.svg_image(x, y, w, h, svg)

    def doc(self, x: float, y: float, w: float, h: float, label: str) -> str:
        """A small file icon with a folded corner, labelled with its extension."""
        st = "shape=note;size=7;" + style(
            fillColor="#FFFFFF",
            strokeColor=MUTED,
            fontColor=MUTED,
            fontSize=9,
            align="center",
            verticalAlign="bottom",
            spacingBottom=2,
        )
        return self._vertex(x, y, w, h, label, st)

    def image(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        path: Path,
        mime: str = "image/jpeg",
        stroke: str = "none",
    ) -> str:
        """An embedded raster image."""
        data = base64.b64encode(path.read_bytes()).decode()
        st = f"shape=image;verticalLabelPosition=bottom;aspect=fixed;imageAspect=0;image=data:{mime},{data};imageBorder={stroke};"
        return self._vertex(x, y, w, h, "", st)

    def svg_image(self, x: float, y: float, w: float, h: float, svg: str) -> str:
        """An embedded vector image."""
        data = base64.b64encode(svg.encode()).decode()
        st = f"shape=image;aspect=fixed;imageAspect=0;image=data:image/svg+xml,{data};"
        return self._vertex(x, y, w, h, "", st)

    def edge(
        self,
        pts: Sequence[Point],
        color: str = MUTED,
        sw: float = 2,
        end: str = "block",
        start: str = "none",
        dashed: bool = False,
        label: str = "",
        rounded: bool = True,
        size: float = 10,
    ) -> str:
        """A connector through ``pts``; the first and last point are its ends.

        Heads are plain filled triangles, never smaller than 9 px; strokes are never thinner than 2 px.
        """
        end = "block" if end == "classic" else end
        start = "block" if start == "classic" else start
        sw, size = max(sw, 2), max(size, 9)
        cid = self._id()
        dash: dict[str, object] = {"dashed": 1, "dashPattern": "4 3"} if dashed else {}
        st = style(
            endArrow=end,
            startArrow=start,
            endFill=1,
            startFill=1,
            strokeColor=color,
            strokeWidth=sw,
            rounded=1 if rounded else 0,
            endSize=size,
            startSize=size,
            edgeStyle="none",
            fontSize=12,
            fontColor=MUTED,
            **dash,
        )
        shifted = [(x, y - self.crop) for x, y in pts]
        (sx, sy), (tx, ty) = shifted[0], shifted[-1]
        mids = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in shifted[1:-1])
        arr = f'<Array as="points">{mids}</Array>' if mids else ""
        self.cells.append(
            f'<mxCell id="{cid}" value={quoteattr(label)} style={quoteattr(st)} edge="1" parent="1">'
            f'<mxGeometry relative="1" as="geometry"><mxPoint x="{sx}" y="{sy}" as="sourcePoint"/>'
            f'<mxPoint x="{tx}" y="{ty}" as="targetPoint"/>{arr}</mxGeometry></mxCell>',
        )
        return cid

    def curve(self, src: Point, dst: Point, color: str = MUTED, sw: float = 2, size: float = 9) -> str:
        """A smooth S-shaped connector from ``src`` to ``dst`` that leaves and enters sideways."""
        cid = self._id()
        st = style(
            endArrow="block",
            endFill=1,
            strokeColor=color,
            strokeWidth=sw,
            endSize=size,
            edgeStyle="none",
            curved=1,
        )
        (sx, sy), (tx, ty) = src, dst
        mx = (sx + tx) / 2
        pts = f'<Array as="points"><mxPoint x="{mx}" y="{sy - self.crop}"/><mxPoint x="{mx}" y="{ty - self.crop}"/></Array>'
        self.cells.append(
            f'<mxCell id="{cid}" value="" style={quoteattr(st)} edge="1" parent="1">'
            f'<mxGeometry relative="1" as="geometry"><mxPoint x="{sx}" y="{sy - self.crop}" as="sourcePoint"/>'
            f'<mxPoint x="{tx}" y="{ty - self.crop}" as="targetPoint"/>{pts}</mxGeometry></mxCell>',
        )
        return cid

    def _vertex(self, x: float, y: float, w: float, h: float, label: str, st: str) -> str:
        cid = self._id()
        self.cells.append(
            f'<mxCell id="{cid}" value={quoteattr(label)} style={quoteattr(st)} vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y - self.crop}" width="{w}" height="{h}" as="geometry"/></mxCell>',
        )
        return cid

    def xml(self, name: str) -> str:
        """The complete mxfile document; text that overflows its box is reported on stderr."""
        for warning in self.warnings:
            print(f"{name}: {warning}", file=sys.stderr)
        return (
            f'<mxfile host="drawio"><diagram id="{name}" name="{name}">'
            f'<mxGraphModel dx="{self.w}" dy="{self.h}" grid="1" gridSize="8" guides="1" page="1" '
            f'pageWidth="{self.w}" pageHeight="{self.h}" background="#ffffff" math="0" shadow="0">'
            f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{"".join(self.cells)}</root>'
            f"</mxGraphModel></diagram></mxfile>"
        )

    def frame(self) -> None:
        """An invisible full-canvas rectangle so the export keeps uniform margins (set ``crop`` first)."""
        self._vertex(
            0,
            self.crop,
            self.w,
            self.h - self.crop,
            "",
            style(fillColor="#FFFFFF", strokeColor="none"),
        )


def note(
    d: Doc,
    x: float,
    y: float,
    w: float,
    h: float,
    s: str,
    size: float = 11,
    color: str = MUTED,
    dashed: bool = True,
    align: str = "center",
) -> None:
    """A dashed note box with wrapped text: something that is not in this repository."""
    d.rect(
        x,
        y,
        w,
        h,
        fill="#FFFFFF",
        stroke="#9AA0A6",
        r=10,
        dashed=dashed,
        label=s,
        fontSize=size,
        fontColor=color,
        align=align,
        verticalAlign="middle",
        spacingLeft=8,
        spacingRight=8,
    )


def curve(d: Doc, src: Point, dst: Point, color: str = MUTED, sw: float = 2, size: float = 9) -> str:
    """Module-level alias of ``Doc.curve`` for scripts that import it as a function."""
    return d.curve(src, dst, color=color, sw=sw, size=size)
