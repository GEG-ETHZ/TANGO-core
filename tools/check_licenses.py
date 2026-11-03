# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Generate and check third-party package license compliance.

Two steps, runnable together or separately:

1. **Generate** (``--generate-only``): inspect the packages installed in the
   current environment and write one entry per package to
   ``tools/licenses.json``. By default only runtime dependencies of
   ``tango-core`` are included -- what a user of ``tango-core`` actually
   gets; pass ``--dev`` to also include dev tooling and anything else
   installed. The license comes from the package's own
   metadata (``License-Expression``, else ``License``, else a
   ``License ::`` classifier, else ``"Unknown"``).
2. **Check** (``--check-only``): normalize each entry's license string and
   compare it against ``ALLOWED_LICENSES``. Every package that isn't
   allowed, including ``"Unknown"`` ones, is listed along with its scope
   and depth, and the script exits 1. If all are allowed it exits 0.

Because the input is the installed environment, not ``pyproject.toml`` or
``uv.lock``, run it from a fully synced environment (``uv sync``) so the
report covers exactly what ships (and, with ``--dev``, what the dev
tooling pulls in).

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
  (e.g. installed by hand). Without ``--dev`` every entry is ``"runtime"``.
- ``RequiredBy``: installed packages that directly require it
  (``tango-core`` included).
- ``Parent``: the requirer on one shortest chain from ``tango-core``;
  following ``Parent`` links back to ``tango-core`` gives that chain.

``--drawio [PATH]`` also writes that shortest-path tree as a draw.io
diagram (default ``tools/dependency_tree.drawio``), colored by license:
green = allowed, red = declares a GPL-family license (read it -- dual
licenses and linking exceptions land here too), yellow = anything else
needing review. With ``--dev``, dev-only packages have a dashed border.

Usage:
    uv run python tools/check_licenses.py                 # generate + check
    uv run python tools/check_licenses.py --generate-only
    uv run python tools/check_licenses.py --check-only
    uv run python tools/check_licenses.py --generate-only --drawio
    uv run python tools/check_licenses.py --dev          # include dev tooling
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
    "epl",
    "zpl-2.1",
    "mit-cmu",
    "tcl",
    "psf",
    "python software foundation",
    "python software foundation license",
    "unlicense",
    "python license",
    "hpnd",
}

# Packages whose license fails the automatic check but has been reviewed by a
# person and judged fine: canonical package name -> (the License string that
# was reviewed -- its first line, for packages that put full license text
# there -- and why it's fine). The approval only applies while the installed
# license still matches, so a relicensed package gets flagged for review again.
REVIEWED_PACKAGES: dict[str, tuple[str, str]] = {
    "pygit2": (
        "GPLv2 with linking exception",
        "linking exception grants unlimited permission to link pygit2 into other programs "
        "and distribute the combination; GPL still applies to modifying pygit2 or "
        "distributing it on its own (see pygit2's COPYING)",
    ),
    "google-crc32c": (
        "Unknown",
        "Apache-2.0: no license metadata, but the bundled dist-info/licenses/LICENSE is the Apache License 2.0",
    ),
    "python-dateutil": (
        "Dual License",
        "Apache-2.0 (contributions since 2017) and BSD-3-Clause (earlier code), per the bundled LICENSE; "
        "both allowed",
    ),
    "graphemeu": (
        "Copyright (c) 2017 The Python Packaging Authority (PyPA)",
        "MIT: the License field holds the MIT license text, starting with its copyright lines",
    ),
    "docutils": (
        "Public Domain, Python Software Foundation License, BSD License, GNU General Public License (GPL)",
        "installed files are public domain, BSD-2/3-Clause, or ZPL-2.1 per the bundled COPYING.txt; its only "
        "GPL file (tools/editors/emacs/rst.el) is not part of the installed package; "
        "checked by Chad Baker and Dieter, 2026-10-01",
    ),
    "rope": (
        "LGPL-3.0-or-later",
        "LGPL, dev-only (pulled in by pylsp-rope for editor refactoring support); never shipped; "
        "approved by Chad Baker, 2026-10-01",
    ),
    "pytoolconfig": (
        "LGPL-3.0-or-later",
        "LGPL, dev-only (pulled in by rope); never shipped; approved by Chad Baker, 2026-10-01",
    ),
    "docstring-to-markdown": (
        "LGPL-2.1-or-later",
        "LGPL, dev-only (pulled in by python-lsp-server); never shipped; approved by Chad Baker, 2026-10-01",
    ),
    "coolprop": (
        "Unknown",
        'MIT: v6.8.0\'s pyproject.toml declares license = "MIT", but its custom build backend '
        "drops license metadata from the wheel "
        "(https://github.com/CoolProp/CoolProp/blob/v6.8.0/pyproject.toml)",
    ),
}

