import highspy
import numpy as np
import matplotlib.pyplot as plt

# =============================================================================
# MILP: Hybrid Energy System Optimization (8760 hours/year)
# =============================================================================
# This is a framework for minimizing the cost of a hybrid energy system.
# 
# Technologies:
#   - Solar PV:        Free energy when available (based on solar profile)
#   - Battery:         Store/discharge energy (continuous power, binary on/off)
#   - Diesel Generator: Backup power (continuous power, binary on/off)
#
# Decision Variables (for each hour t = 0..8759):
#   - solar[t]:       Solar power used (continuous, 0 to available)
#   - battery[t]:     Battery discharge power (continuous)
#   - diesel[t]:      Diesel generator output (continuous)
#   - diesel_on[t]:   Diesel ON/OFF status (BINARY)
#   - battery_on[t]:  Battery discharge ON/OFF (BINARY)
#
# Objective: Minimize total operating cost
#   - Diesel fuel cost: $0.30/kWh when running
#   - Diesel startup cost: $10 per start (simplified)
#   - Battery degradation: $0.05/kWh discharged
#
# Constraints:
#   - Energy balance: solar + battery + diesel >= demand (for each hour)
#   - Diesel min/max when ON: diesel_on * P_min <= diesel <= diesel_on * P_max
#   - Battery capacity limits
# =============================================================================

HOURS_PER_YEAR = 8760

# --- Simulated Data (replace with real data later) ---
np.random.seed(42)

