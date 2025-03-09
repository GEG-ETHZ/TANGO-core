import ast
import operator as op


class FunctionEvaluator:
    """
    A class to evaluate mathematical expressions dynamically.
    """

    def __init__(self, target_mapping, variable_mapping, orchestrator=None, economic=None):
        """
        Initializes the FunctionEvaluator.

        Args:
            target_mapping (dict): A mapping for target parameters.
            variable_mapping (dict): A mapping for variable parameters.
            orchestrator (object): Orchestrator object containing system units and specs.
            economic (object): Economic object, if applicable.
        """
        self.target_mapping = self._preprocess_target_mapping(target_mapping)
        self.variable_mapping = None
        self.evaluated_functions = {}
        self.SAFE_OPERATORS = {
            ast.Add: op.add,
            ast.Sub: op.sub,
            ast.Mult: op.mul,
            ast.Div: op.truediv,
            ast.Pow: op.pow,
            ast.BitXor: op.xor,
            ast.USub: op.neg,
        }
        self.context = None

        if orchestrator or economic:
            specs_for_mapping = self._gather_specs(orchestrator, economic)
            self.preprocess_variable_mapping(variable_mapping, specs_for_mapping)

    def _preprocess_target_mapping(self, mapping):
        """
        Preprocesses the target mapping to remove 'self.tango_instance.workflow' prefix.

        Args:
            mapping (dict): The original target mapping.

        Returns:
            dict: A processed mapping with the prefix removed.
        """
        processed_mapping = {}
        for key, value in mapping.items():
            if value.startswith("self.tango_instance.workflow."):
                processed_mapping[key] = value.replace("self.tango_instance.workflow.", "self.")
            else:
                processed_mapping[key] = value
        return processed_mapping

    def _gather_specs(self, orchestrator, economic):
        """
        Gathers specs from the orchestrator and economic components.

        Args:
            orchestrator (object): Orchestrator object containing system units and specs.
            economic (object): Economic object, if applicable.

        Returns:
            dict: A dictionary of specs for preprocessing.
        """
        specs = {}

        if orchestrator:
            if hasattr(orchestrator.unit, 'surface'):
                specs["surface"] = orchestrator.unit.surface.specs
            if hasattr(orchestrator.unit, 'injection_well'):
                specs["injection_well"] = orchestrator.unit.injection_well._specs
            if hasattr(orchestrator.unit, 'production_well'):
                specs["production_well"] = orchestrator.unit.production_well._specs
            if hasattr(orchestrator.unit, 'reservoir'):
                specs["reservoir"] = orchestrator.unit.reservoir.specs

        if economic and economic.specs:
            specs["economic"] = economic.specs

        return specs

    def preprocess_variable_mapping(self, mapping, specs):
        """
        Dynamically preprocesses the variable mapping to reference the correct specs.

        Args:
            mapping (dict): The original variable mapping.
            specs (dict): A dictionary of specs (surface, injection well, production well, reservoir, economic).

        Returns:
            dict: A processed mapping that maps to the appropriate specs.
        """
        def to_dict(obj):
            """Convert an object to a dictionary if possible."""
            if isinstance(obj, dict):
                return obj
            elif hasattr(obj, '__dict__'):
                return vars(obj)
            else:
                raise TypeError(f"Object of type {type(obj)} is not iterable or convertible to a dictionary.")

        specs_dicts = {key: to_dict(value) for key, value in specs.items() if value}

        processed_mapping = {}

        for key, value in mapping.items():
            for spec_name, spec_dict in specs_dicts.items():
                if spec_name in ["injection_well", "production_well"]:
                    for original_key in ["diameter", "well_length", "epsilon", "vertical_deviation", "wellhead_depth", "num_cells"]:
                        renamed_key = f"{spec_name}_{original_key}"
                        if renamed_key == key:
                            processed_mapping[key] = f"self.orchestrator.unit.{spec_name}._specs.{original_key}"
                            break
                else:
                    # Normal mapping for other categories
                    if key in spec_dict:
                        if spec_name == "economic":
                            processed_mapping[key] = f"self.economic.specs.{key}"
                        else:
                            processed_mapping[key] = f"self.orchestrator.unit.{spec_name}.specs.{key}"
                        break

        self.variable_mapping = processed_mapping

    def set_context(self, context):
        """
        Sets the context for evaluation.

        Args:
            context (object): The context object (e.g., NativeWorkflow instance).
        """
        self.context = context

    def resolve_parameters(self, param_names):
        """
        Resolves parameter values based on the mappings.

        Args:
            param_names (list): List of parameter names to resolve.

        Returns:
            dict: A dictionary of resolved parameter values.

        Raises:
            KeyError: If a parameter is not found in any mapping.
        """
        if self.context is None:
            raise AttributeError("Context is not set. Use `set_context` to provide the necessary context.")

        parameters = {}
        for param in param_names:
            if param in self.target_mapping:
                parameters[param] = eval(self.target_mapping[param], {}, {"self": self.context})
            elif param in self.variable_mapping:
                parameters[param] = eval(self.variable_mapping[param], {}, {"self": self.context})
            else:
                raise KeyError(f"Parameter '{param}' not found in any mapping.")
        return parameters

    def extract_variables(self, expr):
        """
        Extracts variable names from a mathematical expression.

        Args:
            expr (str): The mathematical expression as a string.

        Returns:
            list: A list of variable names used in the expression.
        """
        tree = ast.parse(expr, mode='eval')
        return [node.id for node in ast.walk(tree) if isinstance(node, ast.Name)]

    def eval_math_expr(self, expr, parameter_dict):
        """
        Safely evaluates a mathematical expression using a parameter dictionary.

        Args:
            expr (str): The mathematical expression as a string.
            parameter_dict (dict): A dictionary of parameter values.

        Returns:
            float: The result of the evaluated expression.
        """
        def _eval(node):
            if isinstance(node, ast.Num):
                return node.n
            elif isinstance(node, ast.BinOp):
                return self.SAFE_OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
            elif isinstance(node, ast.UnaryOp):
                return self.SAFE_OPERATORS[type(node.op)](_eval(node.operand))
            elif isinstance(node, ast.Name):
                return parameter_dict[node.id]
            else:
                raise TypeError(f"Unsupported type: {type(node)}")

        parsed_expr = ast.parse(expr, mode='eval').body
        return _eval(parsed_expr)

    def evaluate_functions(self, functions):
        """
        Evaluates multiple functions and stores their results.

        Args:
            functions (dict): A dictionary of function definitions.

        """
        for function_name, function_def in functions.items():
            if function_def['type'] == 'mathematical_expression':
                expr = function_def['value']
                param_names = self.extract_variables(expr)
                parameters = self.resolve_parameters(param_names)
                result = self.eval_math_expr(expr, parameters)
                self.evaluated_functions[function_name] = result
            elif function_def['type'] == 'Constant':
                self.evaluated_functions[function_name] = function_def['value']
            elif function_def['type'] == 'segmented_linear':
                continue
            else:
                continue