LICENSE_ALIASES = {
    "mit license": "mit",
    "apache software license": "apache-2.0",
    "apache 2.0": "apache-2.0",
    "bsd license": "bsd",
    "new bsd": "bsd",
    "3-clause bsd": "bsd-3-clause",
    "zope public": "zpl-2.1",
    "isc license (iscl)": "isc",
    "historical permission notice and disclaimer (hpnd)": "hpnd",
    "mozilla public license 2.0": "mpl-2.0",
    "gnu general public license v2 (gplv2)": "gplv2",
    "gnu general public license v3 (gplv3)": "gplv3",
    "lgpl": "lgpl",
    "agpl": "agpl",
    "other/proprietary license": "proprietary",
}


def _strip_quotes(license_str: str) -> str:
    """Drop quotes wrapping a whole license string, e.g. ``'MIT'`` -> ``MIT``.

    Some packages write their ``License`` value with literal quotes (a
    ``setup.py``/``setup.cfg`` quoting slip), which would otherwise keep it
    from matching any known license.
    """
    license_str = license_str.strip()
    while len(license_str) >= 2 and license_str[0] == license_str[-1] and license_str[0] in "'\"":
        license_str = license_str[1:-1].strip()
    return license_str


def normalize_license(license_str: str) -> str:
    """Normalize a license string to a canonical lowercase form for comparison."""
    license_str = _strip_quotes(license_str).lower()
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
    if "eclipse public" in license_str or re.match(r"epl\b|eplv?\d", license_str):
        return "epl"
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

    In order of preference:

    1. ``License-Expression`` (PEP 639), e.g. ``MIT OR Apache-2.0``.
    2. The legacy ``License`` field, if it holds a license *name* -- a short,
       single line.
    3. ``License ::`` classifiers, e.g. ``License :: OSI Approved :: MIT
       License`` -> ``MIT License``. Several are joined with ``", "``, which
       ``_is_allowed`` treats as AND (the conservative reading).
    4. The ``License`` field even if it holds the full license text; such
       text can't be checked automatically, so ``_is_allowed`` leaves it for
       review.
    5. ``"Unknown"``.

    Many packages put their whole license text in ``License`` *and* declare
    a classifier, so preferring the classifier over the text (3 before 4)
    is what lets them be checked at all.
    """
    expression = dist.metadata.get("License-Expression")
    if expression and expression.strip():
        return _strip_quotes(expression)

    license_field = _strip_quotes(dist.metadata.get("License") or "")
    if license_field.upper() == "UNKNOWN":
        license_field = ""
    if license_field and "\n" not in license_field and len(license_field) <= _MAX_EXPRESSION_LENGTH:
        return license_field

    classifiers = [
        classifier.split("::")[-1].strip()
        for classifier in dist.metadata.get_all("Classifier") or []
        if classifier.startswith("License ::")
    ]
    # "License :: OSI Approved" on its own names no license
    classifiers = [name for name in classifiers if name != "OSI Approved"]
    if classifiers:
        return ", ".join(dict.fromkeys(classifiers))

    if license_field:
        return license_field

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
    # First match wins, the same rule importlib.metadata.distribution() uses: a
    # stale *.egg-info lying around on sys.path (e.g. from an old
    # `pip install -e .`) must not shadow the package that's actually installed.
    dists: dict[str, metadata.Distribution] = {}
    for dist in metadata.distributions():
        if dist.metadata.get("Name"):
            dists.setdefault(_canonical(dist.metadata["Name"]), dist)
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


def _filter_scope(data: list[dict[str, Any]], *, include_dev: bool) -> list[dict[str, Any]]:
    """Keep only runtime entries unless ``include_dev``.

    Entries without a ``Scope`` (a licenses.json written before scopes were
    recorded) are kept, since there's no way to tell what they are.
    """
    if include_dev:
        return data
    return [pkg for pkg in data if pkg.get("Scope", "runtime") == "runtime"]


def write_license_data(data: list[dict[str, Any]]) -> None:
    """Write license data to licenses.json."""
    with JSON_PATH.open("w", encoding="utf-8") as f:
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


# splits a license expression into operators, parentheses, and license terms;
# operators must be whitespace-delimited words so e.g. "GPL-2.0-or-later" stays one term
_EXPRESSION_TOKEN = re.compile(r"(\(|\)|\s+(?:OR|AND|WITH)\s+|\||&|,|;)", re.IGNORECASE)
# an operator anywhere means the string is an expression, not one license name;
# without one, parentheses are part of the name, e.g. "ISC License (ISCL)"
_HAS_OPERATOR = re.compile(r"\s(?:OR|AND|WITH)\s|[|&,;]", re.IGNORECASE)
# longer than this, or multi-line, and it's license prose, not an expression
_MAX_EXPRESSION_LENGTH = 200


def _is_allowed(license_str: str) -> bool:
    """True if ``license_str`` permits use under ``ALLOWED_LICENSES``.

    Short, single-line strings are evaluated as license expressions (SPDX
    style, plus the looser spellings packages actually use):

    - ``A OR B`` / ``A | B``: allowed if either side is -- the user may
      pick the permissive alternative (e.g. ``GPLv2 | EPLv1``).
    - ``A AND B`` / ``A & B`` / ``A, B`` / ``A; B``: allowed only if both are.
    - ``A WITH exception``: judged on ``A`` alone, since an exception only
      grants extra permissions.
    - Parentheses group as usual; AND binds tighter than OR.

    A string with no operator is a single license name, parentheses and
    all. Anything longer or multi-line (packages that put their full
    license text in the ``License`` field) is never allowed automatically:
    its prose contains "or"/"and" that aren't operators, and substring
    matching on it is unreliable (e.g. "isc" inside "disclaimer"), so it
    is left for a human to read.
    """
    text = license_str.strip()
    if "\n" in text or len(text) > _MAX_EXPRESSION_LENGTH:
        return False
    # "Apache License, Version 2.0": the comma is part of the name, not an AND
    text = re.sub(r",\s*(version\b)", r" \1", text, flags=re.IGNORECASE)
    if not _HAS_OPERATOR.search(text):
        return normalize_license(text) in ALLOWED_LICENSES
    tokens = [token.strip() for token in _EXPRESSION_TOKEN.split(text) if token.strip()]
    tokens = [{"|": "OR", "&": "AND", ",": "AND", ";": "AND"}.get(token, token) for token in tokens]
    position = 0

    def peek() -> str | None:
        return tokens[position].upper() if position < len(tokens) else None

    def parse_or() -> bool:
        nonlocal position
        allowed = parse_and()
        while peek() == "OR":
            position += 1
            allowed = parse_and() or allowed
        return allowed

    def parse_and() -> bool:
        nonlocal position
        allowed = parse_term()
        while peek() == "AND":
            position += 1
            allowed = parse_term() and allowed
        return allowed

    def parse_term() -> bool:
        nonlocal position
        if peek() == "(":
            position += 1
            allowed = parse_or()
            if peek() == ")":
                position += 1
        elif peek() is None or peek() in {"OR", "AND", "WITH", ")"}:
            # malformed expression: nothing here to allow
            allowed = False
        else:
            allowed = normalize_license(tokens[position]) in ALLOWED_LICENSES
            position += 1
        if peek() == "WITH":
            position += 2  # skip WITH and the exception identifier
        return allowed

    allowed = parse_or()
    # trailing tokens mean the expression didn't parse cleanly; don't guess
    return allowed and position >= len(tokens)


def _review_status(pkg: dict[str, Any]) -> str | None:
    """``"approved"`` if ``REVIEWED_PACKAGES`` covers this exact license, ``"stale"`` if the
    package was reviewed under a different license string, else ``None``.
    """
    review = REVIEWED_PACKAGES.get(_canonical(pkg.get("Name", "")))
    if review is None:
        return None
    installed = (pkg.get("License") or "").strip()
    first_line = installed.splitlines()[0].strip() if installed else ""
    return "approved" if review[0] in {installed, first_line} else "stale"


def _is_package_allowed(pkg: dict[str, Any]) -> bool:
    """True if the package's license passes ``_is_allowed`` or a matching manual review."""
    return _is_allowed(pkg.get("License", "UNKNOWN")) or _review_status(pkg) == "approved"


