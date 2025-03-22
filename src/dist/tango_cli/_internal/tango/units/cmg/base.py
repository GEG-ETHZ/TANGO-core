from dataclasses import dataclass
import os
import logging
from string import Template
import subprocess

from tango import utils
from tango.core.config import *
from tango.core.abstracts.unit import *

@dataclass
class CMGSpecs:
    r"""
    Specifications for CMG simulation execution.

    Attributes:
        inputfilepath (str): Path to the input .dat file.
        queue (str): Execution queue (e.g., 'local', 'Euler'). Default is 'local'.
        np (int): Number of processors to use. Default is 1.
        version (str): CMG version to use. Default is the latest version.
        nosim (bool): If True, only check input file validity without simulation. Default is False.

    Methods:
        __post_init__: Validates required fields and file paths.
    """

    inputfilepath: str = None
    queue: str = 'local'
    np: int = 1
    version: str = None
    nosim: bool = False

    def __post_init__(self):
        required_fields = ['inputfilepath']
        for field in required_fields:
            if getattr(self, field, None) is None:
                raise RuntimeError(f"Required parameter: {field} is not found.")
        if not os.path.exists(self.inputfilepath):
            raise RuntimeError(f"Input file path for CMG: {self.inputfilepath} not found.")

class CMGBaseUnit(Unit):
    r"""
    Base Unit for CMG simulation execution.

    This class handles the configuration and execution of CMG simulations,
    including input validation, command construction, and execution.

    Attributes:
        specs (CMGSpecs): Specifications for the CMG simulation.
        inputfilepath (str): Path to the input .dat file.
        queue (str): Execution queue.
        np (int): Number of processors.
        version (str): CMG version.
        nosim (bool): If True, only checks input validity without simulation.
        cmd (str): Constructed command for execution.

    Methods:
        stream_interface: Executes the CMG simulation based on the constructed command.
        _get_program: Resolves the executable path for the CMG simulator.
        _parse_args: Constructs the command for simulation execution.
    """

    def __init__(self, id: str, specs: dict) -> None:
        """
        Initializes a new instance of the CMGBaseUnit class.

        Args:
            id (str): Identifier for the CMG unit.
            specs (dict): Specifications for the CMG simulation.
        """
        super().__init__(id, specs)
        self.specs = CMGSpecs(**specs)
        self.inputfilepath = self.specs.inputfilepath
        self.queue = self.specs.queue
        self.np = self.specs.np
        self.version = self.specs.version
        self.nosim = self.specs.nosim
        self._parse_args()

    def _get_program(self) -> str:
        r"""
        Resolves the path to the CMG executable.

        Returns:
            str: Path to the CMG executable.
        """
        # Temporary paths for testing
        cmg_dir = '/Users/tonishi/workdir/CMG'
        os_fld = 'Win_x64'
        simulator_dir = os.path.join(cmg_dir, self.simulator.upper())

        if self.version is None:
            available_versions = [name for name in os.listdir(simulator_dir) if os.path.isdir(os.path.join(simulator_dir, name))]
            available_versions.sort()
            version_fld = available_versions[-1]
        else:
            version_fld = str(self.version)

        exe = f"{CMG_EXE[self.simulator]}".format(version=version_fld.replace('.', ''))
        return os.path.join(simulator_dir, version_fld, os_fld, 'EXE', exe)

    def _parse_args(self) -> None:
        """
        Constructs the command for simulation execution.

        Raises:
            RuntimeError: If argument parsing fails.
        """
        args = {
            'program': self._get_program().replace('\\', '/'),
            'inputfilepath': self.inputfilepath.replace('\\', '/'),
            'np': str(self.np),
            'wd': os.path.dirname(self.inputfilepath).replace('\\', '/')
        }
        try:
            template = CMG_CMG_TEMPLATE + ' -checkonly' if self.nosim else CMG_CMG_TEMPLATE
            self.cmd = Template(template).substitute(args)
        except Exception as e:
            raise RuntimeError(f"Failed to parse arguments: {e}")

    def stream_interface(self) -> None:
        """
        Executes the CMG simulation based on the constructed command.

        Logs the command and handles execution.

        Raises:
            NotImplementedError: If the queue option is not implemented.
        """
        logging.info(f"Starting command: {self.cmd}")
        if self.specs.queue == 'local':
            proc = subprocess.run(self.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                logging.warning(f"CMG simulation exited with non-zero return code: {proc.returncode}")
        else:
            raise NotImplementedError(f"Queue option: {self.queue} has not yet been implemented.")
