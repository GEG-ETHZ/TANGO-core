#
# import numpy as np
# from pymoo.core.problem import ElementwiseProblem
# from pymoo.algorithms.soo.nonconvex.de import DE
# from pymoo.algorithms.soo.nonconvex.ga import GA
# from pymoo.algorithms.soo.nonconvex.nelder import NelderMead
# from pymoo.algorithms.soo.nonconvex.pso import PSO
# from pymoo.algorithms.soo.nonconvex.cmaes import CMAES
# from pymoo.algorithms.soo.nonconvex.pattern import PatternSearch
# from pymoo.algorithms.soo.nonconvex.brkga import BRKGA
# from pymoo.algorithms.soo.nonconvex.es import ES
# from pymoo.algorithms.soo.nonconvex.sres import SRES
# from pymoo.algorithms.soo.nonconvex.isres import ISRES
# from pymoo.optimize import minimize
# import matplotlib.pyplot as plt
# from tango.units.dataclasses import OptimizationSpecs
# import multiprocessing
# from pymoo.core.problem import StarmapParallelization
# from functools import partial
# import time
#
#
# class Optimizer:
#
#     def __init__(self, tango_object, specs):
#         self.tango_instance = tango_object
#         self.optimization_specs = OptimizationSpecs.from_dict(self._process_specs(specs))
#         # print(self.optimization_specs)
#         self.target_parameter = self.translate_parameter(self.optimization_specs.targets[0])
#         self._method = self.optimization_specs.method
#         self._n_gen = self.optimization_specs.n_generation
#         self._parallel_processing = self.optimization_specs.parallel_processing
#         self._pop_size = self.optimization_specs.pop_size  # Take pop_size from optimization_specs
#
#     def _process_specs(self, specs) -> dict:
#         return specs['optimization']
#
#     def translate_parameter(self, parameter_name: str):
#         # Map the parameter name to the corresponding tango_instance attribute
#         translation_dict = {
#             "W_NET": "self.tango_instance.workflow.orchestrator.unit.surface.w_net",
#             "INLET_TEMP": "self.tango_instance.workflow.orchestrator.unit.surface.inlet_fluid.T"
#         }
#         return translation_dict.get(parameter_name)
#
#     def objective_func(self, x):
#         try:
#             for i, var_name in enumerate(self.optimization_specs.variables.keys()):
#                 self.set_parameter(var_name, x[i])
#
#             self.tango_instance.execute()
#
#             result = eval(self.target_parameter)
#             return result if self.optimization_specs.target_type == 'maximize' else -result
#         except Exception as e:
#             print(f"Simulation failed with error: {e}")
#             return float('-inf')
#
#     def set_parameter(self, var_name: str, value: float):
#         translation_dict = {
#             "MASS_FLOW_RATE": "self.tango_instance.specs['schedule']['mass_flow_rate']",
#             "THICKNESS": "self.tango_instance.specs['reservoir']['thickness']"
#         }
#         exec(f"{translation_dict[var_name]} = {value}")
#
#     def constraint_lower_bound_func(self, x, constraint_name, lower_bound):
#         parameter = eval(self.translate_parameter(constraint_name))
#         return lower_bound - parameter
#
#     def constraint_upper_bound_func(self, x, constraint_name, upper_bound):
#         parameter = eval(self.translate_parameter(constraint_name))
#         return parameter - upper_bound
#
#     def execute(self) -> None:
#         variable_ranges = {
#             f"x{i+1}": (specs['lower_bound'], specs['upper_bound'])
#             for i, (var_name, specs) in enumerate(self.optimization_specs.variables.items())
#         }
#         variable_types = {
#             f"x{i+1}": specs['type']
#             for i, (var_name, specs) in enumerate(self.optimization_specs.variables.items())
#         }
#
#         constraints = []
#         for constraint_name, constraint_specs in self.optimization_specs.constraints.items():
#             if 'lower_bound' in constraint_specs:
#                 constraints.append(partial(self.constraint_lower_bound_func, constraint_name=constraint_name, lower_bound=constraint_specs['lower_bound']))
#             if 'upper_bound' in constraint_specs:
#                 constraints.append(partial(self.constraint_upper_bound_func, constraint_name=constraint_name, upper_bound=constraint_specs['upper_bound']))
#
#         optimizer = MINLPOptimizer(
#             self.objective_func,
#             constraints,
#             variable_ranges,
#             variable_types,
#             algorithm_name=self._method,
#             parallel_processing=self._parallel_processing,
#             optimization_specs=self.optimization_specs
#         )
#
#         start = time.time()
#
#         optimizer.optimize(n_gen=self._n_gen)
#
#         end = time.time()
#
#         print('time:', end - start)
#
#         optimizer.print_results()
#         optimizer.plot_results()
#
#         if self._parallel_processing:
#             optimizer.close_pool()  # Close the pool after optimization is done
#         # print(self.optimization_specs)
#         # print(self.target_parameter)
#
#
# class MINLPOptimizer:
#     def __init__(self, objective_func, constraints, variable_ranges, variable_types, algorithm_name='DE', parallel_processing=False, optimization_specs=None):
#         self.optimization_specs = optimization_specs
#         self.objective_func = objective_func
#         self.constraints = constraints
#         self.variable_ranges = variable_ranges
#         self.variable_types = variable_types
#         self.algorithm_name = algorithm_name
#         self.parallel_processing = parallel_processing
#         self.pop_size = self.optimization_specs.pop_size  # Store pop_size from optimization_specs
#
#         if self.parallel_processing:
#             # Initialize multiprocessing pool for parallel execution
#             self.n_processes = self.optimization_specs.n_processes # multiprocessing.cpu_count()
#             self.pool = multiprocessing.Pool(self.n_processes)
#             self.runner = StarmapParallelization(self.pool.starmap)
#         else:
#             self.pool = None
#             self.runner = None
#
#         self.problem = self.MyMINLPProblem(objective_func, constraints, variable_ranges, variable_types, runner=self.runner)
#         self.algorithm = self.select_algorithm(algorithm_name)
#
#     class MyMINLPProblem(ElementwiseProblem):
#         def __init__(self, objective_func, constraints, variable_ranges, variable_types, runner=None):
#             self.objective_func = objective_func
#             self.constraints = constraints
#             self.variable_types = variable_types
#             n_var = len(variable_ranges)
#             xl = np.array([variable_ranges[var][0] for var in variable_ranges])
#             xu = np.array([variable_ranges[var][1] for var in variable_ranges])
#
#             if runner is not None:
#                 super().__init__(n_var=n_var,
#                                  n_obj=1,
#                                  n_ieq_constr=len(constraints),
#                                  xl=xl,
#                                  xu=xu,
#                                  elementwise_runner=runner)
#             else:
#                 super().__init__(n_var=n_var,
#                                  n_obj=1,
#                                  n_ieq_constr=len(constraints),
#                                  xl=xl,
#                                  xu=xu)
#
#         def _evaluate(self, x, out, *args, **kwargs):
#             # Apply integer constraints
#             for i, (var, vtype) in enumerate(self.variable_types.items()):
#                 if vtype == 'integer':
#                     x[i] = np.round(x[i])
#
#             # Objective function
#             out["F"] = -1 * self.objective_func(x)  # Negate to convert maximization to minimization
#
#             # Constraints
#             out["G"] = np.array([constraint(x) for constraint in self.constraints])
#
#     def select_algorithm(self, algorithm_name):
#         if algorithm_name == 'DE':
#             return DE(pop_size=self.pop_size)
#         elif algorithm_name == 'GA':
#             return GA(pop_size=self.pop_size)
#         elif algorithm_name == 'NelderMead':
#             return NelderMead()
#         elif algorithm_name == 'PSO':
#             return PSO(pop_size=self.pop_size)
#         elif algorithm_name == 'CMAES':
#             return CMAES(pop_size=self.pop_size)
#         elif algorithm_name == 'PatternSearch':
#             return PatternSearch()
#         elif algorithm_name == 'BRKGA':
#             return BRKGA()
#         elif algorithm_name == 'ES':
#             return ES()
#         elif algorithm_name == 'SRES':
#             return SRES()
#         elif algorithm_name == 'ISRES':
#             return ISRES()
#         else:
#             raise ValueError(f"Algorithm {algorithm_name} not recognized. Available algorithms: DE, GA, NelderMead, PSO, CMAES, PatternSearch, BRKGA, ES, SRES, ISRES")
#
#     def optimize(self, n_gen=13):
#         # Lists to store variable values and f_min values
#         self.x_values = []
#         self.f_min_values = []
#
#         # Custom callback function to store the values
#         def callback(algorithm):
#             feas_inds = [ind for ind in algorithm.pop if np.all(ind.get("G") <= 0)]
#             if feas_inds:
#                 self.f_min_values.append(min(ind.get("F") for ind in feas_inds))
#                 best_ind = feas_inds[np.argmin([ind.get("F") for ind in feas_inds])]
#                 self.x_values.append([np.round(best_ind.X[i]) if self.variable_types[f'x{i+1}'] == 'integer' else best_ind.X[i] for i in range(len(best_ind.X))])
#
#         # Perform the optimization
#         res = minimize(self.problem,
#                        self.algorithm,
#                        ('n_gen', n_gen),
#                        verbose=True,
#                        callback=callback)
#
#         # Get the results
#         self.x_opt = res.X
#         self.f_opt = -res.F[0]  # Negate the function value to get the maximized value
#
#     def print_results(self):
#         print("Optimal Variables:", self.x_opt)
#         print("Maximum Value:", self.f_opt)
#
#         # Print the values for each generation
#         for gen in range(len(self.f_min_values)):
#             x_vals_str = ', '.join([f'x{i+1} = {self.x_values[gen][i]}' for i in range(len(self.x_values[gen]))])
#             print(f"Generation {gen + 1}: {x_vals_str}, f_min = {self.f_min_values[gen]}")
#
#     def plot_results(self):
#         generations = range(1, len(self.f_min_values) + 1)
#
#         plt.figure(figsize=(12, 6))
#
#         plt.subplot(1, 2, 1)
#         for i in range(len(self.variable_ranges)):
#             plt.plot(generations, [x[i] for x in self.x_values], label=f'x{i+1}')
#         plt.xlabel('Generation')
#         plt.ylabel('Variable Value')
#         plt.title('Variable values over Generations')
#         plt.legend()
#
#         plt.subplot(1, 2, 2)
#         plt.plot(generations, self.f_min_values, label='f_min')
#         plt.xlabel('Generation')
#         plt.ylabel('f_min Value')
#         plt.title('f_min over Generations')
#         plt.legend()
#
#         plt.tight_layout()
#         plt.show()
#
#     def plot_contours(self, resolution=100):
#         variable_names = list(self.variable_ranges.keys())
#         n_vars = len(variable_names)
#         optimal_values = self.x_opt
#
#         if n_vars == 1:
#             x_range = np.linspace(self.variable_ranges[variable_names[0]][0], self.variable_ranges[variable_names[0]][1], resolution)
#             y_values = np.zeros_like(x_range)
#
#             for i in range(resolution):
#                 x = np.copy(optimal_values)
#                 x[0] = x_range[i]
#                 y_values[i] = self.objective_func(x)
#
#             plt.figure()
#             plt.plot(x_range, y_values, label='Objective Function')
#             plt.plot(optimal_values[0], self.objective_func(optimal_values), 'ro', label='Optimum Point')
#             plt.xlabel(variable_names[0])
#             plt.ylabel('Objective Function Value')
#             plt.title(f'Plot of Objective Function\nOptimal value: {variable_names[0]} = {optimal_values[0]:.2f}')
#             plt.legend()
#             plt.show()
#         else:
#             for i in range(n_vars):
#                 for j in range(i + 1, n_vars):
#                     x1_range = np.linspace(self.variable_ranges[variable_names[i]][0], self.variable_ranges[variable_names[i]][1], resolution)
#                     x2_range = np.linspace(self.variable_ranges[variable_names[j]][0], self.variable_ranges[variable_names[j]][1], resolution)
#                     X1, X2 = np.meshgrid(x1_range, x2_range)
#                     Z = np.full_like(X1, np.nan)  # Initialize with NaNs to mark infeasible regions
#
#                     for k in range(resolution):
#                         for l in range(resolution):
#                             x = np.copy(optimal_values)
#                             x[i] = X1[k, l]
#                             x[j] = X2[k, l]
#                             if all(constraint(x) <= 0 for constraint in self.constraints):
#                                 Z[k, l] = self.objective_func(x)
#
#                     other_vars_str = ', '.join([f'{variable_names[m]} = {optimal_values[m]:.2f}' for m in range(n_vars) if m != i and m != j])
#
#                     plt.figure()
#                     cp = plt.contourf(X1, X2, Z, levels=50, cmap='viridis')
#                     plt.colorbar(cp)
#                     plt.plot(optimal_values[i], optimal_values[j], 'ro')  # Mark the optimum point
#                     plt.xlabel(variable_names[i])
#                     plt.ylabel(variable_names[j])
#                     plt.title(f'Contour plot ({variable_names[i]} vs {variable_names[j]})\nOptimal values of other variables: {other_vars_str}')
#                     plt.show()
#
#     def close_pool(self):
#         if self.pool:
#             self.pool.close()




