"""The fluid loop, the plant and the caprock as one vector image, without text.

Drawn in the slide's coordinates (x 40..530, y 40..760); ``system_key.draw_key`` places it. Hot water
rises red on the left, cold water goes down blue on the right, and the pipe runs through the plant.
"""

from drawio import ROLE

HOT, COLD = ROLE["reservoir"][0], ROLE["surface"][0]
INK = "#17140f"

LOOP_L, LOOP_R, LOOP_T, LOOP_B, R, PIPE = 108, 465, 274, 566, 44, 30


def arrow(x: float, y: float, up: bool, color: str, size: float = 1.0) -> str:
    """A fat arrow on a pipe, pointing up or down; ``size`` scales it."""
    k = -1 if up else 1
    tip, neck, half, wing = y + k * 52 * size, y + k * 18 * size, 15 * size, 32 * size
    return (
        f'<path d="M {x - half} {y} V {neck} H {x - wing} L {x} {tip} L {x + wing} {neck} H {x + half} V {y} Z" '
        f'fill="{color}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
    )


hot = f"M {LOOP_L} {LOOP_B - R} V {LOOP_T + R} Q {LOOP_L} {LOOP_T} {LOOP_L + R} {LOOP_T} H 300"
cold = f"M 300 {LOOP_T} H {LOOP_R - R} Q {LOOP_R} {LOOP_T} {LOOP_R} {LOOP_T + R} V {LOOP_B - R}"
base = (
    f"M {LOOP_R} {LOOP_B - R} Q {LOOP_R} {LOOP_B} {LOOP_R - R} {LOOP_B} H {LOOP_L + R} "
    f"Q {LOOP_L} {LOOP_B} {LOOP_L} {LOOP_B - R}"
)
edge = f'fill="none" stroke="{INK}" stroke-width="{PIPE + 6}" stroke-linejoin="round"'
fill = f'fill="none" stroke-width="{PIPE}" stroke-linejoin="round"'
FB = LOOP_T + 24  # the plant's base sits below the pipe's center line, so the pipe runs through the plant
plant = f'<path d="M 218 {FB} V 158 H 244 V 208 L 296 176 V 208 L 348 176 V 208 L 378 190 V {FB} Z" fill="{INK}"/>'
windows = "".join(
    f'<rect x="{x}" y="226" width="26" height="14" fill="{c}"/>'
    for x, c in ((236, HOT), (282, "#FFFFFF"), (328, COLD))
)
LOOP_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="40 150 490 490" width="490" height="490">'
    '<defs><linearGradient id="loop" x1="1" y1="0" x2="0" y2="0">'
    f'<stop offset="0" stop-color="{COLD}"/><stop offset="1" stop-color="{HOT}"/></linearGradient>'
    '<linearGradient id="cap" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#b7a9ab"/><stop offset="1" stop-color="#d9a3a0"/></linearGradient></defs>'
    '<path d="M 82 596 Q 287 516 492 596 L 474 628 Q 287 556 100 628 Z" fill="url(#cap)" stroke="#7d6f72" stroke-width="2"/>'
    + plant
    + windows
    + f'<path d="{hot} {cold[cold.index("H") :]} {base[base.index("Q") :]} Z" {edge}/>'
    f'<path d="{base}" stroke="url(#loop)" {fill}/>'
    f'<path d="{hot}" stroke="{HOT}" {fill}/>'
    f'<path d="{cold}" stroke="{COLD}" {fill}/>'
    + arrow(LOOP_L, 480, True, HOT)
    + arrow(LOOP_L, 540, True, HOT, 0.55)
    + arrow(LOOP_R, 380, False, COLD)
    + arrow(LOOP_R, 470, False, COLD, 0.7)
    + "</svg>"
)
