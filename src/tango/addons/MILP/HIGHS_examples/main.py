import highspy

# =============================================================================
# MILP Example: Factory Production Problem
# =============================================================================
# A factory produces two products:
#   - Product A: $3 profit, 2 hrs labor, 3 kg material (CONTINUOUS)
#   - Product B: $5 profit, 4 hrs labor, 2 kg material (INTEGER)
# 
# Resources: 20 labor hours, 18 kg material
# Goal: Maximize profit
#
# Mathematical formulation:
#   Maximize:   3A + 5B
#   Subject to: 2A + 4B <= 20  (labor)
#               3A + 2B <= 18  (material)
#               A >= 0         (continuous)
#               B >= 0, integer
# =============================================================================

h = highspy.Highs()
h.setOptionValue("output_flag", True)  # Show solver output

# Add variables: A (index 0) and B (index 1)
# addVar(lower_bound, upper_bound)
h.addVar(0, highspy.kHighsInf)  # A >= 0
h.addVar(0, highspy.kHighsInf)  # B >= 0

# Set B as INTEGER (this makes it a MILP!)
h.changeColIntegrality(1, highspy.HighsVarType.kInteger)

# Set objective: MAXIMIZE 3A + 5B
h.changeObjectiveSense(highspy.ObjSense.kMaximize)
h.changeColCost(0, 3)  # coefficient of A
h.changeColCost(1, 5)  # coefficient of B

# Add constraints
# addRow(lower_bound, upper_bound, num_vars, indices, coefficients)
h.addRow(-highspy.kHighsInf, 20, 2, [0, 1], [2, 4])  # 2A + 4B <= 20
h.addRow(-highspy.kHighsInf, 18, 2, [0, 1], [3, 2])  # 3A + 2B <= 18

# Solve
h.run()

# Get results
solution = h.getSolution()
info = h.getInfo()

print("\n" + "="*50)
print("SOLUTION")
print("="*50)
print(f"Product A (continuous): {solution.col_value[0]:.2f} units")
print(f"Product B (integer):    {solution.col_value[1]:.0f} units")
print(f"Maximum Profit:         ${info.objective_function_value:.2f}")
print("="*50)