# import numpy as np
# from pymoo.core.problem import ElementwiseProblem
# from pymoo.algorithms.moo.nsga2 import NSGA2
# from pymoo.algorithms.moo.nsga3 import NSGA3
# from pymoo.optimize import minimize
# from pymoo.core.problem import StarmapParallelization
# from pymoo.indicators.hv import Hypervolume
# from pymoo.indicators.igd import IGD
# import matplotlib.pyplot as plt
# from functools import partial
# import multiprocessing
# import time
# from tango.units.dataclasses import OptimizationSpecs
# from pymoo.operators.sampling.rnd import FloatRandomSampling
# from pymoo.operators.crossover.sbx import SBX
# from pymoo.operators.mutation.pm import PM
# from pymoo.util.reference_direction import UniformReferenceDirectionFactory
#
# class Optimizer:
#
#     def __init__(self, tango_object, specs):
#         self.tango_instance = tango_object
#         self.optimization_specs = OptimizationSpecs.from_dict(self._process_specs(specs))
#         self.target_parameters = [self.translate_parameter(target) for target in self.optimization_specs.targets]
#         self._method = self.optimization_specs.method
#         self._n_gen = self.optimization_specs.n_generation
#         self._parallel_processing = self.optimization_specs.parallel_processing
#         self._pop_size = self.optimization_specs.pop_size
#
#     def _process_specs(self, specs) -> dict:
#         return specs['optimization']
#
#     def translate_parameter(self, parameter_name: str):
#         translation_dict = {
#             "W_NET": "self.tango_instance.workflow.orchestrator.unit.surface.w_net",
#             "INLET_TEMP": "self.tango_instance.workflow.orchestrator.unit.surface.inlet_fluid.T"
#         }
#         return translation_dict.get(parameter_name)
#
#     def objective_func(self, x):
#         if not x:
#             # Return a placeholder list with the correct number of objectives
#             return [0.0] * len(self.target_parameters)
#
#         try:
#             for i, var_name in enumerate(self.optimization_specs.variables.keys()):
#                 self.set_parameter(var_name, x[i])
#
#             self.tango_instance.execute()
#
#             results = []
#             for target in self.target_parameters:
#                 try:
#                     result = eval(target)
#                     results.append(result)
#                 except Exception as e:
#                     print(f"Error evaluating target '{target}': {e}")
#                     results.append(float('-inf'))
#
#             if not results:
#                 raise ValueError("Objective function did not return any results.")
#             return results
#         except Exception as e:
#             print(f"Simulation failed with error: {e}")
#             return [float('-inf')] * len(self.target_parameters)
#
#     def set_parameter(self, var_name: str, value: float):
#         translation_dict = {
#             "MASS_FLOW_RATE": "self.tango_instance.specs['schedule']['mass_flow_rate']",
#             "THICKNESS": "self.tango_instance.specs['reservoir']['thickness']"
#         }
#         try:
#             exec(f"{translation_dict[var_name]} = {value}")
#         except Exception as e:
#             print(f"Failed to set parameter '{var_name}' to '{value}': {e}")
#
#     def constraint_lower_bound_func(self, x, constraint_name, lower_bound):
#         try:
#             parameter = eval(self.translate_parameter(constraint_name))
#             return lower_bound - parameter
#         except Exception as e:
#             print(f"Error evaluating lower bound constraint for '{constraint_name}': {e}")
#             return float('-inf')
#
#     def constraint_upper_bound_func(self, x, constraint_name, upper_bound):
#         try:
#             parameter = eval(self.translate_parameter(constraint_name))
#             return parameter - upper_bound
#         except Exception as e:
#             print(f"Error evaluating upper bound constraint for '{constraint_name}': {e}")
#             return float('inf')
#
#     def execute(self) -> None:
#         variable_ranges = {
#             f"x{i+1}": (specs['lower_bound'], specs['upper_bound'])
#             for i, (var_name, specs) in enumerate(self.optimization_specs.variables.items())
#         }
#         variable_types = {
#             f"x{i+1}": specs['type']
#             for i, (var_name, specs) in enumerate(self.optimization_specs.variables.items())
#         }
#
#         constraints = []
#         for constraint_name, constraint_specs in self.optimization_specs.constraints.items():
#             if 'lower_bound' in constraint_specs:
#                 constraints.append(partial(self.constraint_lower_bound_func, constraint_name=constraint_name, lower_bound=constraint_specs['lower_bound']))
#             if 'upper_bound' in constraint_specs:
#                 constraints.append(partial(self.constraint_upper_bound_func, constraint_name=constraint_name, upper_bound=constraint_specs['upper_bound']))
#
#         optimizer = MOOOptimizer(
#             self.objective_func,
#             constraints,
#             variable_ranges,
#             variable_types,
#             algorithm_name=self._method,
#             parallel_processing=self._parallel_processing,
#             optimization_specs=self.optimization_specs
#         )
#
#         start = time.time()
#
#         optimizer.optimize(n_gen=self._n_gen)
#
#         end = time.time()
#
#         print('Time taken:', end - start)
#
#         optimizer.print_results()
#         optimizer.plot_results()
#         # optimizer.plot_hypervolume_igd()  # Plot the metrics (Hypervolume and IGD)
#
#         if self._parallel_processing:
#             optimizer.close_pool()
#
# class MOOOptimizer:
#     def __init__(self, objective_func, constraints, variable_ranges, variable_types, algorithm_name='nsga2',
#                  parallel_processing=False, optimization_specs=None, sampling=None, crossover=None,
#                  mutation=None, eliminate_duplicates=None):
#
#         self.optimization_specs = optimization_specs
#         self.objective_func = objective_func
#         self.constraints = constraints
#         self.variable_ranges = variable_ranges
#         self.variable_types = variable_types
#         self.algorithm_name = algorithm_name
#         self.parallel_processing = parallel_processing
#         self.pop_size = self.optimization_specs.pop_size
#
#         if not np.isclose(np.sum(self.optimization_specs.weights), 1.0):
#             raise ValueError("The sum of the weights in optimization_specs.weights must be equal to 1.")
#
#         if self.parallel_processing:
#             self.n_processes = self.optimization_specs.n_processes
#             self.pool = multiprocessing.Pool(self.n_processes)
#             self.runner = StarmapParallelization(self.pool.starmap)
#         else:
#             self.pool = None
#             self.runner = None
#
#         self.problem = self.MyMOOProblem(objective_func, constraints, variable_ranges, variable_types, runner=self.runner)
#         # Set the algorithm parameters
#         self.sampling = FloatRandomSampling()
#         self.crossover = SBX(prob=self.optimization_specs.crossover_probability, eta=self.optimization_specs.distribution_index)
#         self.mutation = PM(eta=self.optimization_specs.polynomial_mutation)
#         self.eliminate_duplicates = True
#         self.algorithm = self.select_algorithm(algorithm_name)
#
#     def select_algorithm(self, algorithm_name):
#         if algorithm_name == 'nsga2':
#             return NSGA2(
#                 pop_size=self.pop_size,
#                 sampling=self.sampling,
#                 crossover=self.crossover,
#                 mutation=self.mutation,
#                 eliminate_duplicates=self.eliminate_duplicates
#             )
#         elif algorithm_name == 'nsga3':
#             ref_dirs = UniformReferenceDirectionFactory(self.problem.n_obj, n_points=self.pop_size).do()
#             return NSGA3(
#                 pop_size=self.pop_size,
#                 ref_dirs=ref_dirs,
#                 sampling=self.sampling,
#                 crossover=self.crossover,
#                 mutation=self.mutation,
#                 eliminate_duplicates=self.eliminate_duplicates
#             )
#         else:
#             raise ValueError(f"Algorithm {algorithm_name} not recognized. Available algorithms: nsga2, nsga3")
#
#     def optimize(self, n_gen=20):
#         try:
#             self.res = minimize(self.problem,
#                                 self.algorithm,
#                                 ('n_gen', n_gen),
#                                 verbose=True,
#                                 save_history=True)
#
#             if self.res.F is None:
#                 raise ValueError("Optimization did not produce any results.")
#
#             self.x_opt = self.res.X
#             self.f_opt = self.res.F
#
#             # Calculate ASF solution directly after optimization
#             if self.optimization_specs.final_selection == 'ASF':
#                 self.selected_asf_solution = self.f_opt[calculate_asf(self.f_opt)]
#             elif self.optimization_specs.final_selection == 'pseudo_weights':
#                 self.selected_asf_solution = self.f_opt[calculate_pseudo_weights(self.f_opt)]
#             else:
#                 self.selected_asf_solution = None
#
#             self._normalize_objectives()  # Normalize objectives after optimization
#
#             # Calculate and plot hypervolume and IGD
#             self.plot_hypervolume_igd()
#
#         except Exception as e:
#             print(f"Optimization failed with error: {e}")
#             self.x_opt = None
#             self.f_opt = None
#             self.selected_asf_solution = None
#
#     class MyMOOProblem(ElementwiseProblem):
#         def __init__(self, objective_func, constraints, variable_ranges, variable_types, runner=None):
#             self.objective_func = objective_func
#             self.constraints = constraints
#             self.variable_types = variable_types
#             n_var = len(variable_ranges)
#             xl = np.array([variable_ranges[var][0] for var in variable_ranges])
#             xu = np.array([variable_ranges[var][1] for var in variable_ranges])
#
#             if runner is not None:
#                 super().__init__(n_var=n_var,
#                                  n_obj=len(objective_func([])),
#                                  n_ieq_constr=len(constraints),
#                                  xl=xl,
#                                  xu=xu,
#                                  elementwise_runner=runner)
#             else:
#                 super().__init__(n_var=n_var,
#                                  n_obj=len(objective_func([])),
#                                  n_ieq_constr=len(constraints),
#                                  xl=xl,
#                                  xu=xu)
#
#         def _evaluate(self, x, out, *args, **kwargs):
#             for i, (var, vtype) in enumerate(self.variable_types.items()):
#                 if vtype == 'integer':
#                     x[i] = np.round(x[i])
#
#             out["F"] = self.objective_func(x)
#             out["G"] = np.array([constraint(x) for constraint in self.constraints])
#
#     def plot_hypervolume_igd(self):
#         ideal_point = self.f_opt.min(axis=0)
#         nadir_point = self.f_opt.max(axis=0)
#
#         hv = Hypervolume(ref_point=nadir_point + 1.0)  # Reference point should be slightly worse than nadir
#         igd = IGD(ideal_point)  # Use ideal point for IGD reference
#
#         hv_values = []
#         igd_values = []
#
#         for gen in self.res.history:
#             F = gen.opt.get("F")
#             hv_values.append(hv.do(F))
#             igd_values.append(igd.do(F))
#
#         generations = np.arange(len(self.res.history))
#
#         plt.figure(figsize=(14, 6))
#
#         plt.subplot(1, 2, 1)
#         plt.plot(generations, hv_values, '-o', label='Hypervolume')
#         plt.title('Hypervolume over Generations')
#         plt.xlabel('Generation')
#         plt.ylabel('Hypervolume')
#         plt.grid(True)
#
#         plt.subplot(1, 2, 2)
#         plt.plot(generations, igd_values, '-o', label='IGD', color='orange')
#         plt.title('IGD over Generations')
#         plt.xlabel('Generation')
#         plt.ylabel('IGD')
#         plt.grid(True)
#
#         plt.tight_layout()
#         plt.show()
#
#     def _normalize_objectives(self):
#         # Get max and min for each objective
#         self.f_max = np.max(self.f_opt, axis=0)
#         self.f_min = np.min(self.f_opt, axis=0)
#
#         # Normalize objectives based on target types
#         normalized_f_opt = np.zeros_like(self.f_opt)
#
#         for i in range(len(self.f_max)):
#             if self.optimization_specs.target_type[i] == 'maximize':
#                 normalized_f_opt[:, i] = (self.f_max[i] - self.f_opt[:, i]) / (self.f_max[i] - self.f_min[i])
#             else:  # 'maximize'
#                 normalized_f_opt[:, i] = (self.f_opt[:, i] - self.f_min[i]) / (self.f_max[i] - self.f_min[i])
#
#         self.normalized_f_opt = normalized_f_opt * self.optimization_specs.weights
#
#     def print_results(self):
#         if self.x_opt is None or self.f_opt is None:
#             print("No valid optimization results to display.")
#             return
#
#         print("Optimal Variables and Objectives on Pareto front:")
#         for i in range(len(self.f_opt)):
#             print(f"Solution {i + 1}:")
#             for j in range(len(self.x_opt[i])):
#                 print(f"x{j + 1} = {self.x_opt[i][j]}")
#             for k in range(len(self.f_opt[i])):
#                 print(f"Objective {k + 1} = {self.f_opt[i][k]}")
#
#         if self.optimization_specs.final_selection == 'ASF':
#             self.solution = self._select_asf_solution()
#             print("\nSelected ASF Solution:")
#             print(self.solution)
#         elif self.optimization_specs.final_selection == 'pseudo_weights':
#             self.solution = self._select_pseudo_weights_solution()
#             print("\nSelected Pseudo-Weights Solution:")
#             print(self.solution)
#
#     def plot_results(self):
#         if self.f_opt is None:
#             print("No valid results to plot.")
#             return
#
#         # Check if ASF solution exists
#         selected_solution = self.solution[1] if self.solution is not None else None
#
#         # Handle 2D plot for two objectives
#         if len(self.f_opt[0]) == 2:
#             plt.scatter(self.f_opt[:, 0], self.f_opt[:, 1], label='Pareto Front')
#
#             if selected_solution is not None:
#                 plt.scatter(selected_solution[0], selected_solution[1],
#                             color='red', marker='x', s=100, label='Selected Solution')
#
#             plt.xlabel('Objective 1')
#             plt.ylabel('Objective 2')
#             plt.title('Pareto Front')
#             plt.legend()
#             plt.show()
#
#         # Handle 3D plot for three objectives
#         elif len(self.f_opt[0]) == 3:
#             from mpl_toolkits.mplot3d import Axes3D  # Importing here to avoid issues if not needed
#
#             fig = plt.figure()
#             ax = fig.add_subplot(111, projection='3d')
#
#             # Plot the Pareto front in 3D
#             ax.scatter(self.f_opt[:, 0], self.f_opt[:, 1], self.f_opt[:, 2], label='Pareto Front')
#
#             if selected_solution is not None:
#                 ax.scatter(selected_solution[0], selected_solution[1], selected_solution[2],
#                            color='red', marker='x', s=100, label='Selected Solution')
#
#             # Set labels for each axis
#             ax.set_xlabel('Objective 1')
#             ax.set_ylabel('Objective 2')
#             ax.set_zlabel('Objective 3')
#             ax.set_title('Pareto Front')
#             plt.legend()
#             plt.show()
#
#         else:
#             print("Plotting is only supported for 2 or 3 objectives.")
#
#     def _select_asf_solution(self):
#         index = calculate_asf(self.normalized_f_opt)
#         return self.x_opt[index], self.f_opt[index]
#
#     def _select_pseudo_weights_solution(self):
#         index = calculate_pseudo_weights(self.normalized_f_opt)
#         return self.x_opt[index], self.f_opt[index]
#
#     def close_pool(self):
#         if self.pool:
#             self.pool.close()
#
# # Manual ASF Calculation
# def calculate_asf(normalized_objectives):
#     asf_values = np.max(normalized_objectives, axis=1)
#     return np.argmin(asf_values)
#
# # Manual Pseudo-Weighting Calculation
# def calculate_pseudo_weights(normalized_objectives):
#     weighted_sum = np.sum(normalized_objectives, axis=1)
#     return np.argmin(weighted_sum)











































