"""Regenerate the editable diagrams in docs/diagrams/ from the scripts next to this file.

Each script prints draw.io XML; the draw.io command line (``drawio``, installed with the desktop app)
exports it to an SVG with the diagram embedded, so the result opens in draw.io for hand edits. The
banner in docs/assets/ is drawn separately by tools/readme_assets.py.

Usage: just diagrams   (or: uv run python tools/diagrams/build.py)
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent.parent / "docs" / "diagrams"
#: script -> exported file name under docs/diagrams/
DIAGRAMS = {
    "system_key.py": "system-key",
    "hero.py": "hero",
    "system.py": "tango-couples-every-model",
    "user_experience.py": "user-experience",
    "architecture_map.py": "architecture-map",
}

log = logging.getLogger(__name__)


def export(script: str, name: str, drawio: str, workdir: Path) -> Path:
    """Run one script, export its XML to ``docs/diagrams/<name>.drawio.svg`` and return that path."""
    xml = subprocess.run(
        [sys.executable, str(HERE / script)],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    source = workdir / f"{name}.drawio"
    source.write_text(xml, encoding="utf-8")
    target = OUT / f"{name}.drawio.svg"
    target.unlink(missing_ok=True)
    result = subprocess.run(
        [
            drawio,
            "-x",
            "-f",
            "svg",
            "--embed-diagram",
            "--svg-theme",
            "light",
            "-b",
            "0",
            "-o",
            str(target),
            str(source),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not target.exists():
        raise RuntimeError(
            f"drawio failed to export {name} (exit {result.returncode}): {result.stderr.strip()}",
        )
    return target


def main() -> int:
    """Export every diagram; return a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    drawio = shutil.which("drawio")
    if drawio is None:
        log.error(
            "drawio not found on PATH: install the draw.io desktop app and link its command line as `drawio`",
        )
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        for script, name in DIAGRAMS.items():
            target = export(script, name, drawio, Path(tmp))
            log.info("wrote %s (%d KB)", target.relative_to(OUT.parent.parent), target.stat().st_size // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
