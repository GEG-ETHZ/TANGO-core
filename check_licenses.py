import json
import sys

# Define normalized allowed licenses
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
# License aliases to normalize inconsistencies
LICENSE_ALIASES = {
    "mit license": "mit",
    "apache software license": "apache-2.0",
    "apache 2.0": "apache-2.0",
    "bsd license": "bsd",
    "isc license (iscl)": "isc",  # Fix ISCL format issue
    "historical permission notice and disclaimer (hpnd)": "hpnd",
    "mozilla public license 2.0": "mpl-2.0",
    "gnu general public license v2 (gplv2)": "gplv2",
    "gnu general public license v3 (gplv3)": "gplv3",
    "lgpl": "lgpl",
    "agpl": "agpl",
    "other/proprietary license": "proprietary",
}

import re


def normalize_license(license_str):
    license_str = license_str.lower().strip()

    # Remove extra spaces and clean up text
    license_str = re.sub(r"[\s]+", " ", license_str)  # Normalize multiple spaces to single space
    license_str = license_str.replace("license", "").strip()
    license_str = license_str.replace("software", "").strip()  # Fix "Apache Software License"
    license_str = license_str.replace("historical permission notice and disclaimer", "hpnd")
    license_str = license_str.replace("the unlicense", "unlicense")  # Fix Unlicense variations
    license_str = license_str.replace("the un (un)", "unlicense")  # Fix incorrect Unlicense format
    license_str = license_str.replace("python software foundation", "psf")  # Fix PSF license
    license_str = license_str.replace("python  foundation", "psf")  # Fix incorrect PSF format

    # Additional fixes for common variations
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
    if "unlicense" in license_str or "the unlicense" in license_str:
        return "unlicense"
    if "gnu general public license v2" in license_str or "gplv2" in license_str:
        return "gplv2"
    if "gnu general public license v3" in license_str or "gplv3" in license_str:
        return "gplv3"

    # Check against aliases
    for key, value in LICENSE_ALIASES.items():
        if key in license_str:
            return value

    return license_str  # Return as is if no match


# Load the licenses.json file
with open("licenses.json") as f:
    data = json.load(f)

# Debug: Print all unique normalized licenses before checking violations
all_licenses = {normalize_license(pkg["License"]) for pkg in data}
print("\n✅ Unique normalized licenses detected:\n", all_licenses)

# Check for non-compliant licenses
violations = []
for pkg in data:
    pkg_name = pkg.get("Name", "UNKNOWN")
    pkg_license = pkg.get("License", "UNKNOWN")

    # Normalize and split multiple licenses
    pkg_licenses = {normalize_license(lic.strip()) for lic in pkg_license.replace(";", ",").split(",")}

    # Check if any license is not in the allowed list
    if not pkg_licenses.issubset(ALLOWED_LICENSES):
        violations.append((pkg_name, pkg_license))

# Print results
if violations:
    print("\n❌ Found non-compliant licenses:")
    for name, license in violations:
        print(f"  - {name}: {license}")

    print("\n🚨 Action required: Consider removing or replacing these packages.\n")
    sys.exit(1)  # Exit with error code 1 to fail in CI/CD

else:
    print("\n✅ All packages have compliant licenses.")
    sys.exit(0)  # Exit successfully
