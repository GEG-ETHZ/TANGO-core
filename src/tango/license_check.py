import json
import re
import subprocess
import time

import pandas as pd
import requests
import yaml
from tqdm import tqdm

env_file = "/Users/morteza/Documents/projects/TANGO/environment.yml"

with open(env_file) as file:
    env_data = yaml.safe_load(file)

packages = env_data.get("dependencies", [])
conda_packages = []
pip_packages = []

for pkg in packages:
    if isinstance(pkg, str):
        clean_pkg = re.split(r"[<>=!]", pkg)[0].strip()
        conda_packages.append(clean_pkg)
    elif isinstance(pkg, dict) and "pip" in pkg:
        pip_packages.extend(pkg["pip"])
    elif isinstance(pkg, dict):
        conda_packages.append(list(pkg.keys())[0])

pip_packages = [re.split(r"[<>=!]", pkg)[0].strip() for pkg in pip_packages]

license_info = {}

print("\n Checking Conda package licenses...")
for package in tqdm(conda_packages, desc="Processing Conda Packages", unit="pkg"):
    try:
        result = subprocess.run(["conda", "search", package, "--json"], capture_output=True, text=True)
        data = json.loads(result.stdout)

        if package in data:
            latest_version = sorted(data[package], key=lambda x: x["version"], reverse=True)[0]
            license_info[package] = latest_version.get("license", "Unknown")
        else:
            license_info[package] = "Not Found"
    except Exception as e:
        license_info[package] = f"Error: {str(e)}"

if "CoolProp" in conda_packages and license_info.get("CoolProp") == "Not Found":
    print("\n Checking CoolProp license from Anaconda API...")
    try:
        response = requests.get("https://api.anaconda.org/package/conda-forge/coolprop", timeout=5)
        if response.status_code == 200:
            data = response.json()
            license_info["CoolProp"] = data.get("license", "Unknown")
        else:
            license_info["CoolProp"] = "Not Found"
    except Exception as e:
        license_info["CoolProp"] = f"Error: {str(e)}"

print("\n Checking Pip package licenses from PyPI...")
for package in tqdm(pip_packages, desc="Processing Pip Packages", unit="pkg"):
    try:
        response = requests.get(f"https://pypi.org/pypi/{package}/json", timeout=5)
        if response.status_code == 200:
            data = response.json()
            license_info[package] = data["info"].get("license", "Unknown")

            if not license_info[package] or license_info[package] == "UNKNOWN":
                classifiers = data["info"].get("classifiers", [])
                for classifier in classifiers:
                    if "License" in classifier:
                        license_info[package] = classifier.split("::")[-1].strip()
        else:
            license_info[package] = "Not Found"
    except Exception as e:
        license_info[package] = f"Error: {str(e)}"

    time.sleep(0.3)

df = pd.DataFrame(license_info.items(), columns=["Package", "License"])
csv_filename = "conda_and_pip_package_licenses.csv"
df.to_csv(csv_filename, index=False)

print("\n License Check Complete!")
print(df.to_string(index=False))
print(f"\n License information saved to {csv_filename}")
