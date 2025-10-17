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
from tango.parameter_mappings import get_target_translation, VARIABLE_PARAMETER_MAPPING
import os

class Optimizer:
    """
    A class to handle the optimization process for a TANGO-based system.

    This class sets up and executes an optimization process using specifications
    provided in the `specs` argument. It supports various optimization methods,
    parallel processing, and parameter translation.

    Attributes
    ----------
    tango_instance : object
        An instance of the TANGO object that provides access to the simulation or process.
    optimization_specs : OptimizationSpecs
        The specifications for the optimization process, including variables, targets, and constraints.
    target_parameters : list
        Translated parameter names for the optimization targets.
    _method : str
        The optimization method to use (e.g., "GA", "DE").
    _n_gen : int
        The number of generations to run for the optimization.
    _parallel_processing : bool
        Whether parallel processing is enabled.
    _pop_size : int
        The population size for the optimization algorithm.
    """
    def __init__(self, tango_object, specs):
        self.tango_instance = tango_object
        self.optimization_specs = OptimizationSpecs.from_dict(self._process_specs(specs))
        self.target_parameters = [self.translate_parameter(target) for target in self.optimization_specs.targets]
        self._method = self.optimization_specs.method
        self._n_gen = self.optimization_specs.n_generation
        self._parallel_processing = self.optimization_specs.parallel_processing
        self._pop_size = self.optimization_specs.pop_size
        self.variable_names = list(self.optimization_specs.variables.keys())
        self.objective_names = self.optimization_specs.targets

    def _process_specs(self, specs) -> dict:
        """
        Processes the optimization specifications from the input dictionary.

        Parameters
        ----------
        specs : dict
            A dictionary containing the optimization specifications.

        Returns
        -------
        dict
            The processed optimization specifications.
        """
        return specs['optimization']

    def translate_parameter(self, parameter_name: str):
        """
        Translates a parameter name to its corresponding TANGO parameter path.

        Parameters
        ----------
        parameter_name : str
            The name of the parameter to be translated.

        Returns
        -------
        str
            The translated TANGO parameter path.
        """
        return get_target_translation(parameter_name)

    def objective_func(self, x):
        """
        Evaluates the objective function for optimization.

        Parameters
        ----------
        x : list
            Input values for the optimization variables.

        Returns
        -------
        float or list of float
            The result of the objective function. A single float for one target,
            or a list of floats for multiple targets.

        Notes
        -----
        - Adjusts input variables, executes computations, and evaluates targets.
        - Maximization targets are inverted for minimization-based optimizers.
        - Returns `float('inf')` or a list of `float('inf')` if an error occurs.

        """
        try:
            for i, var_name in enumerate(self.optimization_specs.variables.keys()):
                self.set_parameter(var_name, x[i])

            self.tango_instance.execute()

            results = []

            for i, target in enumerate(self.target_parameters):
                result = eval(target)

                if self.optimization_specs.target_type[i] == 'maximize':
                    results.append(-result if len(self.target_parameters) > 1 else result)
                else:
                    results.append(result if len(self.target_parameters) > 1 else -result)

            return results if len(results) > 1 else results[0]

        except Exception as e:
            print(f"Error in objective function: {e}")
            return float('inf') if len(self.target_parameters) == 1 else [float('inf')] * len(self.target_parameters)

    def get_dynamic_power_plant_translations(self, specs):
        """
        Dynamically creates translation mappings for power plant components if available.

        Parameters
        ----------
        specs : dict
            The full specs dictionary containing the power_plant_graph.

        Returns
        -------
        dict
            A dictionary with dynamic mappings for power plant components.
            Example: {"pump2_efficiency": "self.tango_instance.specs['pump2']['efficiency']"}
            Returns an empty dict if power_plant_graph is not present.
        """
        dynamic_mapping = {}

        power_plant_nodes = specs.get('power_plant_graph', {}).get('nodes', {})

        if not power_plant_nodes:
            return dynamic_mapping

        for component_name, component_details in power_plant_nodes.items():
            component_specs = specs.get(component_name, {})
            for param, value in component_specs.items():
                mapping_key = f"powerplant_{component_name}_{param}"
                mapping_value = f"self.tango_instance.specs['{component_name}']['{param}']"
                dynamic_mapping[mapping_key] = mapping_value

        return dynamic_mapping

    def get_variable_translation(self, var_name: str, specs=None) -> str:
        """
        Get the translation for a variable parameter, with dynamic handling for power plant components.

        Parameters
        ----------
        var_name : str
            The name of the variable to translate.
        specs : dict, optional
            The specs dictionary to check for dynamic mappings.

        Returns
        -------
        str
            The corresponding TANGO variable path.

        Raises
        ------
        KeyError
            If the variable name is not found in either static or dynamic mapping.
        """
        if var_name in VARIABLE_PARAMETER_MAPPING:
            return VARIABLE_PARAMETER_MAPPING[var_name]

        if specs is not None:
            dynamic_mapping = self.get_dynamic_power_plant_translations(specs)
            if var_name in dynamic_mapping:
                return dynamic_mapping[var_name]

        available_static = list(VARIABLE_PARAMETER_MAPPING.keys())
        available_dynamic = list(dynamic_mapping.keys()) if specs else []
        raise KeyError(
            f"Variable parameter '{var_name}' not found.\n"
            f"Available static mappings: {available_static}\n"
            f"Available dynamic mappings: {available_dynamic}"
        )

    def set_parameter(self, var_name: str, value: float):
        """
        Sets a parameter in the TANGO instance based on the provided variable name and value.

        Parameters
        ----------
        var_name : str
            The name of the variable to set.
        value : float
            The value to assign to the variable.
        """
        param_path = self.get_variable_translation(var_name, self.tango_instance.specs)
        exec(f"{param_path} = {value}")

    def constraint_lower_bound_func(self, x, constraint_name, lower_bound):
        """
        Evaluates the lower bound constraint for a given parameter.

        Parameters
        ----------
        x : list or ndarray
            A list of variable values to evaluate the constraint.
        constraint_name : str
            The name of the parameter to apply the constraint.
        lower_bound : float
            The lower bound value for the constraint.

        Returns
        -------
        float
            The constraint evaluation result. A positive value means the constraint is satisfied.
        """
        try:
            parameter = eval(self.translate_parameter(constraint_name))
            return lower_bound - parameter
        except Exception as e:
            print(f"Error evaluating lower bound constraint for '{constraint_name}': {e}")
            return float('-inf')

    def constraint_upper_bound_func(self, x, constraint_name, upper_bound):
        """
        Evaluates the upper bound constraint for a given parameter.

        Parameters
        ----------
        x : list or ndarray
            A list of variable values to evaluate the constraint.
        constraint_name : str
            The name of the parameter to apply the constraint.
        upper_bound : float
            The upper bound value for the constraint.

        Returns
        -------
        float
            The constraint evaluation result. A positive value means the constraint is satisfied.
        """
        try:
            parameter = eval(self.translate_parameter(constraint_name))
            return parameter - upper_bound
        except Exception as e:
            print(f"Error evaluating upper bound constraint for '{constraint_name}': {e}")
            return float('inf')

    def execute(self):
        """
        Executes the optimization process.

        This method prepares variable ranges, constraints, and selects the appropriate optimizer
        (single-objective or multi-objective). It runs the optimization process for the specified
        number of generations, outputs the results, and generates relevant plots.

        Steps:
        - Prepare variable ranges and types.
        - Construct constraints from the optimization specifications.
        - Choose an optimizer based on the number of objectives.
        - Run the optimization and measure execution time.
        - Output results and generate plots.

        Attributes
        ----------
        variable_ranges : dict
            Ranges (lower and upper bounds) for each optimization variable.
        variable_types : dict
            Types of the variables (e.g., "integer", "float").
        constraints : list
            List of constraints (lower and upper bounds) for the variables.
        optimizer : SOOOptimizer or MOOOptimizer
            The selected optimizer for single-objective or multi-objective optimization.

        Plots
        -----
        - Variable values and function values across generations.
        - Hypervolume and IGD (for multi-objective optimization).

        Example
        -------
        >>> optimizer = Optimizer(tango_instance, optimization_specs)
        >>> optimizer.execute()
        """
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
            optimizer = MOOOptimizer(
                self.objective_func,
                constraints,
                variable_ranges,
                variable_types,
                self._method,
                self._parallel_processing,
                self.optimization_specs,
                self.variable_names,
                self.objective_names
            )
        else:
            optimizer = SOOOptimizer(
                self.objective_func,
                constraints,
                variable_ranges,
                variable_types,
                self._method,
                self._parallel_processing,
                self.optimization_specs,
                self.variable_names,
                self.objective_names
            )

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
    """
    A base class for optimization algorithms.

    This class provides the foundational structure for single-objective (SOO) and
    multi-objective (MOO) optimizers. It manages variable ranges, constraints,
    optimization specifications, and parallel processing.

    Attributes
    ----------
    optimization_specs : object
        The specifications for the optimization process (variables, constraints, etc.).
    objective_func : callable
        The objective function to optimize.
    constraints : list
        A list of constraint functions for the optimization problem.
    variable_ranges : dict
        Ranges (lower and upper bounds) for each optimization variable.
    variable_types : dict
        Types of the variables (e.g., "integer", "float").
    algorithm_name : str
        The name of the optimization algorithm to use.
    parallel_processing : bool
        Whether parallel processing is enabled.
    pop_size : int
        Population size for the optimization algorithm.
    n_processes : int
        Number of processes for parallel execution (if enabled).
    pool : multiprocessing.Pool or None
        The multiprocessing pool for parallel execution.
    runner : callable
        A function to run the optimization (either parallel or sequential).
    problem : object
        The optimization problem, defined by subclasses.

    """

    def __init__(self, objective_func, constraints, variable_ranges, variable_types, algorithm_name, parallel_processing, optimization_specs, variable_names, objective_names):
        """
        Initializes the BaseOptimizer.

        Parameters
        ----------
        objective_func : callable
            The objective function to optimize.
        constraints : list
            A list of constraint functions.
        variable_ranges : dict
            Ranges (lower and upper bounds) for each optimization variable.
        variable_types : dict
            Types of the variables (e.g., "integer", "float").
        algorithm_name : str
            The name of the optimization algorithm to use.
        parallel_processing : bool
            Whether parallel processing is enabled.
        optimization_specs : object
            The specifications for the optimization process (variables, constraints, etc.).
        """
        self.optimization_specs = optimization_specs
        self.objective_func = objective_func
        self.constraints = constraints
        self.variable_ranges = variable_ranges
        self.variable_types = variable_types
        self.algorithm_name = algorithm_name
        self.parallel_processing = parallel_processing
        self.pop_size = self.optimization_specs.pop_size
        self.plot_name = self.optimization_specs.plot_name
        self.variable_names = variable_names
        self.objective_names = objective_names

        if self.parallel_processing:
            self.n_processes = self.optimization_specs.n_processes
            self.pool = multiprocessing.Pool(self.n_processes)
            self.runner = StarmapParallelization(self.pool.starmap)
        else:
            self.pool = None
            self.runner = lambda func, X: [func(x) for x in X]

        self.problem = self.define_problem()

    def define_problem(self):
        """
        Abstract method to define the optimization problem.

        Must be implemented by subclasses.

        Raises
        ------
        NotImplementedError
            If the method is not implemented in the subclass.
        """
        raise NotImplementedError("Subclasses should implement this method.")

    def optimize(self, n_gen):
        """
        Abstract method to execute the optimization process.

        Must be implemented by subclasses.

        Parameters
        ----------
        n_gen : int
            The number of generations for the optimization.

        Raises
        ------
        NotImplementedError
            If the method is not implemented in the subclass.
        """
        raise NotImplementedError("Subclasses should implement this method.")

    def print_results(self):
        """
        Abstract method to print the results.

        Must be implemented by subclasses.

        Raises
        ------
        NotImplementedError
            If the method is not implemented in the subclass.
        """
        raise NotImplementedError("Subclasses should implement this method.")

    def plot_results(self):
        """
        Abstract method to plot the optimization results.

        Must be implemented by subclasses.

        Raises
        ------
        NotImplementedError
            If the method is not implemented in the subclass.
        """
        raise NotImplementedError("Subclasses should implement this method.")

    def close_pool(self):
        """
        Closes the multiprocessing pool if parallel processing is enabled.

        Ensures that all resources are released after optimization.

        Raises
        ------
        Exception
            If an error occurs while closing the pool.
        """
        if self.pool:
            self.pool.close()


