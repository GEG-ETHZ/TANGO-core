# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Draw the README banner into docs/assets/, light and dark.

Standard library only: no fonts, no embedded images. The banner is the wordmark and the headline. The
letters carry the fluid's path through the system, from the cold surface (blue) down the wells (purple)
into the hot reservoir (red); the mark on the right is the same path as a loop, surface at the top,
reservoir at the bottom, with the plant on the surface.

Usage: uv run python tools/readme_assets.py   (also run by `just diagrams`)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets"
FONT = "Inter, ui-sans-serif, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"

HEADLINE = "Techno-economic ANalysis of Geoenergy Operations"
SUPPORT_1 = "Reservoir, wells and surface plant coupled in one modular simulator, solved"
SUPPORT_2 = "over the project's lifetime, with the levelized cost of electricity or heat."

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Palette:
    """Colors of one variant: neutrals and the three stops of the cold-to-hot gradient."""

    name: str
    paper: str
    ink: str
    grey: str
    hair: str
    surface: str
    well: str
    reservoir: str


LIGHT = Palette("light", "#FCFCFA", "#0E0E10", "#6F6F6B", "#E5E4DE", "#2F6FBF", "#7D4FB0", "#D2402C")
DARK = Palette("dark", "#0E0E10", "#EDEDEA", "#A3A39D", "#2A2A2E", "#82AEEA", "#B794E0", "#F08A78")


def text(x: float, y: float, s: str, size: float, fill: str, weight: int = 400, spacing: float = 0) -> str:
    """An SVG text element."""
    extra = f' letter-spacing="{spacing}"' if spacing else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}"{extra}>{escape(s)}</text>'


def gradient(gid: str, p: Palette, vertical: bool) -> str:
    """The cold-to-hot gradient: surface blue, well purple, reservoir red."""
    axis = 'x1="0" y1="0" x2="0" y2="1"' if vertical else 'x1="0" y1="0" x2="1" y2="0"'
    return (
        f'<linearGradient id="{gid}" {axis}>'
        f'<stop offset="0" stop-color="{p.surface}"/>'
        f'<stop offset="0.5" stop-color="{p.well}"/>'
        f'<stop offset="1" stop-color="{p.reservoir}"/>'
        "</linearGradient>"
    )


def mark(p: Palette, x: float, y: float, s: float) -> str:
    """The loop mark: the fluid's closed path. Cold water leaves the plant and goes down the injection
    well, warms across the reservoir, rises hot up the production well into the plant, and leaves it
    cold again. Drawn in a 200 x 220 box scaled by ``s``; (x, y) is its top-left corner.
    """
    g = f"warm-{p.name}"
    hot, cold = p.reservoir, p.surface
    stroke = 'fill="none" stroke-width="18" stroke-linejoin="round" stroke-linecap="butt"'
    return (
        f'<g transform="translate({x} {y}) scale({s})">'
        # the bottom pipe warms from right to left: the gradient runs cold at the right end, hot at the left
        f'<defs><linearGradient id="{g}" x1="1" y1="0" x2="0" y2="0">'
        f'<stop offset="0" stop-color="{cold}"/><stop offset="1" stop-color="{hot}"/></linearGradient></defs>'
        # the ground, and two faint strata
        f'<rect x="0" y="62" width="200" height="1.5" fill="{p.grey}"/>'
        f'<path d="M 0 130 Q 100 122 200 130" fill="none" stroke="{p.hair}" stroke-width="1.5"/>'
        f'<path d="M 0 182 Q 100 190 200 182" fill="none" stroke="{p.hair}" stroke-width="1.5"/>'
        # cold out of the plant and all the way down the injection well
        f'<path d="M 128 44 H 140 Q 150 44 150 54 V 190" stroke="{cold}" {stroke}/>'
        # warming across the reservoir
        f'<path d="M 150 190 Q 150 200 140 200 H 60 Q 50 200 50 190" stroke="url(#{g})" {stroke}/>'
        # hot up the production well and into the plant
        f'<path d="M 50 190 V 54 Q 50 44 60 44 H 82" stroke="{hot}" {stroke}/>'
        # the plant on the surface, where the heat becomes power
        f'<path d="M 80 62 V 24 H 94 V 40 L 112 30 V 40 L 130 30 V 62 Z" fill="{p.ink}"/>'
        f'<rect x="86" y="46" width="8" height="7" fill="{p.paper}"/>'
        f'<rect x="100" y="46" width="8" height="7" fill="{p.paper}"/>'
        f'<rect x="114" y="46" width="8" height="7" fill="{p.paper}"/>'
        # flow: up on the red production leg, down on the blue injection leg
        f'<path d="M 50 104 l -7 12 h 14 z" fill="{p.paper}"/>'
        f'<path d="M 150 120 l -7 -12 h 14 z" fill="{p.paper}"/>'
        "</g>"
    )


BANNER_W, BANNER_H = 1200, 340


def banner(p: Palette) -> str:
    """The wordmark in the cold-to-hot gradient, the headline, and the loop mark."""
    aria = f"TANGO, {HEADLINE}. {SUPPORT_1} {SUPPORT_2}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{BANNER_W}" height="{BANNER_H}" viewBox="0 0 {BANNER_W} {BANNER_H}" role="img" aria-label="{escape(aria, {chr(34): "&quot;"})}">
  <title>TANGO</title>
  <defs>
    {gradient(f"word-{p.name}", p, vertical=False)}
    {gradient(f"loop-{p.name}", p, vertical=True)}
  </defs>
  <rect width="{BANNER_W}" height="{BANNER_H}" fill="{p.paper}"/>
  <rect y="{BANNER_H - 1}" width="{BANNER_W}" height="1" fill="{p.hair}"/>
  <g font-family="{FONT}">
    <text x="66" y="151" font-size="96" font-weight="800" letter-spacing="-3.6" fill="url(#word-{p.name})">TANGO</text>
    {text(72, 201, HEADLINE, 21, p.ink, 600, -0.3)}
    {text(72, 235, SUPPORT_1, 16.5, p.grey)}
    {text(72, 260, SUPPORT_2, 16.5, p.grey)}
  </g>
  {mark(p, 900, 48, 1.1)}
</svg>
"""


def main() -> None:
    """Write both variants of the banner into ``docs/assets/``."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (LIGHT, DARK):
        (OUT / f"banner-{p.name}.svg").write_text(banner(p), encoding="utf-8")
    log.info("wrote the banner, light and dark, into %s", OUT)


if __name__ == "__main__":
    main()
