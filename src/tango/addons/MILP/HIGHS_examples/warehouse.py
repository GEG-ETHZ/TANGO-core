import highspy

# =============================================================================
# MILP Example 2: Warehouse Storage Problem
# =============================================================================
# A warehouse manager allocates storage for:
#   - Large Containers (x): $8 value, 3m² space, 2 tons weight (INTEGER, max 8)
#   - Bulk Material (y):    $2/ton,  1m² space, 1 ton weight  (CONTINUOUS, max 15)
#
# Resources: 30 m² space, 25 tons weight capacity
# Goal: Maximize total value
#
# Mathematical formulation:
#   Maximize:   8x + 2y
#   Subject to: 3x + y  <= 30  (space)
#               2x + y  <= 25  (weight)
#               0 <= x <= 8,  integer
#               0 <= y <= 15
# =============================================================================

h = highspy.Highs()
h.setOptionValue("output_flag", True)

# Add variables with UPPER BOUNDS
# addVar(lower_bound, upper_bound)
h.addVar(0, 8)   # x: 0 <= x <= 8 (containers)
h.addVar(0, 15)  # y: 0 <= y <= 15 (bulk material in tons)

# Set x as INTEGER
h.changeColIntegrality(0, highspy.HighsVarType.kInteger)

# Set objective: MAXIMIZE 8x + 2y
h.changeObjectiveSense(highspy.ObjSense.kMaximize)
h.changeColCost(0, 8)  # coefficient of x
h.changeColCost(1, 2)  # coefficient of y

# Add constraints
# addRow(lower_bound, upper_bound, num_vars, indices, coefficients)
h.addRow(-highspy.kHighsInf, 30, 2, [0, 1], [3, 1])  # 3x + y <= 30 (space)
h.addRow(-highspy.kHighsInf, 25, 2, [0, 1], [2, 1])  # 2x + y <= 25 (weight)

# Solve
h.run()

# Get results
solution = h.getSolution()
info = h.getInfo()

print("\n" + "="*50)
print("SOLUTION: Warehouse Storage")
print("="*50)
print(f"Large Containers (x): {solution.col_value[0]:.0f} units  (max: 8)")
print(f"Bulk Material (y):    {solution.col_value[1]:.2f} tons   (max: 15)")
print(f"Maximum Value:        ${info.objective_function_value:.2f}")
print("="*50)

# Verify constraints
x, y = solution.col_value[0], solution.col_value[1]
print("\nConstraint Verification:")
print(f"  Space used:  {3*x + y:.1f} / 30 m²")
print(f"  Weight used: {2*x + y:.1f} / 25 tons")
print(f"  x bounds:    0 <= {x:.0f} <= 8  ✓")
print(f"  y bounds:    0 <= {y:.2f} <= 15  ✓")