import numpy as np
from pymoo.core.problem import ElementwiseProblem
from pymoo.algorithms.soo.nonconvex.de import DE
from pymoo.algorithms.soo.nonconvex.ga import GA
from pymoo.algorithms.soo.nonconvex.nelder import NelderMead
from pymoo.algorithms.soo.nonconvex.pso import PSO
from pymoo.algorithms.soo.nonconvex.cmaes import CMAES
from pymoo.algorithms.soo.nonconvex.pattern import PatternSearch
from pymoo.algorithms.soo.nonconvex.brkga import BRKGA
from pymoo.algorithms.soo.nonconvex.es import ES
from pymoo.algorithms.soo.nonconvex.sres import SRES
from pymoo.algorithms.soo.nonconvex.isres import ISRES
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.nsga3 import NSGA3
from pymoo.optimize import minimize
from pymoo.core.problem import StarmapParallelization
from pymoo.indicators.hv import Hypervolume
from pymoo.indicators.igd import IGD
from pymoo.operators.sampling.rnd import FloatRandomSampling
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.util.reference_direction import UniformReferenceDirectionFactory
import matplotlib.pyplot as plt
import multiprocessing
import time
from functools import partial
from tango.units.dataclasses import OptimizationSpecs


class Optimizer:
    def __init__(self, tango_object, specs):
        self.tango_instance = tango_object
        self.optimization_specs = OptimizationSpecs.from_dict(self._process_specs(specs))
        self.target_parameters = [self.translate_parameter(target) for target in self.optimization_specs.targets]
        self._method = self.optimization_specs.method
        self._n_gen = self.optimization_specs.n_generation
        self._parallel_processing = self.optimization_specs.parallel_processing
        self._pop_size = self.optimization_specs.pop_size

    def _process_specs(self, specs) -> dict:
        return specs['optimization']

    def translate_parameter(self, parameter_name: str):
        translation_dict = {
            "W_NET": "self.tango_instance.workflow.orchestrator.unit.surface.w_net",
            "INLET_TEMP": "self.tango_instance.workflow.orchestrator.unit.surface.inlet_fluid.T"
        }
        return translation_dict.get(parameter_name)

    # def objective_func(self, x):
    #     try:
    #         for i, var_name in enumerate(self.optimization_specs.variables.keys()):
    #             self.set_parameter(var_name, x[i])
    #
    #         self.tango_instance.execute()
    #
    #         results = []
    #         for i, target in enumerate(self.target_parameters):
    #             result = eval(target)
    #             if self.optimization_specs.target_type[i] == 'maximize':
    #                 results.append(result)
    #             else:
    #                 results.append(-result)
    #
    #         return results if len(results) > 1 else results[0]
    #
    #     except Exception as e:
    #         print(f"Simulation failed with error: {e}")
    #         return [float('-inf')] * len(self.target_parameters) if len(self.target_parameters) > 1 else float('-inf')


    def objective_func(self, x):
        try:
            # Set the parameters based on the input 'x'
            for i, var_name in enumerate(self.optimization_specs.variables.keys()):
                self.set_parameter(var_name, x[i])

            # Execute the tango_instance to run the simulation or process
            self.tango_instance.execute()

            # Prepare the results list
            results = []

            # Iterate over the targets and process results
            for i, target in enumerate(self.target_parameters):
                result = eval(target)

                # Handle the inversion based on target type
                if self.optimization_specs.target_type[i] == 'maximize':
                    # If maximizing, in multi-objective, we negate maximization targets
                    # In single-objective, we return maximized values directly
                    if len(self.target_parameters) > 1:
                        results.append(-result)  # Negate for multi-objective maximization
                    else:
                        results.append(result)   # Keep as is for single-objective maximization
                else:
                    # If minimizing, in multi-objective, we keep the minimization targets
                    # In single-objective, we negate minimization targets to maximize
                    if len(self.target_parameters) > 1:
                        results.append(result)  # Keep as is for multi-objective minimization
                    else:
                        results.append(-result)  # Negate for single-objective minimization

            # Return results: single value for single-objective, list for multi-objective
            return results if len(results) > 1 else results[0]

        except Exception as e:
            print(f"Simulation failed with error: {e}")
            # Return invalid values for failed executions
            return [float('-inf')] * len(self.target_parameters) if len(self.target_parameters) > 1 else float('-inf')

    def set_parameter(self, var_name: str, value: float):
        translation_dict = {
            "MASS_FLOW_RATE": "self.tango_instance.specs['schedule']['mass_flow_rate']",
            "THICKNESS": "self.tango_instance.specs['reservoir']['thickness']"
        }
        exec(f"{translation_dict[var_name]} = {value}")

    def constraint_lower_bound_func(self, x, constraint_name, lower_bound):
        try:
            parameter = eval(self.translate_parameter(constraint_name))
            return lower_bound - parameter
        except Exception as e:
            print(f"Error evaluating lower bound constraint for '{constraint_name}': {e}")
            return float('-inf')

    def constraint_upper_bound_func(self, x, constraint_name, upper_bound):
        try:
            parameter = eval(self.translate_parameter(constraint_name))
            return parameter - upper_bound
        except Exception as e:
            print(f"Error evaluating upper bound constraint for '{constraint_name}': {e}")
            return float('inf')

    def execute(self):
        variable_ranges = {
            f"x{i+1}": (specs['lower_bound'], specs['upper_bound'])
            for i, (var_name, specs) in enumerate(self.optimization_specs.variables.items())
        }
        variable_types = {
            f"x{i+1}": specs['type']
            for i, (var_name, specs) in enumerate(self.optimization_specs.variables.items())
        }

        constraints = []
        for constraint_name, constraint_specs in self.optimization_specs.constraints.items():
            if 'lower_bound' in constraint_specs:
                constraints.append(partial(self.constraint_lower_bound_func, constraint_name=constraint_name, lower_bound=constraint_specs['lower_bound']))
            if 'upper_bound' in constraint_specs:
                constraints.append(partial(self.constraint_upper_bound_func, constraint_name=constraint_name, upper_bound=constraint_specs['upper_bound']))

        if len(self.target_parameters) > 1:
            optimizer = MOOOptimizer(self.objective_func, constraints, variable_ranges, variable_types, self._method, self._parallel_processing, self.optimization_specs)
        else:
            optimizer = SOOOptimizer(self.objective_func, constraints, variable_ranges, variable_types, self._method, self._parallel_processing, self.optimization_specs)

        start = time.time()
        optimizer.optimize(n_gen=self._n_gen)
        end = time.time()

        print('Time taken:', end - start)

        optimizer.print_results()
        optimizer.plot_results()

        if len(self.target_parameters) > 1:
            optimizer.plot_hypervolume_igd()

        if self._parallel_processing:
            optimizer.close_pool()


