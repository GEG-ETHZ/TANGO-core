"""Generate and check third-party package license compliance.

Merges what used to be two disconnected scripts (root-level
`check_licenses.py`, which checked a `licenses.json` snapshot of unclear
origin, and `src/tango/license_check.py`, which queried PyPI for packages
listed in a personal, machine-specific `environment.yml` that doesn't exist
in this repo) into one tool with a single source of truth: the packages
actually installed in the current environment.

Usage:
    uv run python tools/check_licenses.py                 # generate + check
    uv run python tools/check_licenses.py --generate-only
    uv run python tools/check_licenses.py --check-only
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from importlib import metadata
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
JSON_PATH = TOOLS_DIR / "licenses.json"
CSV_PATH = TOOLS_DIR / "conda_and_pip_package_licenses.csv"

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


def generate_license_data() -> list[dict[str, str]]:
    """Collect name/license pairs for every package installed in the current environment."""
    data = [
        {"Name": dist.metadata["Name"], "License": _license_for(dist)}
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    ]
    data.sort(key=lambda pkg: pkg["Name"].lower())
    return data


def write_license_data(data: list[dict[str, str]]) -> None:
    """Write license data to both licenses.json and the CSV, keeping them in sync."""
    with JSON_PATH.open("w") as f:
        json.dump(data, f, indent=2)

    with CSV_PATH.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Package", "License"])
        for pkg in data:
            writer.writerow([pkg["Name"], pkg["License"]])

    print(
        f"Wrote {len(data)} packages to {JSON_PATH.relative_to(TOOLS_DIR.parent)} "
        f"and {CSV_PATH.relative_to(TOOLS_DIR.parent)}",
    )


def check_compliance(data: list[dict[str, str]]) -> bool:
    """Print a compliance report; return True if every package is allowed."""
    all_licenses = {normalize_license(pkg["License"]) for pkg in data}
    print("\nUnique normalized licenses detected:\n", all_licenses)

    violations = []
    for pkg in data:
        pkg_name = pkg.get("Name", "UNKNOWN")
        pkg_license = pkg.get("License", "UNKNOWN")
        pkg_licenses = {normalize_license(lic.strip()) for lic in pkg_license.replace(";", ",").split(",")}
        if not pkg_licenses.issubset(ALLOWED_LICENSES):
            violations.append((pkg_name, pkg_license))

    if violations:
        print("\nFound non-compliant licenses:")
        for name, license_str in violations:
            print(f"  - {name}: {license_str}")
        print("\nAction required: Consider removing or replacing these packages.\n")
        return False

    print("\nAll packages have compliant licenses.")
    return True


def main() -> int:
    """Parse CLI args and run the requested generate/check steps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Only regenerate licenses.json / the CSV, skip the compliance check.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check compliance against the existing licenses.json, skip regenerating it.",
    )
    args = parser.parse_args()

    if args.check_only:
        with JSON_PATH.open() as f:
            data = json.load(f)
    else:
        data = generate_license_data()
        write_license_data(data)
        if args.generate_only:
            return 0

    return 0 if check_compliance(data) else 1


if __name__ == "__main__":
    sys.exit(main())