def check_compliance(data: list[dict[str, Any]]) -> bool:
    """Print a compliance report; return True if every package is allowed."""
    all_licenses = {normalize_license(pkg["License"]) for pkg in data}
    print("\nUnique normalized licenses detected:\n", all_licenses)

    violations = []
    for pkg in data:
        pkg_name = pkg.get("Name", "UNKNOWN")
        pkg_license = pkg.get("License", "UNKNOWN")
        if _is_package_allowed(pkg):
            continue
        note = _graph_note(pkg)
        if _review_status(pkg) == "stale":
            reviewed_license = REVIEWED_PACKAGES[_canonical(pkg_name)][0]
            note += f"  (license changed since manual review of {reviewed_license!r})"
        violations.append((pkg_name, pkg_license, note))

    approved = [
        pkg for pkg in data if not _is_allowed(pkg.get("License", "")) and _review_status(pkg) == "approved"
    ]
    if approved:
        print("\nAllowed by manual review (REVIEWED_PACKAGES):")
        for pkg in approved:
            print(
                f"  - {pkg['Name']}: {_short_license(pkg['License'])} -- {REVIEWED_PACKAGES[_canonical(pkg['Name'])][1]}",
            )

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


def _license_class(pkg: dict[str, Any]) -> str:
    """``allowed`` / ``mentions-gpl`` / ``review`` bucket used to color draw.io nodes.

    ``allowed`` includes packages approved via ``REVIEWED_PACKAGES``.

    ``mentions-gpl`` means the declared license (its first line) names a
    GPL-family license -- including dual licenses (``Apache-2.0 OR
    GPL-2.0``) and linking exceptions -- so it flags what needs reading, not
    a verdict. Packages that put their whole license text in metadata often
    mention GPL further down only for bundled third-party components; those
    land in ``review`` instead.
    """
    if _is_package_allowed(pkg):
        return "allowed"
    if re.search(r"\b(A|L)?GPL", _short_license(pkg["License"], limit=10_000), re.IGNORECASE):
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
            fill, stroke = LICENSE_CLASS_STYLE[_license_class(pkg)]
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
    path.write_text(xml, encoding="utf-8")
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
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Include dev dependencies (and unreferenced installed packages), not just runtime ones.",
    )
    args = parser.parse_args()

    if args.check_only:
        with JSON_PATH.open(encoding="utf-8") as f:
            data = _filter_scope(json.load(f), include_dev=args.dev)
    else:
        data = _filter_scope(generate_license_data(), include_dev=args.dev)
        write_license_data(data)
    if args.drawio:
        write_dependency_tree(data, args.drawio)
    if args.generate_only:
        return 0

    return 0 if check_compliance(data) else 1


if __name__ == "__main__":
    sys.exit(main())