# Demand profile (kW) - typical daily pattern repeated
hourly_pattern = np.array([
    30, 28, 25, 24, 23, 25, 35, 50,  # 0-7h (night, morning ramp)
    70, 80, 85, 90, 88, 85, 80, 75,  # 8-15h (daytime peak)
    70, 75, 80, 70, 55, 45, 40, 35   # 16-23h (evening decline)
])
demand = np.tile(hourly_pattern, HOURS_PER_YEAR // 24 + 1)[:HOURS_PER_YEAR]
# print(demand[:100])
demand = demand + np.random.normal(0, 5, HOURS_PER_YEAR)  # Add noise
demand = np.maximum(demand, 10)  # Minimum 10 kW demand

# Solar availability (kW) - peaks at midday, zero at night
solar_pattern = np.array([
    0, 0, 0, 0, 0, 5, 20, 40,        # 0-7h
    60, 80, 95, 100, 100, 95, 80, 60, # 8-15h (peak solar)
    40, 20, 5, 0, 0, 0, 0, 0          # 16-23h
])
solar_available = np.tile(solar_pattern, HOURS_PER_YEAR // 24 + 1)[:HOURS_PER_YEAR]
solar_available = solar_available * np.random.uniform(0.7, 1.0, HOURS_PER_YEAR)  # Weather variation

# --- System Parameters ---
DELTA_T = 1.0        # Time resolution (hours) - change to 0.25 for 15-min resolution
DIESEL_MIN = 20      # Minimum output when ON (kW)
DIESEL_MAX = 100     # Maximum output (kW)
BATTERY_MAX = 50     # Maximum discharge rate (kW)
DIESEL_COST = 0.30   # $/kWh
BATTERY_COST = 0.05  # $/kWh degradation cost

print(f"Setting up MILP for {HOURS_PER_YEAR} hours...")
print(f"Average demand: {demand.mean():.1f} kW")
print(f"Average solar available: {solar_available.mean():.1f} kW")

# =============================================================================
# BUILD THE MODEL
# =============================================================================
h = highspy.Highs()
h.setOptionValue("output_flag", True)
h.setOptionValue("time_limit", 60.0)  # 60 second time limit

# Variable indices (organized for clarity)
# For each hour t, we have 5 variables:
#   0: solar[t]      - continuous [0, solar_available[t]]
#   1: battery[t]    - continuous [0, BATTERY_MAX]
#   2: diesel[t]     - continuous [0, DIESEL_MAX]
#   3: diesel_on[t]  - BINARY [0, 1]
#   4: battery_on[t] - BINARY [0, 1]

VARS_PER_HOUR = 5
IDX_SOLAR = 0
IDX_BATTERY = 1
IDX_DIESEL = 2
IDX_DIESEL_ON = 3
IDX_BATTERY_ON = 4

def var_idx(hour: int, var_type: int) -> int:
    """Get variable index for a given hour and variable type."""
    return hour * VARS_PER_HOUR + var_type

# Add all variables
print("Adding variables...")
for t in range(HOURS_PER_YEAR):
    # Solar: continuous [0, available]
    h.addVar(0, solar_available[t])
    # Battery discharge: continuous [0, max]  
    h.addVar(0, BATTERY_MAX)
    # Diesel output: continuous [0, max]
    h.addVar(0, DIESEL_MAX)
    # Diesel ON/OFF: binary
    h.addVar(0, 1)
    # Battery ON/OFF: binary
    h.addVar(0, 1)

# Set binary variables
print("Setting binary variables...")
for t in range(HOURS_PER_YEAR):
    h.changeColIntegrality(var_idx(t, IDX_DIESEL_ON), highspy.HighsVarType.kInteger)
    h.changeColIntegrality(var_idx(t, IDX_BATTERY_ON), highspy.HighsVarType.kInteger)

# Set objective: MINIMIZE cost
# Cost = sum over t of: DIESEL_COST * DELTA_T * diesel[t] + BATTERY_COST * DELTA_T * battery[t]
# Units: $/kWh * hours * kW = $
h.changeObjectiveSense(highspy.ObjSense.kMinimize)
print("Setting objective coefficients...")
for t in range(HOURS_PER_YEAR):
    h.changeColCost(var_idx(t, IDX_SOLAR), 0)                      # Solar is free
    h.changeColCost(var_idx(t, IDX_BATTERY), BATTERY_COST * DELTA_T)  # $/kWh * hr
    h.changeColCost(var_idx(t, IDX_DIESEL), DIESEL_COST * DELTA_T)    # $/kWh * hr
    h.changeColCost(var_idx(t, IDX_DIESEL_ON), 0)                  # No direct cost for ON status
    h.changeColCost(var_idx(t, IDX_BATTERY_ON), 0)

# Add constraints
print("Adding constraints...")
for t in range(HOURS_PER_YEAR):
    # Constraint 1: Energy balance
    # solar[t] + battery[t] + diesel[t] >= demand[t]
    h.addRow(
        demand[t], highspy.kHighsInf,  # lower bound = demand, upper = infinity
        3,
        [var_idx(t, IDX_SOLAR), var_idx(t, IDX_BATTERY), var_idx(t, IDX_DIESEL)],
        [1, 1, 1]
    )
    
    # Constraint 2: Diesel minimum when ON
    # diesel[t] >= DIESEL_MIN * diesel_on[t]
    # Rewritten: diesel[t] - DIESEL_MIN * diesel_on[t] >= 0
    h.addRow(
        0, highspy.kHighsInf,
        2,
        [var_idx(t, IDX_DIESEL), var_idx(t, IDX_DIESEL_ON)],
        [1, -DIESEL_MIN]
    )
    
    # Constraint 3: Diesel maximum when ON (big-M style)
    # diesel[t] <= DIESEL_MAX * diesel_on[t]
    # Rewritten: diesel[t] - DIESEL_MAX * diesel_on[t] <= 0
    h.addRow(
        -highspy.kHighsInf, 0,
        2,
        [var_idx(t, IDX_DIESEL), var_idx(t, IDX_DIESEL_ON)],
        [1, -DIESEL_MAX]
    )
    
    # Constraint 4: Battery maximum when ON
    # battery[t] <= BATTERY_MAX * battery_on[t]
    h.addRow(
        -highspy.kHighsInf, 0,
        2,
        [var_idx(t, IDX_BATTERY), var_idx(t, IDX_BATTERY_ON)],
        [1, -BATTERY_MAX]
    )

print(f"\nModel size:")
print(f"  Variables: {HOURS_PER_YEAR * VARS_PER_HOUR:,} ({HOURS_PER_YEAR * 2:,} binary)")
print(f"  Constraints: {HOURS_PER_YEAR * 4:,}")

# =============================================================================
# SOLVE
# =============================================================================
print("\n" + "="*60)
print("SOLVING...")
print("="*60)
h.run()

# =============================================================================
# RESULTS
# =============================================================================
solution = h.getSolution()
info = h.getInfo()
status = h.getModelStatus()

print("\n" + "="*60)
print("SOLUTION SUMMARY")
print("="*60)
print(f"Status: {status}")
print(f"Total Annual Cost: ${info.objective_function_value:,.2f}")

# Extract solution values
solar_used = np.array([solution.col_value[var_idx(t, IDX_SOLAR)] for t in range(HOURS_PER_YEAR)])
battery_used = np.array([solution.col_value[var_idx(t, IDX_BATTERY)] for t in range(HOURS_PER_YEAR)])
diesel_used = np.array([solution.col_value[var_idx(t, IDX_DIESEL)] for t in range(HOURS_PER_YEAR)])
diesel_on = np.array([solution.col_value[var_idx(t, IDX_DIESEL_ON)] for t in range(HOURS_PER_YEAR)])
battery_on = np.array([solution.col_value[var_idx(t, IDX_BATTERY_ON)] for t in range(HOURS_PER_YEAR)])

# Calculate energy (kWh) = power (kW) * time (hours)
solar_energy = solar_used.sum() * DELTA_T
battery_energy = battery_used.sum() * DELTA_T
diesel_energy = diesel_used.sum() * DELTA_T
total_demand_energy = demand.sum() * DELTA_T

print(f"\nEnergy Sources (annual totals):")
print(f"  Solar used:    {solar_energy:,.0f} kWh ({100*solar_energy/total_demand_energy:.1f}% of demand)")
print(f"  Battery used:  {battery_energy:,.0f} kWh ({100*battery_energy/total_demand_energy:.1f}% of demand)")
print(f"  Diesel used:   {diesel_energy:,.0f} kWh ({100*diesel_energy/total_demand_energy:.1f}% of demand)")
print(f"  Total demand:  {total_demand_energy:,.0f} kWh")

print(f"\nOperating Statistics:")
print(f"  Diesel ON hours:  {diesel_on.sum():.0f} / {HOURS_PER_YEAR} ({100*diesel_on.sum()/HOURS_PER_YEAR:.1f}%)")
print(f"  Battery ON hours: {battery_on.sum():.0f} / {HOURS_PER_YEAR} ({100*battery_on.sum()/HOURS_PER_YEAR:.1f}%)")

print(f"\nCost Breakdown:")
print(f"  Diesel cost:   ${DIESEL_COST * diesel_energy:,.2f}")
print(f"  Battery cost:  ${BATTERY_COST * battery_energy:,.2f}")
print("="*60)

# =============================================================================
# VISUALIZATION
# =============================================================================
print("\nGenerating plots...")

hours = np.arange(HOURS_PER_YEAR)

# Create figure with subplots
fig, axes = plt.subplots(3, 1, figsize=(14, 10))

# --- Plot 1: Full year stacked area ---
ax1 = axes[0]
ax1.stackplot(hours, solar_used, battery_used, diesel_used,
              labels=['Solar', 'Battery', 'Diesel'],
              colors=['#FFD700', '#4CAF50', '#FF5722'], alpha=0.8)
ax1.plot(hours, demand, 'k-', linewidth=0.5, label='Demand', alpha=0.7)
ax1.set_xlabel('Hour of Year')
ax1.set_ylabel('Power (kW)')
ax1.set_title('Energy Dispatch - Full Year (8760 hours)')
ax1.legend(loc='upper right')
ax1.set_xlim(0, HOURS_PER_YEAR)
ax1.grid(True, alpha=0.3)

# --- Plot 2: One week zoom (168 hours) ---
ax2 = axes[1]
week_start = 24 * 180  # Start at day 180 (summer)
week_end = week_start + 168
week_hours = hours[week_start:week_end] - week_start

ax2.stackplot(week_hours, 
              solar_used[week_start:week_end], 
              battery_used[week_start:week_end], 
              diesel_used[week_start:week_end],
              labels=['Solar', 'Battery', 'Diesel'],
              colors=['#FFD700', '#4CAF50', '#FF5722'], alpha=0.8)
ax2.plot(week_hours, demand[week_start:week_end], 'k-', linewidth=1.5, label='Demand')
ax2.set_xlabel('Hour of Week')
ax2.set_ylabel('Power (kW)')
ax2.set_title(f'Energy Dispatch - One Week (Day 180-187)')
ax2.legend(loc='upper right')
ax2.set_xlim(0, 168)
ax2.set_xticks(np.arange(0, 169, 24))
ax2.grid(True, alpha=0.3)

# --- Plot 3: Monthly energy breakdown ---
ax3 = axes[2]
days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

monthly_solar = []
monthly_battery = []
monthly_diesel = []

start_hour = 0
for days in days_per_month:
    end_hour = start_hour + days * 24
    monthly_solar.append(solar_used[start_hour:end_hour].sum() * DELTA_T)
    monthly_battery.append(battery_used[start_hour:end_hour].sum() * DELTA_T)
    monthly_diesel.append(diesel_used[start_hour:end_hour].sum() * DELTA_T)
    start_hour = end_hour

x = np.arange(12)
width = 0.6

ax3.bar(x, monthly_solar, width, label='Solar', color='#FFD700')
ax3.bar(x, monthly_battery, width, bottom=monthly_solar, label='Battery', color='#4CAF50')
ax3.bar(x, monthly_diesel, width, bottom=np.array(monthly_solar)+np.array(monthly_battery), 
        label='Diesel', color='#FF5722')
ax3.set_xlabel('Month')
ax3.set_ylabel('Energy (kWh)')
ax3.set_title('Monthly Energy Breakdown')
ax3.set_xticks(x)
ax3.set_xticklabels(month_names)
ax3.legend(loc='upper right')
ax3.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig('energy_dispatch.png', dpi=150, bbox_inches='tight')
print("Saved: energy_dispatch.png")
plt.show()
