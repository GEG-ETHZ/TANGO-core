import json
import logging
import inspect
import os
import numpy as np
from datetime import datetime

import pandas as pd
from scipy.optimize import minimize

from dataclasses import dataclass
from tango.utils import load_from_yaml, read_result
from tango.driver import Tango


@dataclass
class OptimizationSpecs:
    method: str = None
    options: dict = None
    bounds: list = None
    def __post_init__(self):
        default_values = [{'maxitr': 10, 'disp': True}, [(0., None)]]
        for idx, s in enumerate(['options', 'bounds']):
            if getattr(self, s, None) == None:
                setattr(self, s, default_values[idx])
    @classmethod
    def from_dict(cls, env): # ignore extra arguments passed to a dataclass
        return cls(**{
            k: v for k, v in env.items()
            if k in inspect.signature(cls).parameters
        })


class Optimizer:

    def __init__(self,
                 fun: object):
        """
            Optimizer to minimize LCOE by tuning mass flow rate.
        """
        self._tango = fun
        self._initialize()


    def _initialize(self) -> None:
        d = dict()
        if 'optimization' in self._tango.specs:
            d = self._tango.specs['optimization']
            if 'options' in self._tango.specs['optimization']:
                d = d | self._tango.specs['optimization']['options']
        specs =  OptimizationSpecs.from_dict(d)
        self._method = specs.method
        self._bounds = specs.bounds
        self._options = specs.options
        self._x0 = self._initial_guess()
        self._itr_count = 0
        self._init_result_smry()
        self._set_nmlz_values()


    def _set_nmlz_values(self) -> None:
        self._x_max = 2 * self._x0
        self._x_min = 0.
        self._x0_nmlz = self._normalize(num=self._x0, bound=[self._x_min, self._x_max])


    def _init_result_smry(self) -> None:
        self._results_summary = dict()
        self._results_summary['num_fun_eval'] = list()
        self._results_summary['obj'] = list()



    @staticmethod
    def _normalize(num: float, bound: list[float]) -> float:
        min, max = bound
        return (num - min) / (max - min)


    @staticmethod
    def _denormalize(num, bound: list[float]) -> float:
        min, max = bound
        return num * (max - min) + min


    def _initial_guess(self) -> float: #TODO: support more parameters (should it be done by WorkflowOrchestrator?)
        try:
            return self._tango.specs['schedule']['mass_flow_rate']
        except Exception as e:
            raise RuntimeError(f"Failed to get mass_flow_rate: {e}")


    def _f(self, x: list) -> float:
        """
            Wrapper function to run TANGO.

            Args:
                x: list of parameter(s) to be tuned

            Returns: Objective function
            Note: Currently only supports 'mass_flow_rate' as a parameter
        """

        self._itr_count += 1
        logging.info(f"Function evaluation count: {self._itr_count}")
        mass_flow_rate = self._denormalize(num=x[0], bound=[self._x_min, self._x_max])
        # mass_flow_rate = x[0]

        try:
            self._tango.specs['schedule']['mass_flow_rate'] = mass_flow_rate
            self._tango.execute()
            econ_results = self._tango.workflow.economic.get_results()
            obj = econ_results['LCOE']
            logging.info(f"Optimization status:\n{json.dumps({'status': 'running','fun': obj, 'x': mass_flow_rate}, indent=4)}")
            if np.isnan(obj):
                obj = 1e10
        except Exception as e:
            logging.warning(
                f"Optimization status:\n{json.dumps({'status': f'TANGO run failed: {e}', 'x': mass_flow_rate}, indent=4)}")
            obj = 1.e10

        self._results_summary['num_fun_eval'].append(self._itr_count)
        self._results_summary['obj'].append(obj)

        return obj


    def _post(self, output: dict) -> None:
        smry = {'message': output['message'],
                'health': \
                    {
                        'status': output['status'],
                        'success': output['success'],
                    },
                'run_summary': \
                    {
                        'num_function_evaluations': output['nfev'],
                        'num_jacobian_evaluations': output['njev'],
                        'num_iterations': output['nit'],
                        'x': output['x'][0],
                        'fun': output['fun']
                    }
                }
        logging.info(f"Optimization output:\n{json.dumps(smry, indent=4)}")

        df = pd.DataFrame(self._results_summary)
        df.to_csv(f"{os.path.splitext(self._tango.input_file)[0]}_opt_smry.csv", index=False)


    def execute(self) -> None:

        logging.info(f"Running optimization\n")

        try:
            output = minimize(fun=self._f,
                              x0=[self._x0_nmlz],
                              method=self._method,
                              options=self._options,
                              bounds=self._bounds)
        except Exception as e:
            raise RuntimeError(f"Optimization failed: {e}")

        self._post(output)

