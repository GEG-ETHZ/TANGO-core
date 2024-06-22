WORKFLOW_OPTIONS = {'native': 'NativeWorkflow',
                    'cmg': 'CMGWorkflow'}

SYSTEM_OPTIONS = {'native': 'SystemNative',
                  'native_cpg': 'SystemCPGNative',
                  'native_dh': 'SystemCPGNative',
                  'moose_cpg': 'SystemExternal',
                  'tespy_cpg': 'SystemExternal',
                  'tespy_orc': 'SystemExternal',
                  'tespy_sf': 'SystemExternal',
                  'tespy_df': 'SystemExternal',
                  'native_orc': 'SystemORCNative'}

UNIT_OPTIONS = {
                    'surface':
                        {
                            'native_cpg': 'SurfaceUnitCPGNative',
                            'native_dh': 'SurfaceUnitDHNative',
                            'moose_cpg': 'SurfaceUnitCPGNative',
                            'dwsim_cpg': 'SurfaceUnitCPGDWSIM',
                            'tespy_cpg': 'SurfaceUnitCPGTESPy',
                            'tespy_orc': 'SurfaceUnitORCTESPy',
                            'tespy_sf': 'SurfaceUnitSingleFlashTESPy',
                            'tespy_df': 'SurfaceUnitDoubleFlashTESPy',
                            'native_orc': 'SurfaceUnitORCNative'
                        },
                    'injection_well':
                        {
                            'native': 'InjectionWellUnitNative',
                            'moose': 'WellUnitMOOSE'
                        },
                    'production_well':
                        {
                        'native': 'ProductionWellUnitNative'
                        },
                    'horizontal_well':
                        {
                            'native': 'HorizontalWellUnitNative'
                        },
                    'production_well_pump':
                        {
                            'native': 'ProductionWellPumpUnitNative'
                        },
                    'reservoir':
                        {
                            'native': 'ReservoirUnitNative',
                            'moose': 'ReservoirUnitPorousflow'
                        },
                    'stream':
                        {
                            'native': 'StreamNative'
                        },
                    'cmg':
                        {
                            'imex': 'ImexUnit',
                            'gem': 'GemUnit',
                            'coflow': 'CoFlowUnit'
                        },
                    'economic':
                        {
                            'native': 'EconomicUnitNative'
                        }
                } # {'node_type_name': 'UnitClassName'}

UNIT_STATE_OPTIONS = {
                        'surface':
                            {
                                'native_cpg': 'SurfaceStateCPGNative',
                                'moose_cpg': 'SurfaceStateCPGNative',
                                'dwsim_cpg': 'SurfaceStateCPGDWSIM',
                                'tespy_cpg': 'SurfaceStateCPGTESPy',
                                'tespy_orc': 'SurfaceStateORCTESPy',
                                'tespy_sf': 'SurfaceStateSingleFlashTESPy',
                                'tespy_df': 'SurfaceStateDoubleFlashTESPy',
                                'native_orc': 'SurfaceStateORCNative'
                            },
                       'injection_well':
                           {
                               'native': 'UnitState',
                               'moose': 'UnitState'
                           },
                       'production_well':
                           {
                               'native': 'ProductionWellStateNative'
                           },
                       'horizontal_well':
                           {
                               'native': 'HorizontalWellStateNative'
                           },
                       'production_well_pump':
                           {
                               'native': 'ProductionWellPumpStateNative'
                           },
                       'reservoir':
                           {
                               'native': 'ReservoirStateNative',
                               'moose': 'UnitState'
                           },
                       'stream':
                           {
                               'native': 'StreamStateNative'
                           },
                       'economic':
                           {
                               'native': 'EconomicStateNative'
                           }
                     } # {'node_type_name': 'UnitStateClassName'}

UNIT_OPTIONS_FOR_ECONUNIT = {
                            'native':
                                {
                                    'surface': ['native_cpg', 'native_dh', 'moose_cpg', 'dwsim_cpg', 'tespy_cpg',  'tespy_orc', 'tespy_sf', 'tespy_df', 'native_orc'],
                                    'injection_well': ['native', 'moose'],
                                    'production_well': ['native'],
                                    'production_well_pump': ['native'],
                                    'horizontal_well': ['native'],
                                    'reservoir': ['native', 'moose']
                                }
                            }


MULTIPLE_UNIT_NODE_OPTIONS = ['horizontal_well']

MAP_FLUIDNAME_TO_SURFACE_DESIGN = {'CO2': 'CPG', 'H2O': 'ORC'}

WELL_PATTERN_OPTIONS = ['DOUBLET', '5SPOT', 'INVERTED_5SPOT', 'AGS']
PROJECT_MATURITY_OPTIONS = ['GREEN_FIELD', 'BROWN_FIELD']
REGRIGERANT_OPTIONS = ['R245fa', 'R600a']
MAP_WELLPATTERN_TO_NUM_WELLS = {'DOUBLET': [1, 1], '5SPOT': [4, 1], 'INVERTED_5SPOT': [1, 4]} # [num_inj, num_prod]

FLUID_NAME_OPTIONS = ['CO2', 'H2O']
# TODO: These options should be checked!
WELL_COST_OPTIONS = ['gengeo', 'halliburton', 'st_gallen', 'bavaria', 'swiss', 'ppgd']
SURFACE_DESIGN_OPTIONS = ['OPEN', 'CLOSED']
COOLING_MODE_OPTIONS = ['WET', 'DRY']
SKIP_REPORT_ATTRIBUTES = ['mass_rate', 'mu', 'rho']
REPORT_SETTINGS = {'surface': [], 'reservoir': 'outlet_fluid', 'injection_well': 'inlet_fluid', 'production_well': 'outlet_fluid'}
MAP_ORC_OPTNAME_TO_TABLE_NAME = {'min_cost': 'minCost', 'max_power': 'maxPower'}
DATETIME_FMT = '%Y-%m-%d'
CONVERGENCE_CRITERIA = {'dP_reservoir': 1000, 'dP_surface': 100, 'dT_surface': 0.5, 'max_num_itr': 20}

#
# ... CMG configs
#

CMG_PATH = {
    'WIN': r"C:\Program Files\CMG",
    'LINUX': 'xxx'
}

CMG_EXE_FLD = {
                   'WIN': "Win_x64",
                   'LINUX': 'xxx'
              }

CMG_EXE = {
                 'imex': "mx{version}.exe",
                 'gem': 'gm{version}.exe'
          }

CMG_CMG_TEMPLATE = '"$program" -f "$inputfilepath" -wd "$wd" -parasol $np'