class BaseOptimizer:
    def __init__(self, objective_func, constraints, variable_ranges, variable_types, algorithm_name, parallel_processing, optimization_specs):
        self.optimization_specs = optimization_specs
        self.objective_func = objective_func
        self.constraints = constraints
        self.variable_ranges = variable_ranges
        self.variable_types = variable_types
        self.algorithm_name = algorithm_name
        self.parallel_processing = parallel_processing
        self.pop_size = self.optimization_specs.pop_size

        if self.parallel_processing:
            self.n_processes = self.optimization_specs.n_processes
            self.pool = multiprocessing.Pool(self.n_processes)
            self.runner = StarmapParallelization(self.pool.starmap)
        else:
            self.pool = None
            self.runner = None

        self.problem = self.define_problem()

    def define_problem(self):
        raise NotImplementedError("Subclasses should implement this method.")

    def optimize(self, n_gen):
        raise NotImplementedError("Subclasses should implement this method.")

    def print_results(self):
        raise NotImplementedError("Subclasses should implement this method.")

    def plot_results(self):
        raise NotImplementedError("Subclasses should implement this method.")

    def close_pool(self):
        if self.pool:
            self.pool.close()


class SOOOptimizer(BaseOptimizer):
    class MySOOProblem(ElementwiseProblem):
        def __init__(self, objective_func, constraints, variable_ranges, variable_types, runner=None):
            self.objective_func = objective_func
            self.constraints = constraints
            self.variable_types = variable_types
            n_var = len(variable_ranges)
            xl = np.array([variable_ranges[var][0] for var in variable_ranges])
            xu = np.array([variable_ranges[var][1] for var in variable_ranges])

            if runner:
                super().__init__(n_var=n_var, n_obj=1, n_ieq_constr=len(constraints), xl=xl, xu=xu, elementwise_runner=runner)
            else:
                super().__init__(n_var=n_var, n_obj=1, n_ieq_constr=len(constraints), xl=xl, xu=xu)

        def _evaluate(self, x, out, *args, **kwargs):
            for i, (var, vtype) in enumerate(self.variable_types.items()):
                if vtype == 'integer':
                    x[i] = np.round(x[i])

            out["F"] = -1 * self.objective_func(x)  # Negate to convert maximization to minimization
            out["G"] = np.array([constraint(x) for constraint in self.constraints])

    def define_problem(self):
        return self.MySOOProblem(self.objective_func, self.constraints, self.variable_ranges, self.variable_types, runner=self.runner)

    def optimize(self, n_gen):
        self.x_values = []
        self.f_min_values = []

        def callback(algorithm):
            feas_inds = [ind for ind in algorithm.pop if np.all(ind.get("G") <= 0)]
            if feas_inds:
                self.f_min_values.append(min(ind.get("F") for ind in feas_inds))
                best_ind = feas_inds[np.argmin([ind.get("F") for ind in feas_inds])]
                self.x_values.append([np.round(best_ind.X[i]) if self.variable_types[f'x{i+1}'] == 'integer' else best_ind.X[i] for i in range(len(best_ind.X))])

        self.algorithm = self.select_algorithm()
        res = minimize(self.problem, self.algorithm, ('n_gen', n_gen), verbose=True, callback=callback)

        self.x_opt = res.X
        self.f_opt = -res.F[0]

    def select_algorithm(self):
        algorithms = {
            'DE': DE(pop_size=self.pop_size),
            'GA': GA(pop_size=self.pop_size),
            'NelderMead': NelderMead(),
            'PSO': PSO(pop_size=self.pop_size),
            'CMAES': CMAES(pop_size=self.pop_size),
            'PatternSearch': PatternSearch(),
            'BRKGA': BRKGA(),
            'ES': ES(),
            'SRES': SRES(),
            'ISRES': ISRES()
        }
        return algorithms.get(self.algorithm_name, DE(pop_size=self.pop_size))

    def print_results(self):
        print("Optimal Variables:", self.x_opt)
        print("Maximum Value:", self.f_opt)

        for gen in range(len(self.f_min_values)):
            x_vals_str = ', '.join([f'x{i+1} = {self.x_values[gen][i]}' for i in range(len(self.x_values[gen]))])
            print(f"Generation {gen + 1}: {x_vals_str}, f_min = {self.f_min_values[gen]}")

    def plot_results(self):
        generations = range(1, len(self.f_min_values) + 1)

        plt.figure(figsize=(12, 6))
        plt.subplot(1, 2, 1)
        for i in range(len(self.variable_ranges)):
            plt.plot(generations, [x[i] for x in self.x_values], label=f'x{i+1}')
        plt.xlabel('Generation')
        plt.ylabel('Variable Value')
        plt.title('Variable values over Generations')
        plt.legend()

        plt.subplot(1, 2, 2)

        f_min_values_array = np.array(self.f_min_values)

        print('type', self.optimization_specs.target_type[0])

        if (self.optimization_specs.target_type[0] == 'maximize'):
            plt.plot(generations, -f_min_values_array)
        else:
            plt.plot(generations, f_min_values_array)

        plt.xlabel('Generation')
        plt.ylabel('Function Value')
        plt.title('function over Generations')
        plt.legend()

        plt.tight_layout()
        plt.show()

