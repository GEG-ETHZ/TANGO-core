"""
Generate input profile figures for presentation.
Creates 4 separate figures: electricity price, ambient temperature, radiation, and demand.
Compact size for single slide layout (2x2), large fonts, simple lines.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# Set style for presentation - compact with large fonts
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['figure.figsize'] = (7, 3.5)  # Smaller for 2x2 layout
plt.rcParams['font.size'] = 14
plt.rcParams['axes.titlesize'] = 16
plt.rcParams['axes.labelsize'] = 14
plt.rcParams['xtick.labelsize'] = 12
plt.rcParams['ytick.labelsize'] = 12

# Data directory
data_dir = os.path.join(os.path.dirname(__file__), "data")
output_dir = os.path.join(os.path.dirname(__file__), "outputs", "input_profiles")
os.makedirs(output_dir, exist_ok=True)

# Hours array for x-axis
hours = np.arange(1, 8761)

# Month labels for x-axis
month_starts = [1, 745, 1417, 2161, 2881, 3625, 4345, 5089, 5833, 6553, 7297, 8017]
month_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def add_month_labels(ax):
    """Add month labels to x-axis."""
    ax.set_xticks(month_starts[::2])  # Every other month for compact view
    ax.set_xticklabels(month_labels[::2])
    ax.set_xlim(1, 8760)


# =============================================================================
# 1. Electricity Price Profile
# =============================================================================
print("Generating electricity price profile...")
df_price = pd.read_csv(os.path.join(data_dir, "Wien_2016_electricity_price_profile.csv"))

fig, ax = plt.subplots()
ax.plot(hours, df_price['Price_EUR_MWh'].values, color='black', linewidth=0.4)
ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.8, alpha=0.7)
ax.set_ylabel('Price [€/MWh]')
ax.set_xlabel('Month')
ax.set_title('Electricity Price Profile')
add_month_labels(ax)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "electricity_price_profile.png"), dpi=200, bbox_inches='tight')
plt.close()
print(f"  Saved: {output_dir}/electricity_price_profile.png")


# =============================================================================
# 2. Ambient Air Temperature Profile
# =============================================================================
print("Generating ambient temperature profile...")
df_temp = pd.read_csv(os.path.join(data_dir, "Wien_2016_temperature_profiles.csv"))

fig, ax = plt.subplots()
ax.plot(hours, df_temp['ambient_temp'].values, color='black', linewidth=0.4)
ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.8, alpha=0.7)
ax.set_ylabel('Temperature [°C]')
ax.set_xlabel('Month')
ax.set_title('Ambient Air Temperature')
add_month_labels(ax)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "ambient_temperature_profile.png"), dpi=200, bbox_inches='tight')
plt.close()
print(f"  Saved: {output_dir}/ambient_temperature_profile.png")


# =============================================================================
# 3. Solar Radiation Profile
# =============================================================================
print("Generating solar radiation profile...")
df_rad = pd.read_csv(os.path.join(data_dir, "Wien_2016_radiation_profile.csv"))

fig, ax = plt.subplots()
ax.plot(hours, df_rad['radiation_wm2'].values, color='black', linewidth=0.4)
ax.set_ylabel('Radiation [W/m²]')
ax.set_xlabel('Month')
ax.set_title('Solar Radiation Profile')
add_month_labels(ax)
ax.set_ylim(0, None)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "solar_radiation_profile.png"), dpi=200, bbox_inches='tight')
plt.close()
print(f"  Saved: {output_dir}/solar_radiation_profile.png")


# =============================================================================
# 4. Heat Demand Profile
# =============================================================================
print("Generating heat demand profile...")
df_demand = pd.read_csv(os.path.join(data_dir, "demand_profile_AT.csv"))

fig, ax = plt.subplots()
ax.plot(hours, df_demand['demand_mw'].values, color='black', linewidth=0.4)
ax.set_ylabel('Demand [MW]')
ax.set_xlabel('Month')
ax.set_title('Heat Demand Profile')
add_month_labels(ax)
ax.set_ylim(0, None)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "heat_demand_profile.png"), dpi=200, bbox_inches='tight')
plt.close()
print(f"  Saved: {output_dir}/heat_demand_profile.png")


print(f"\n✅ All 4 figures saved to: {output_dir}/")
