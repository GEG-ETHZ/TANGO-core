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
    inputfilepath: str = None  # input file (.dat) path
    queue: str = 'local'  # local, Euler, etc.
    np: int = 1  # number of processors. optional (default=1)
    version: str = None  # version. optional (default-latest)
    nosim: bool = False  # optional (default=False)
    def __post_init__(self):
        required_fields = ['inputfilepath']
        for s in required_fields:
            if getattr(self, s, None) == None:
                raise RuntimeError(f"Required parameter: {s} is not found.")
        if not os.path.exists(self.inputfilepath):
            raise RuntimeError(f"Input file path for CMG: {self.inputfilepath} not found.")


class CMGBaseUnit(Unit):

    def __init__(self, id: str, specs: dict) -> None:
        super().__init__(id, specs)
        self.specs = CMGSpecs(**specs)
        self.inputfilepath = self.specs.inputfilepath
        self.queue = self.specs.queue
        self.np = self.specs.np
        self.version = self.specs.version
        self.nosim = self.specs.nosim
        self._parse_args()


    def _get_program(self) -> str:
        #TODO: use CMG_HOME env var
        # cmg_dir = CMG_PATH[utils.get_os()] #TODO: uncomment
        # exe_fld_name = CMG_EXE_FLD[utils.get_os()]  # TODO: uncomment
        cmg_dir = '/Users/tonishi/workdir/CMG' # temporary treatment to test in Mac
        os_fld = 'Win_x64' # temporary treatment to test in Mac
        simulator_dir = os.path.join(cmg_dir, self.simulator.upper()) #TODO: add more checking.
        if self.version == None:
            # flds = [x[0] for x in os.walk(simulator_dir)]
            flds = [name for name in os.listdir(simulator_dir) if os.path.isdir(os.path.join(simulator_dir, name))]
            flds.sort()
            version_fld = flds[-1]
        else:
            version_fld = str(self.version)
        # exe = CMG_EXE[self.simulator].format(version_fld.replace('.', ''))
        exe = f"{CMG_EXE[self.simulator]}".format(**{'version': version_fld.replace('.', '')})
        lst = [simulator_dir, version_fld, os_fld, 'EXE', exe]

        return os.path.join(*lst)


    def _parse_args(self) -> None:
        d_tmp = dict()
        d_tmp['program'] = self._get_program().replace('\\','/') #TODO: check if this replacement works in linux
        d_tmp['inputfilepath'] = self.inputfilepath.replace('\\','/')
        d_tmp['np'] = str(self.np)
        d_tmp['wd'] = os.path.dirname(self.inputfilepath).replace('\\','/') # working dir
        try:
            template = template + ' -checkonly' if self.nosim else CMG_CMG_TEMPLATE
            self.cmd = Template(template).substitute(d_tmp)
            #TODO: sudo su .... in linux?
        except:
            RuntimeError(f"Failed to parse args (template: {template})")


    def execute(self) -> None:
        logging.info(f"Starting cmd: {self.cmd}")
        if self.specs.queue == 'local':
            proc = subprocess.run(self.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                logging.warning(f"CMG simulation exited with non-zero return code: {proc.returncode}")
            #TODO: add output
        else:
            raise NotImplementedError(f"Queue option: {queue} has not yet been implemented.")