class MOOOptimizer(BaseOptimizer):
    class MyMOOProblem(ElementwiseProblem):
        def __init__(self, objective_func, constraints, variable_ranges, variable_types, runner=None):
            self.objective_func = objective_func
            self.constraints = constraints
            self.variable_types = variable_types
            n_var = len(variable_ranges)
            xl = np.array([variable_ranges[var][0] for var in variable_ranges])
            xu = np.array([variable_ranges[var][1] for var in variable_ranges])

            super().__init__(n_var=n_var,
                             n_obj=len(objective_func([])),
                             n_ieq_constr=len(constraints),
                             xl=xl,
                             xu=xu,
                             elementwise_runner=runner if runner else None)

        def _evaluate(self, x, out, *args, **kwargs):
            for i, (var, vtype) in enumerate(self.variable_types.items()):
                if vtype == 'integer':
                    x[i] = np.round(x[i])

            out["F"] = self.objective_func(x)
            out["G"] = np.array([constraint(x) for constraint in self.constraints])

    def define_problem(self):
        return self.MyMOOProblem(self.objective_func, self.constraints, self.variable_ranges, self.variable_types, runner=self.runner)

    def optimize(self, n_gen):
        self.algorithm = self.select_algorithm()
        self.res = minimize(self.problem, self.algorithm, ('n_gen', n_gen), verbose=True, save_history=True)

        self.x_opt = self.res.X
        self.f_opt = self.res.F

        # Ensure objectives are normalized before selecting the final solution
        self._normalize_objectives()

        if self.optimization_specs.final_selection == 'ASF':
            self.solution = self._select_asf_solution()
        elif self.optimization_specs.final_selection == 'pseudo_weights':
            self.solution = self._select_pseudo_weights_solution()

    def select_algorithm(self):
        if self.algorithm_name == 'nsga2':
            return NSGA2(pop_size=self.pop_size, sampling=FloatRandomSampling(), crossover=SBX(prob=self.optimization_specs.crossover_probability, eta=self.optimization_specs.distribution_index), mutation=PM(eta=self.optimization_specs.polynomial_mutation), eliminate_duplicates=True)
        elif self.algorithm_name == 'nsga3':
            ref_dirs = UniformReferenceDirectionFactory(self.problem.n_obj, n_points=self.pop_size).do()
            return NSGA3(pop_size=self.pop_size, ref_dirs=ref_dirs, sampling=FloatRandomSampling(), crossover=SBX(prob=self.optimization_specs.crossover_probability, eta=self.optimization_specs.distribution_index), mutation=PM(eta=self.optimization_specs.polynomial_mutation), eliminate_duplicates=True)
        else:
            raise ValueError(f"Algorithm {self.algorithm_name} not recognized. Available algorithms: nsga2, nsga3")

    def _normalize_objectives(self):
        self.f_max = np.max(self.f_opt, axis=0)
        self.f_min = np.min(self.f_opt, axis=0)
        normalized_f_opt = np.zeros_like(self.f_opt)

        for i in range(len(self.f_max)):
            normalized_f_opt[:, i] = (self.f_opt[:, i] - self.f_min[i]) / (self.f_max[i] - self.f_min[i])
            # if self.optimization_specs.target_type[i] == 'maximize':
            #     normalized_f_opt[:, i] = (self.f_max[i] - self.f_opt[:, i]) / (self.f_max[i] - self.f_min[i])
            # else:
            #     normalized_f_opt[:, i] = (self.f_opt[:, i] - self.f_min[i]) / (self.f_max[i] - self.f_min[i])

        self.normalized_f_opt = normalized_f_opt * self.optimization_specs.weights

    def _select_asf_solution(self):
        index = calculate_asf(self.normalized_f_opt)
        return self.x_opt[index], self.f_opt[index]

    def _select_pseudo_weights_solution(self):
        index = calculate_pseudo_weights(self.normalized_f_opt)
        return self.x_opt[index], self.f_opt[index]

    def print_results(self):
        if self.x_opt is None or self.f_opt is None:
            print("No valid optimization results to display.")
            return

        print("Optimal Variables and Objectives on Pareto front:")
        for i in range(len(self.f_opt)):
            print(f"Solution {i + 1}:")
            for j in range(len(self.x_opt[i])):
                print(f"x{j + 1} = {self.x_opt[i][j]}")
            for k in range(len(self.f_opt[i])):
                print(f"Objective {k + 1} = {self.f_opt[i][k]}")

        if self.optimization_specs.final_selection == 'ASF':
            print("\nSelected ASF Solution:")
            print(self.solution)
        elif self.optimization_specs.final_selection == 'pseudo_weights':
            print("\nSelected Pseudo-Weights Solution:")
            print(self.solution)

    # def plot_results(self):
    #     if self.f_opt is None:
    #         print("No valid results to plot.")
    #         return
    #
    #     selected_solution = self.solution[1] if self.solution is not None else None
    #
    #     if len(self.f_opt[0]) == 2:
    #         plt.scatter(self.f_opt[:, 0], self.f_opt[:, 1], label='Pareto Front')
    #         if selected_solution is not None:
    #             plt.scatter(selected_solution[0], selected_solution[1], color='red', marker='x', s=100, label='Selected Solution')
    #         plt.xlabel('Objective 1')
    #         plt.ylabel('Objective 2')
    #         plt.title('Pareto Front')
    #         plt.legend()
    #         plt.show()
    #
    #     elif len(self.f_opt[0]) == 3:
    #         fig = plt.figure()
    #         ax = fig.add_subplot(111, projection='3d')
    #         ax.scatter(self.f_opt[:, 0], self.f_opt[:, 1], self.f_opt[:, 2], label='Pareto Front')
    #         if selected_solution is not None:
    #             ax.scatter(selected_solution[0], selected_solution[1], selected_solution[2], color='red', marker='x', s=100, label='Selected Solution')
    #         ax.set_xlabel('Objective 1')
    #         ax.set_ylabel('Objective 2')
    #         ax.set_zlabel('Objective 3')
    #         ax.set_title('Pareto Front')
    #         plt.legend()
    #         plt.show()
    #     else:
    #         print("Plotting is only supported for 2 or 3 objectives.")

    def plot_results(self):
        if self.f_opt is None:
            print("No valid results to plot.")
            return

        # Revert the negation to get the original objective values
        original_f_opt = np.copy(self.f_opt)

        for i, target_type in enumerate(self.optimization_specs.target_type):
            if target_type == 'maximize':
                # If target was minimized, it was negated, so revert to the original value
                original_f_opt[:, i] = -self.f_opt[:, i]

        selected_solution = self.solution[1] if self.solution is not None else None

        if len(original_f_opt[0]) == 2:
            plt.scatter(original_f_opt[:, 0], original_f_opt[:, 1], label='Pareto Front')
            if selected_solution is not None:
                # Ensure that selected solution's objective values are also shown in their original form
                original_selected_solution = np.copy(selected_solution)
                for i, target_type in enumerate(self.optimization_specs.target_type):
                    if target_type == 'maximize':
                        original_selected_solution[i] = -selected_solution[i]
                plt.scatter(original_selected_solution[0], original_selected_solution[1], color='red', marker='x', s=100, label='Selected Solution')
            plt.xlabel('Objective 1')
            plt.ylabel('Objective 2')
            plt.title('Pareto Front with Original Objective Values')
            plt.legend()
            plt.show()

        elif len(original_f_opt[0]) == 3:
            fig = plt.figure()
            ax = fig.add_subplot(111, projection='3d')
            ax.scatter(original_f_opt[:, 0], original_f_opt[:, 1], original_f_opt[:, 2], label='Pareto Front')
            if selected_solution is not None:
                original_selected_solution = np.copy(selected_solution)
                for i, target_type in enumerate(self.optimization_specs.target_type):
                    if target_type == 'minimize':
                        original_selected_solution[i] = -selected_solution[i]
                ax.scatter(original_selected_solution[0], original_selected_solution[1], original_selected_solution[2], color='red', marker='x', s=100, label='Selected Solution')
            ax.set_xlabel('Objective 1')
            ax.set_ylabel('Objective 2')
            ax.set_zlabel('Objective 3')
            ax.set_title('Pareto Front with Original Objective Values')
            plt.legend()
            plt.show()
        else:
            print("Plotting is only supported for 2 or 3 objectives.")

    def plot_hypervolume_igd(self):
        ideal_point = self.f_opt.min(axis=0)
        nadir_point = self.f_opt.max(axis=0)

        hv = Hypervolume(ref_point=nadir_point + 1.0)
        igd = IGD(ideal_point)

        hv_values = []
        igd_values = []

        for gen in self.res.history:
            F = gen.opt.get("F")
            hv_values.append(hv.do(F))
            igd_values.append(igd.do(F))

        generations = np.arange(len(self.res.history))

        plt.figure(figsize=(14, 6))
        plt.subplot(1, 2, 1)
        plt.plot(generations, hv_values, '-o', label='Hypervolume')
        plt.title('Hypervolume over Generations')
        plt.xlabel('Generation')
        plt.ylabel('Hypervolume')
        plt.grid(True)

        plt.subplot(1, 2, 2)
        plt.plot(generations, igd_values, '-o', label='IGD', color='orange')
        plt.title('IGD over Generations')
        plt.xlabel('Generation')
        plt.ylabel('IGD')
        plt.grid(True)

        plt.tight_layout()
        plt.show()


# Utility Functions for Manual ASF and Pseudo-Weights Calculation
def calculate_asf(normalized_objectives):
    asf_values = np.max(normalized_objectives, axis=1)
    return np.argmin(asf_values)

def calculate_pseudo_weights(normalized_objectives):
    weighted_sum = np.sum(normalized_objectives, axis=1)
    return np.argmin(weighted_sum)