class SOOOptimizer(BaseOptimizer):
    """
    Single-Objective Optimization (SOO) class.

    This class handles single-objective optimization by extending the `BaseOptimizer`.
    It defines the optimization problem, executes the optimization, and provides
    methods to print and plot the results.

    Inner Class
    -----------
    MySOOProblem : ElementwiseProblem
        A custom single-objective optimization problem definition for Pymoo.
        Handles variable ranges, constraints, and the evaluation of the objective function.

    Attributes
    ----------
    x_opt : list
        The optimal variable values after optimization.
    f_opt : float
        The optimal function value after optimization.
    x_values : list
        A history of variable values across generations.
    f_min_values : list
        A history of minimum function values across generations.

    Notes
    -----
    - This class supports multiple algorithms, including DE, GA, Nelder-Mead, PSO, CMAES, and others.
    - Supports integer and continuous (float) variables.
    - Automatically handles maximization by converting it to minimization during optimization.
    """

    class MySOOProblem(ElementwiseProblem):
        """
        Defines a single-objective optimization problem.

        Attributes
        ----------
        objective_func : callable
            The objective function to optimize.
        constraints : list
            A list of constraint functions for the problem.
        variable_ranges : dict
            Ranges (lower and upper bounds) for each optimization variable.
        variable_types : dict
            Types of the variables (e.g., "integer", "float").
        runner : callable, optional
            A parallel runner for evaluating the objective function.
        """

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
            """
            Evaluates the objective function and constraints.

            Parameters
            ----------
            x : list or ndarray
                A list of variable values to evaluate.
            out : dict
                A dictionary to store the objective function value and constraint values.

            Returns
            -------
            None
            """
            for i, (var, vtype) in enumerate(self.variable_types.items()):
                if vtype == 'integer':
                    x[i] = int(np.round(x[i]))

            out["F"] = -1 * self.objective_func(x)
            out["G"] = np.array([constraint(x) for constraint in self.constraints])

    def define_problem(self):
        """
        Defines the single-objective optimization problem.

        Returns
        -------
        MySOOProblem
            An instance of the custom single-objective problem.
        """
        return self.MySOOProblem(self.objective_func, self.constraints, self.variable_ranges, self.variable_types, runner=self.runner if self.parallel_processing else None)

    def optimize(self, n_gen):
        self.x_values = []
        self.f_min_values = []

        def callback(algorithm):
            feas_inds = [ind for ind in algorithm.pop if np.all(ind.get("G") <= 0)]
            if feas_inds:
                self.f_min_values.append(min(ind.get("F") for ind in feas_inds))
                best_ind = feas_inds[np.argmin([ind.get("F") for ind in feas_inds])]
                self.x_values.append([
                    int(np.round(best_ind.X[i])) if self.variable_types[f'x{i+1}'] == 'integer' else best_ind.X[i]
                    for i in range(len(best_ind.X))
                ])

        self.algorithm = self.select_algorithm()
        res = minimize(self.problem, self.algorithm, ('n_gen', n_gen), verbose=True, callback=callback)

        self.x_opt = [
            int(np.round(res.X[i])) if self.variable_types[f'x{i+1}'] == 'integer' else res.X[i]
            for i in range(len(res.X))
        ]
        self.f_opt = -res.F[0]

        print("Performing a final simulation with the optimized variables...")
        final_simulation_result = self.objective_func(self.x_opt)
        print(f"Final simulation result: {final_simulation_result}")

    def select_algorithm(self):
        """
        Selects the optimization algorithm based on the method name.

        Returns
        -------
        object
            The selected optimization algorithm.
        """
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
        """
        Prints the results of the optimization process.

        Outputs
        -------
        - Optimal variables and function value.
        - Results across generations.
        """
        log_filename = os.path.join("/Users/morteza/Documents/projects/TANGO/examples/", self.plot_name + '_log')
        with open(log_filename, 'w') as log_file:
            log_file.write("Optimal Variables:\n")
            formatted_vars = []
            for i, var in enumerate(self.x_opt):
                if self.variable_types[f'x{i+1}'] == 'integer':
                    formatted_vars.append(f"x{i+1} = {int(var)}")
                else:
                    formatted_vars.append(f"x{i+1} = {var:.6f}")
            log_file.write(', '.join(formatted_vars) + "\n")

            log_file.write("Maximum Value:\n")
            log_file.write(f"{self.f_opt}\n\n")

            for gen in range(len(self.f_min_values)):
                x_vals_str = ', '.join([
                    f"x{i+1} = {int(self.x_values[gen][i])}" if self.variable_types[f'x{i+1}'] == 'integer' \
                    else f"x{i+1} = {self.x_values[gen][i]:.6f}"
                    for i in range(len(self.x_values[gen]))
                ])

                if isinstance(self.f_min_values[gen], np.ndarray):
                    f_min_str = ', '.join([f"{val:.6f}" for val in self.f_min_values[gen]])
                    log_file.write(f"Generation {gen + 1}: {x_vals_str}, f_min = [{f_min_str}]\n")
                else:
                    log_file.write(f"Generation {gen + 1}: {x_vals_str}, f_min = {self.f_min_values[gen]:.6f}\n")

        print(f"Results have been saved to {log_filename}.")

    def plot_results(self):
        """
        Plots the optimization results across generations with real names for variables and objectives.
        Each variable is plotted separately to handle different ranges effectively.
        """
        generations = range(1, len(self.f_min_values) + 1)

        plt.style.use('seaborn-v0_8-deep')

        num_variables = len(self.variable_names)
        plt.figure(figsize=(6 * num_variables, 6))

        for i, var_name in enumerate(self.variable_names):
            plt.subplot(1, num_variables, i + 1)
            plt.plot(generations, [x[i] for x in self.x_values], label=f'{var_name}', linewidth=2)
            plt.xlabel('Generation', fontsize=12)
            plt.ylabel(f'{var_name}', fontsize=12)
            plt.grid(alpha=0.5, linestyle='--')

        plt.tight_layout()
        plt.savefig(os.path.join("/Users/morteza/Documents/projects/TANGO/examples/", self.plot_name + '_variables.png'), dpi=300)

        plt.figure(figsize=(8, 6))
        f_min_values_array = np.array(self.f_min_values)
        if self.optimization_specs.target_type[0] == 'maximize':
            plt.plot(generations, -f_min_values_array, label=f'{self.objective_names[0]}', linewidth=2, color='C1')
        else:
            plt.plot(generations, f_min_values_array, label=f'{self.objective_names[0]}', linewidth=2, color='C1')
        plt.xlabel('Generation', fontsize=12)
        plt.ylabel(f'{self.objective_names[0]}', fontsize=12)
        plt.grid(alpha=0.5, linestyle='--')

        plt.tight_layout()
        plt.savefig(os.path.join("/Users/morteza/Documents/projects/TANGO/examples/", self.plot_name + '_objective.png'), dpi=300)


