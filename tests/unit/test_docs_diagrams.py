"""Every draw.io diagram in docs/diagrams/src/ has its SVG export in docs/diagrams/, and vice versa.

The SVGs are committed so GitHub and the Sphinx docs can show them without a
draw.io install; `just diagrams` regenerates them. This only checks that each
pair exists, not that the SVG is up to date: draw.io versions export slightly
different SVG for the same diagram, so comparing contents would be brittle.
"""

from __future__ import annotations

from pathlib import Path

DIAGRAMS_DIR = Path(__file__).resolve().parents[2] / "docs" / "diagrams"
SOURCES_DIR = DIAGRAMS_DIR / "src"


def test_every_drawio_source_has_an_svg_export() -> None:
    """A diagram added under docs/diagrams/src/ must be exported with `just diagrams` and committed."""
    missing = [
        src.name
        for src in sorted(SOURCES_DIR.glob("*.drawio"))
        if not (DIAGRAMS_DIR / f"{src.stem}.svg").exists()
    ]
    assert not missing, f"no SVG export for {missing}: run `just diagrams` and commit docs/diagrams/*.svg"


def test_every_svg_export_has_a_drawio_source() -> None:
    """An SVG left behind after its source was renamed or deleted is stale."""
    orphans = [
        svg.name
        for svg in sorted(DIAGRAMS_DIR.glob("*.svg"))
        if not (SOURCES_DIR / f"{svg.stem}.drawio").exists()
    ]
    assert not orphans, f"SVG with no docs/diagrams/src/*.drawio source: {orphans}"
