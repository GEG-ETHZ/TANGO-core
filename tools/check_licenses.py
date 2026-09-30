"""Generate and check third-party package license compliance.

Two steps, runnable together or separately:

1. **Generate** (``--generate-only``): inspect every package installed in the
   current environment and write one entry per package to
   ``tools/licenses.json``. The license comes from the package's own
   metadata (``License-Expression``, else ``License``, else a
   ``License ::`` classifier, else ``"Unknown"``).
2. **Check** (``--check-only``): normalize each entry's license string and
   compare it against ``ALLOWED_LICENSES``. Every package that isn't
   allowed, including ``"Unknown"`` ones, is listed along with its scope
   and depth, and the script exits 1. If all are allowed it exits 0.

Because the input is the installed environment, not ``pyproject.toml`` or
``uv.lock``, run it from a fully synced environment (``uv sync``) so the
report covers exactly what ships and what the dev tooling pulls in.

Each entry in licenses.json has ``Name`` and ``License``, plus where the
package sits in the dependency graph rooted at ``tango-core``. That graph is
built from installed metadata (``Requires-Dist``, with environment markers
and extras evaluated) plus the ``dev`` dependency group in ``pyproject.toml``:

- ``Depth``: shortest requirement chain from ``tango-core`` (1 = direct
  dependency); ``null`` if nothing in the graph requires it.
- ``Direct``: ``Depth == 1``.
- ``Scope``: ``"runtime"`` if reachable through ``tango-core``'s own
  dependencies, ``"dev"`` if reachable only through the ``dev`` extra or
  the ``dev`` dependency group, ``"unreferenced"`` if not reachable at all
  (e.g. installed by hand).
- ``RequiredBy``: installed packages that directly require it
  (``tango-core`` included).
- ``Parent``: the requirer on one shortest chain from ``tango-core``;
  following ``Parent`` links back to ``tango-core`` gives that chain.

``--drawio [PATH]`` also writes that shortest-path tree as a draw.io
diagram (default ``tools/dependency_tree.drawio``), colored by license:
green = allowed, red = declares a GPL-family license (read it -- dual
licenses and linking exceptions land here too), yellow = anything else
needing review. Dev-only packages have a dashed border.

Usage:
    uv run python tools/check_licenses.py                 # generate + check
    uv run python tools/check_licenses.py --generate-only
    uv run python tools/check_licenses.py --check-only
    uv run python tools/check_licenses.py --generate-only --drawio
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import deque
from importlib import metadata
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

TOOLS_DIR = Path(__file__).resolve().parent
JSON_PATH = TOOLS_DIR / "licenses.json"
PYPROJECT_PATH = TOOLS_DIR.parent / "pyproject.toml"
ROOT_NAME = str(canonicalize_name("tango-core"))
DEV_EXTRA = "dev"
DEFAULT_DRAWIO_PATH = TOOLS_DIR / "dependency_tree.drawio"

ALLOWED_LICENSES = {
    "mit",
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "bsd",
    "isc",
    "mpl-2.0",
    "psf",
    "python software foundation",
    "python software foundation license",
    "unlicense",
    "python license",
    "hpnd",
}

LICENSE_ALIASES = {
    "mit license": "mit",
    "apache software license": "apache-2.0",
    "apache 2.0": "apache-2.0",
    "bsd license": "bsd",
    "isc license (iscl)": "isc",
    "historical permission notice and disclaimer (hpnd)": "hpnd",
    "mozilla public license 2.0": "mpl-2.0",
    "gnu general public license v2 (gplv2)": "gplv2",
    "gnu general public license v3 (gplv3)": "gplv3",
    "lgpl": "lgpl",
    "agpl": "agpl",
    "other/proprietary license": "proprietary",
}


def normalize_license(license_str: str) -> str:
    """Normalize a license string to a canonical lowercase form for comparison."""
    license_str = license_str.lower().strip()
    license_str = re.sub(r"[\s]+", " ", license_str)
    license_str = license_str.replace("license", "").strip()
    license_str = license_str.replace("software", "").strip()
    license_str = license_str.replace("historical permission notice and disclaimer", "hpnd")
    license_str = license_str.replace("the unlicense", "unlicense")
    license_str = license_str.replace("the un (un)", "unlicense")
    license_str = license_str.replace("python software foundation", "psf")
    license_str = license_str.replace("python  foundation", "psf")

    if "apache" in license_str:
        return "apache-2.0"
    if (
        "python software foundation" in license_str
        or "psf" in license_str
        or "python foundation" in license_str
    ):
        return "psf"
    if "isc" in license_str:
        return "isc"
    if "mozilla public license" in license_str or "mpl 2.0" in license_str:
        return "mpl-2.0"
    if "hpnd" in license_str:
        return "hpnd"
    if "unlicense" in license_str:
        return "unlicense"
    if "gnu general public license v2" in license_str or "gplv2" in license_str:
        return "gplv2"
    if "gnu general public license v3" in license_str or "gplv3" in license_str:
        return "gplv3"

    for key, value in LICENSE_ALIASES.items():
        if key in license_str:
            return value

    return license_str


def _license_for(dist: metadata.Distribution) -> str:
    """Best-effort license lookup for an installed distribution.

    Newer packages (PEP 639) only populate `License-Expression`; older ones
    populate the legacy `License` field or a `License ::` classifier.
    """
    expression = dist.metadata.get("License-Expression")
    if expression and expression.strip():
        return expression.strip()

    license_field = dist.metadata.get("License")
    if license_field and license_field.strip() and license_field.strip().upper() != "UNKNOWN":
        return license_field.strip()

    for classifier in dist.metadata.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            return classifier.split("::")[-1].strip()

    return "Unknown"


def _canonical(name: str) -> str:
    """PEP 503-normalized package name, as a plain ``str`` for use as a dict key."""
    return str(canonicalize_name(name))


def _requirements(dist: metadata.Distribution, extra: str | None) -> list[Requirement]:
    """Requirements of ``dist`` active in this environment, for its base install or one extra.

    ``extra=None`` returns the base requirements; ``extra="x"`` returns the
    ones pulled in only by requesting ``dist[x]``. Environment markers
    (python version, platform, ...) are evaluated against the running
    interpreter, so the graph matches what is actually installed.
    """
    active = []
    for req_str in dist.requires or []:
        req = Requirement(req_str)
        if req.marker is None:
            if extra is None:
                active.append(req)
        elif extra is None:
            if req.marker.evaluate({"extra": ""}):
                active.append(req)
        elif req.marker.evaluate({"extra": extra}) and not req.marker.evaluate({"extra": ""}):
            active.append(req)
    return active


def _dev_group_requirements() -> list[Requirement]:
    """The ``[dependency-groups] dev`` entries from pyproject.toml (not in installed metadata)."""
    with PYPROJECT_PATH.open("rb") as f:
        groups = tomllib.load(f).get("dependency-groups", {})
    return [Requirement(entry) for entry in groups.get(DEV_EXTRA, []) if isinstance(entry, str)]


def _walk(
    dists: dict[str, metadata.Distribution],
    seeds: list[tuple[str, str | None]],
) -> tuple[dict[str, int], dict[str, str], dict[str, set[str]]]:
    """Breadth-first walk from ``seeds`` (depth-1 nodes).

    Returns each reachable package's depth, its parent on one shortest
    chain from ``tango-core`` (the first requirer the walk reached it
    through), and every package that requires it.

    Graph nodes are ``(package, extra)`` pairs so that requesting
    ``pkg[extra]`` also follows the requirements that extra adds.
    """
    depth: dict[str, int] = {}
    parent: dict[str, str] = {}
    required_by: dict[str, set[str]] = {}
    queue: deque[tuple[str, str | None, int, str]] = deque(
        (name, extra, 1, ROOT_NAME) for name, extra in seeds
    )
    seen: set[tuple[str, str | None]] = set()
    while queue:
        name, extra, level, via = queue.popleft()
        if (name, extra) in seen or name not in dists:
            continue
        seen.add((name, extra))
        if name not in depth:
            # breadth-first, so the first visit is at the shortest depth
            depth[name] = level
            parent[name] = via
        for req in _requirements(dists[name], extra):
            child = _canonical(req.name)
            required_by.setdefault(child, set()).add(name)
            queue.append((child, None, level + 1, name))
            queue.extend((child, child_extra, level + 1, name) for child_extra in req.extras)
    return depth, parent, required_by


def _dependency_graph(
    dists: dict[str, metadata.Distribution],
) -> tuple[dict[str, int], dict[str, str], dict[str, int], dict[str, str], dict[str, set[str]]]:
    """Depth and shortest-path parent at runtime, the same with dev tooling, and requirers of each package."""
    runtime_seeds = [
        (_canonical(req.name), extra)
        for req in _requirements(dists[ROOT_NAME], None)
        for extra in (None, *req.extras)
    ]
    dev_seeds = list(runtime_seeds)
    dev_seeds += [
        (_canonical(req.name), extra)
        for req in _requirements(dists[ROOT_NAME], DEV_EXTRA)
        for extra in (None, *req.extras)
    ]
    for req in _dev_group_requirements():
        name = _canonical(req.name)
        if name == ROOT_NAME:
            # `tango-core[dev]` in the group: its extras' requirements are direct dev deps
            dev_seeds += [
                (_canonical(r.name), extra)
                for group_extra in req.extras
                for r in _requirements(dists[ROOT_NAME], group_extra)
                for extra in (None, *r.extras)
            ]
        else:
            dev_seeds += [(name, extra) for extra in (None, *req.extras)]

    runtime_depth, runtime_parent, runtime_required_by = _walk(dists, runtime_seeds)
    dev_depth, dev_parent, required_by = _walk(dists, dev_seeds)
    for name, parents in runtime_required_by.items():
        required_by.setdefault(name, set()).update(parents)
    for name, _ in runtime_seeds + dev_seeds:
        required_by.setdefault(name, set()).add(ROOT_NAME)
    return runtime_depth, runtime_parent, dev_depth, dev_parent, required_by


def generate_license_data() -> list[dict[str, Any]]:
    """Collect license and dependency-graph info for every package installed in the current environment."""
    dists = {
        _canonical(dist.metadata["Name"]): dist
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    }
    runtime_depth, runtime_parent, dev_depth, dev_parent, required_by = _dependency_graph(dists)

    data: list[dict[str, Any]] = []
    for name, dist in dists.items():
        if name == ROOT_NAME:
            continue
        parent: str | None
        if name in runtime_depth:
            scope, depth, parent = "runtime", runtime_depth[name], runtime_parent[name]
        elif name in dev_depth:
            scope, depth, parent = "dev", dev_depth[name], dev_parent[name]
        else:
            scope, depth, parent = "unreferenced", None, None
        data.append(
            {
                "Name": dist.metadata["Name"],
                "License": _license_for(dist),
                "Direct": depth == 1,
                "Depth": depth,
                "Scope": scope,
                "RequiredBy": sorted(required_by.get(name, set())),
                "Parent": parent,
            },
        )
    data.sort(key=lambda pkg: pkg["Name"].lower())
    return data


def write_license_data(data: list[dict[str, Any]]) -> None:
    """Write license data to licenses.json."""
    with JSON_PATH.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print(f"Wrote {len(data)} packages to {JSON_PATH.relative_to(TOOLS_DIR.parent)}")


def _graph_note(pkg: dict[str, Any]) -> str:
    """`` [runtime, depth 2, via x, y]``-style suffix; empty for a licenses.json without graph fields."""
    if "Scope" not in pkg:
        return ""
    depth = "direct" if pkg["Direct"] else f"depth {pkg['Depth']}" if pkg["Depth"] is not None else "no depth"
    via = [parent for parent in pkg["RequiredBy"] if parent != ROOT_NAME]
    return (
        f"  [{pkg['Scope']}, {depth}" + (f", via {', '.join(via)}" if via and not pkg["Direct"] else "") + "]"
    )


def _is_allowed(license_str: str) -> bool:
    """True if every license named in ``license_str`` normalizes into ``ALLOWED_LICENSES``."""
    parts = {normalize_license(lic.strip()) for lic in license_str.replace(";", ",").split(",")}
    return parts.issubset(ALLOWED_LICENSES)


def check_compliance(data: list[dict[str, Any]]) -> bool:
    """Print a compliance report; return True if every package is allowed."""
    all_licenses = {normalize_license(pkg["License"]) for pkg in data}
    print("\nUnique normalized licenses detected:\n", all_licenses)

    violations = []
    for pkg in data:
        pkg_name = pkg.get("Name", "UNKNOWN")
        pkg_license = pkg.get("License", "UNKNOWN")
        if not _is_allowed(pkg_license):
            violations.append((pkg_name, pkg_license, _graph_note(pkg)))

    if violations:
        print("\nFound non-compliant licenses:")
        for name, license_str, note in violations:
            print(f"  - {name}: {license_str}{note}")
        print("\nAction required: Consider removing or replacing these packages.\n")
        return False

    print("\nAll packages have compliant licenses.")
    return True


# draw.io node fill/stroke per license class; dev-scope nodes additionally get a dashed border
LICENSE_CLASS_STYLE = {
    "allowed": ("#d5e8d4", "#82b366"),
    "mentions-gpl": ("#f8cecc", "#b85450"),
    "review": ("#fff2cc", "#d6b656"),
}
NODE_WIDTH = 190
NODE_HEIGHT = 34
COLUMN_GAP = 60
ROW_GAP = 8


def _license_class(license_str: str) -> str:
    """``allowed`` / ``mentions-gpl`` / ``review`` bucket used to color draw.io nodes.

    ``mentions-gpl`` means the declared license (its first line) names a
    GPL-family license -- including dual licenses (``Apache-2.0 OR
    GPL-2.0``) and linking exceptions -- so it flags what needs reading, not
    a verdict. Packages that put their whole license text in metadata often
    mention GPL further down only for bundled third-party components; those
    land in ``review`` instead.
    """
    if _is_allowed(license_str):
        return "allowed"
    if re.search(r"\b(A|L)?GPL", _short_license(license_str, limit=10_000), re.IGNORECASE):
        return "mentions-gpl"
    return "review"


def _short_license(license_str: str, limit: int = 40) -> str:
    """First line of a license string, truncated -- some packages put the whole license text here."""
    first_line = license_str.strip().splitlines()[0] if license_str.strip() else "Unknown"
    return first_line if len(first_line) <= limit else first_line[: limit - 1] + "…"


def write_dependency_tree(data: list[dict[str, Any]], path: Path) -> None:
    """Write the shortest-path dependency tree rooted at ``tango-core`` as a draw.io diagram.

    Each package appears once, under its ``Parent`` (so this is a tree, not
    the full graph -- ``RequiredBy`` in licenses.json lists every
    requirer). Depth runs left to right, one column per level; nodes are
    colored by ``_license_class``, and dev-scope nodes have a dashed
    border. Unreferenced packages are left out.
    """
    by_name = {_canonical(pkg["Name"]): pkg for pkg in data if pkg.get("Parent")}
    children: dict[str, list[str]] = {}
    for name, pkg in by_name.items():
        children.setdefault(_canonical(pkg["Parent"]), []).append(name)
    for kids in children.values():
        # runtime subtrees above dev ones, then alphabetical
        kids.sort(key=lambda name: (by_name[name]["Scope"] != "runtime", name))

    # tidy-tree layout: leaves take consecutive rows, parents sit centered on their children
    row_of: dict[str, float] = {}
    next_row = 0

    def place(name: str) -> float:
        nonlocal next_row
        kids = children.get(name, [])
        if kids:
            rows = [place(kid) for kid in kids]
            row_of[name] = (rows[0] + rows[-1]) / 2
        else:
            row_of[name] = next_row
            next_row += 1
        return row_of[name]

    place(ROOT_NAME)

    def cell_id(name: str) -> str:
        return "pkg-" + name

    cells = ['<mxCell id="0" />', '<mxCell id="1" parent="0" />']
    for name, row in row_of.items():
        pkg = by_name.get(name)
        depth = pkg["Depth"] if pkg else 0
        x = depth * (NODE_WIDTH + COLUMN_GAP)
        y = row * (NODE_HEIGHT + ROW_GAP)
        if pkg is None:
            label, fill, stroke, dashed = "<b>tango-core</b>", "#dae8fc", "#6c8ebf", 0
        else:
            fill, stroke = LICENSE_CLASS_STYLE[_license_class(pkg["License"])]
            dashed = int(pkg["Scope"] == "dev")
            label = f"<b>{escape(pkg['Name'])}</b><br>{escape(_short_license(pkg['License']))}"
        style = f"rounded=1;whiteSpace=wrap;html=1;fontSize=10;fillColor={fill};strokeColor={stroke};dashed={dashed};"
        cells.append(
            f"<mxCell id={quoteattr(cell_id(name))} value={quoteattr(label)} style={quoteattr(style)} "
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{NODE_WIDTH}" height="{NODE_HEIGHT}" '
            'as="geometry" /></mxCell>',
        )
    for name, pkg in by_name.items():
        if name not in row_of:
            continue
        cells.append(
            f'<mxCell id={quoteattr("edge-" + name)} edge="1" parent="1" '
            f"source={quoteattr(cell_id(_canonical(pkg['Parent'])))} target={quoteattr(cell_id(name))} "
            'style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=none;strokeColor=#999999;'
            'exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;">'
            '<mxGeometry relative="1" as="geometry" /></mxCell>',
        )

    xml = (
        '<mxfile host="tools/check_licenses.py">\n'
        '  <diagram name="Dependency tree" id="dependency-tree">\n'
        '    <mxGraphModel grid="0" page="0">\n'
        "      <root>\n        " + "\n        ".join(cells) + "\n      </root>\n"
        "    </mxGraphModel>\n  </diagram>\n</mxfile>\n"
    )
    path.write_text(xml)
    print(f"Wrote dependency tree ({len(row_of) - 1} packages) to {path}")


def main() -> int:
    """Parse CLI args and run the requested generate/check steps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Only regenerate licenses.json, skip the compliance check.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check compliance against the existing licenses.json, skip regenerating it.",
    )
    parser.add_argument(
        "--drawio",
        nargs="?",
        const=DEFAULT_DRAWIO_PATH,
        type=Path,
        metavar="PATH",
        help=f"Also write the dependency tree as a draw.io diagram (default: {DEFAULT_DRAWIO_PATH.name}).",
    )
    args = parser.parse_args()

    if args.check_only:
        with JSON_PATH.open() as f:
            data = json.load(f)
    else:
        data = generate_license_data()
        write_license_data(data)
    if args.drawio:
        write_dependency_tree(data, args.drawio)
    if args.generate_only:
        return 0

    return 0 if check_compliance(data) else 1


if __name__ == "__main__":
    sys.exit(main())