class MOOOptimizer(BaseOptimizer):
    """
    Multi-Objective Optimization (MOO) class.

    This class handles multi-objective optimization by extending the `BaseOptimizer`.
    It defines the multi-objective problem, executes the optimization, normalizes
    the objectives, and selects the final solution based on user-defined criteria.

    Inner Class
    -----------
    MyMOOProblem : ElementwiseProblem
        A custom multi-objective optimization problem definition for Pymoo.
        Handles variable ranges, constraints, and evaluation of multiple objectives.

    Attributes
    ----------
    x_opt : list
        The optimal variable values on the Pareto front.
    f_opt : ndarray
        The objective function values on the Pareto front.
    normalized_f_opt : ndarray
        The normalized objective values on the Pareto front.
    solution : tuple
        The final selected solution (variables and objectives).
    res : object
        The optimization result object containing history and statistics.

    Notes
    -----
    - Supports algorithms such as NSGA-II and NSGA-III.
    - Automatically handles integer and continuous (float) variables.
    """

    class MyMOOProblem(ElementwiseProblem):
        """
        Defines a multi-objective optimization problem.

        Attributes
        ----------
        objective_func : callable
            The objective function to optimize (returns multiple objectives).
        constraints : list
            A list of constraint functions for the problem.
        variable_ranges : dict
            Ranges (lower and upper bounds) for each optimization variable.
        variable_types : dict
            Types of the variables (e.g., "integer", "float").
        runner : callable, optional
            A parallel runner for evaluating the objective function.

        """

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
                             elementwise_runner=runner)

        def _evaluate(self, x, out, *args, **kwargs):
            """
            Evaluates the objective functions and constraints.

            Parameters
            ----------
            x : list or ndarray
                A list of variable values to evaluate.
            out : dict
                A dictionary to store the objective function values and constraint values.

            Returns
            -------
            None
            """
            for i, (var, vtype) in enumerate(self.variable_types.items()):
                if vtype == 'integer':
                    x[i] = int(np.round(x[i]))

            out["F"] = self.objective_func(x)
            out["G"] = np.array([constraint(x) for constraint in self.constraints])

    def define_problem(self):
        """
        Defines the multi-objective optimization problem.

        Returns
        -------
        MyMOOProblem
            An instance of the custom multi-objective problem.
        """
        return self.MyMOOProblem(self.objective_func, self.constraints, self.variable_ranges, self.variable_types, runner=self.runner)

    def optimize(self, n_gen):
        self.algorithm = self.select_algorithm()
        self.res = minimize(self.problem, self.algorithm, ('n_gen', n_gen), verbose=True, save_history=True)

        self.x_opt = [
            [int(np.round(x[i])) if self.variable_types[f'x{i+1}'] == 'integer' else x[i]
             for i in range(len(x))]
            for x in self.res.X
        ]
        self.f_opt = self.res.F

        self._normalize_objectives()

        if self.optimization_specs.final_selection == 'ASF':
            self.solution = self._select_asf_solution()
        elif self.optimization_specs.final_selection == 'pseudo_weights':
            self.solution = self._select_pseudo_weights_solution()

        print("Performing a final simulation with the selected solution...")
        final_solution_vars, final_solution_objs = self.solution
        final_simulation_result = self.objective_func(final_solution_vars)
        print(f"Final simulation result: {final_simulation_result}")

    def select_algorithm(self):
        """
        Selects the optimization algorithm based on the method name.

        Returns
        -------
        object
            The selected optimization algorithm.

        Raises
        ------
        ValueError
            If the specified algorithm is not recognized.
        """
        if self.algorithm_name == 'nsga2':
            return NSGA2(pop_size=self.pop_size, sampling=FloatRandomSampling(), crossover=SBX(prob=self.optimization_specs.crossover_probability, eta=self.optimization_specs.distribution_index), mutation=PM(eta=self.optimization_specs.polynomial_mutation), eliminate_duplicates=True)
        elif self.algorithm_name == 'nsga3':
            ref_dirs = UniformReferenceDirectionFactory(self.problem.n_obj, n_points=self.pop_size).do()
            return NSGA3(pop_size=self.pop_size, ref_dirs=ref_dirs, sampling=FloatRandomSampling(), crossover=SBX(prob=self.optimization_specs.crossover_probability, eta=self.optimization_specs.distribution_index), mutation=PM(eta=self.optimization_specs.polynomial_mutation), eliminate_duplicates=True)
        else:
            raise ValueError(f"Algorithm {self.algorithm_name} not recognized. Available algorithms: nsga2, nsga3")

    def _normalize_objectives(self):
        """
        Normalizes the objective values on the Pareto front.

        Notes
        -----
        - Normalizes objectives to the range [0, 1] based on their minimum and maximum values.
        - Applies user-specified weights to the normalized objectives.
        """
        self.f_max = np.max(self.f_opt, axis=0)
        self.f_min = np.min(self.f_opt, axis=0)
        normalized_f_opt = np.zeros_like(self.f_opt)

        for i in range(len(self.f_max)):
            if self.f_max[i] == self.f_min[i]:
                normalized_f_opt[:, i] = 0.0
            else:
                normalized_f_opt[:, i] = (self.f_opt[:, i] - self.f_min[i]) / (self.f_max[i] - self.f_min[i])


        self.normalized_f_opt = normalized_f_opt * self.optimization_specs.weights

    def _select_asf_solution(self):
        """
        Selects the final solution using the Achievement Scalarizing Function (ASF).

        Returns
        -------
        tuple
            The selected variable values and objective values.
        """
        index = calculate_asf(self.normalized_f_opt)
        return self.x_opt[index], self.f_opt[index]

    def _select_pseudo_weights_solution(self):
        """
        Selects the final solution using pseudo-weighting.

        Returns
        -------
        tuple
            The selected variable values and objective values.
        """
        index = calculate_pseudo_weights(self.normalized_f_opt)
        return self.x_opt[index], self.f_opt[index]

    def print_results(self):
        """
        Prints the results of the optimization process.

        Outputs
        -------
        - Variable values and objective values for each solution on the Pareto front.
        - The final selected solution.
        """
        log_filename = os.path.join("/Users/morteza/Documents/projects/TANGO/examples/", self.plot_name + '_log')
        with open(log_filename, 'w') as log_file:
            if self.x_opt is None or self.f_opt is None:
                log_file.write("No valid optimization results to display.\n")
                print(f"Results have been saved to {log_filename}.")
                return

            log_file.write("Optimal Variables and Objectives on Pareto front:\n")
            for i in range(len(self.f_opt)):
                log_file.write(f"Solution {i + 1}:\n")
                for j in range(len(self.x_opt[i])):
                    log_file.write(f"x{j + 1} = {self.x_opt[i][j]}\n")
                for k in range(len(self.f_opt[i])):
                    log_file.write(f"Objective {k + 1} = {self.f_opt[i][k]}\n")
                log_file.write("\n")

            if self.optimization_specs.final_selection == 'ASF':
                log_file.write("\nSelected ASF Solution:\n")
                log_file.write(f"{self.solution}\n")
            elif self.optimization_specs.final_selection == 'pseudo_weights':
                log_file.write("\nSelected Pseudo-Weights Solution:\n")
                log_file.write(f"{self.solution}\n")

        print(f"Results have been saved to {log_filename}.")

    def plot_results(self):
        """
        Plots the Pareto front and the selected solution with real names for objectives.
        Makes it visually appealing and scientifically formatted.
        """
        if self.f_opt is None:
            print("No valid results to plot.")
            return

        original_f_opt = np.copy(self.f_opt)

        for i, target_type in enumerate(self.optimization_specs.target_type):
            if target_type == 'maximize':
                original_f_opt[:, i] = -self.f_opt[:, i]

        selected_solution = self.solution[1] if self.solution is not None else None

        plt.style.use('seaborn-v0_8-colorblind')

        if len(original_f_opt[0]) == 2:
            plt.figure(figsize=(8, 6))
            plt.scatter(original_f_opt[:, 0], original_f_opt[:, 1], label='Pareto Front', s=50, alpha=0.7)
            if selected_solution is not None:
                original_selected_solution = np.copy(selected_solution)
                for i, target_type in enumerate(self.optimization_specs.target_type):
                    if target_type == 'maximize':
                        original_selected_solution[i] = -selected_solution[i]
                plt.scatter(original_selected_solution[0], original_selected_solution[1], color='red', marker='x', s=200, label='Selected Solution')
            plt.xlabel(self.objective_names[0], fontsize=14)
            plt.ylabel(self.objective_names[1], fontsize=14)
            plt.legend(fontsize=12)
            plt.grid(alpha=0.5, linestyle='--')
            plt.tight_layout()
            plt.savefig(os.path.join("/Users/morteza/Documents/projects/TANGO/examples/", self.plot_name + '_moo_pareto_front_2d.png'), dpi=300)

        elif len(original_f_opt[0]) == 3:
            fig = plt.figure(figsize=(10, 8))
            ax = fig.add_subplot(111, projection='3d')
            ax.scatter(original_f_opt[:, 0], original_f_opt[:, 1], original_f_opt[:, 2], label='Pareto Front', s=50, alpha=0.7)
            if selected_solution is not None:
                original_selected_solution = np.copy(selected_solution)
                for i, target_type in enumerate(self.optimization_specs.target_type):
                    if target_type == 'maximize':
                        original_selected_solution[i] = -selected_solution[i]
                ax.scatter(original_selected_solution[0], original_selected_solution[1], original_selected_solution[2], color='red', marker='x', s=200, label='Selected Solution')
            ax.set_xlabel(self.objective_names[0], fontsize=14)
            ax.set_ylabel(self.objective_names[1], fontsize=14)
            ax.set_zlabel(self.objective_names[2], fontsize=14)
            ax.legend(fontsize=12)
            plt.tight_layout()
            plt.savefig(os.path.join("/Users/morteza/Documents/projects/TANGO/examples/", self.plot_name + '_moo_pareto_front_3d.png'), dpi=300)
        else:
            print("Plotting is only supported for 2 or 3 objectives.")

    def plot_hypervolume_igd(self):
        """
        Plots the Hypervolume and IGD over generations with scientific styling.
        """
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

        plt.style.use('seaborn-v0_8-whitegrid')

        # Hypervolume Plot
        plt.figure(figsize=(14, 6))
        plt.subplot(1, 2, 1)
        plt.plot(generations, hv_values, '-o', linewidth=2, markersize=6)
        plt.xlabel('Generation', fontsize=14)
        plt.ylabel('Hypervolume', fontsize=14)
        plt.grid(alpha=0.5, linestyle='--')
        plt.legend(fontsize=12)

        # IGD Plot
        plt.subplot(1, 2, 2)
        plt.plot(generations, igd_values, '-o', color='orange', linewidth=2, markersize=6)
        plt.xlabel('Generation', fontsize=14)
        plt.ylabel('Inverted Generational Distance (IGD)', fontsize=14)
        plt.grid(alpha=0.5, linestyle='--')
        plt.legend(fontsize=12)

        plt.tight_layout()
        plt.savefig(os.path.join("/Users/morteza/Documents/projects/TANGO/examples/", self.plot_name + '_hypervolume_igd.png'), dpi=300)


def calculate_asf(normalized_objectives):
    """
    Calculates the Achievement Scalarizing Function (ASF) values.

    This function computes ASF values for a set of normalized objective vectors
    and returns the index of the vector with the smallest ASF value. The ASF is
    used to select a solution on the Pareto front that balances all objectives
    based on their maximum normalized value.

    Parameters
    ----------
    normalized_objectives : ndarray
        A 2D array of normalized objective values, where each row corresponds
        to a solution, and each column corresponds to an objective.

    Returns
    -------
    int
        The index of the solution with the smallest ASF value.

    Example
    -------
    >>> normalized_objectives = np.array([[0.2, 0.8], [0.5, 0.5], [0.1, 0.9]])
    >>> calculate_asf(normalized_objectives)
    1
    """
    asf_values = np.max(normalized_objectives, axis=1)
    return np.argmin(asf_values)


def calculate_pseudo_weights(normalized_objectives):
    """
    Calculates the pseudo-weighted sum for normalized objectives.

    This function computes the weighted sum for each normalized objective vector
    and returns the index of the vector with the smallest weighted sum. Pseudo-weighting
    is often used to select a solution on the Pareto front based on user-defined
    weights or uniform preference among objectives.

    Parameters
    ----------
    normalized_objectives : ndarray
        A 2D array of normalized objective values, where each row corresponds
        to a solution, and each column corresponds to an objective.

    Returns
    -------
    int
        The index of the solution with the smallest pseudo-weighted sum.

    Example
    -------
    >>> normalized_objectives = np.array([[0.2, 0.8], [0.5, 0.5], [0.1, 0.9]])
    >>> calculate_pseudo_weights(normalized_objectives)
    1
    """
    weighted_sum = np.sum(normalized_objectives, axis=1)
    return np.argmin(weighted_sum)

