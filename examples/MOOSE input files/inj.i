[Mesh]
  type = FileMesh
  file = inj.msh
[]

[UserObjects]
  [./viscosity]
    type = MoskitoViscosityWaterVogel
  [../]
  [./eos]
    type = MoskitoEOS1P_Brine
  [../]
  [./annulus]
    type = MoskitoAnnulus
    density = 1000.0
    viscosity = 0.001
    thermal_expansion = 2.0e-4
    thermal_conductivity = 0.6
    heat_capacity = 4000.0
    emissivity_inner = 0.9
    emissivity_outer = 0.9
    convective_heat_method = Churchill
  [../]
[]

[Materials]
  [./l0_430]
    type = MoskitoFluidWell_1p1c
    pressure = p
    temperature = T
    flowrate = q
    well_direction = -z
    well_type = 1
    eos_uo = eos
    viscosity_uo = viscosity
    well_diameter = 0.1429
    roughness_type = rough
    roughness = 1e-04
    gravity = '0 0 -9.8'
    # block = l0_430
    # outputs = exodus
  [../]
  [./lat-l0_430]
    type = MoskitoLatHeat_Inc_Formation_1p
    temperature_inner = T
    outer_diameters = '0.1429 0.1778 0.2168'
    conductivities = '43.75 0.7'
    formation_density = 2200
    formation_heat_capacity = 850
    formation_temperature_function = grad_func
    convective_thermal_resistance = true
    nondimensional_time_function = Hasan_Kabir_2012
    # outputs = exodus
    # block = l0_430
    formation_thermal_conductivity = 3.8
  [../]
[]

[Functions]
  [./dts]
    type = PiecewiseLinear
    x = '0 10000  315360  31536000 630720000'
    y = '1000.0 1000.0 86400 3153600 1000000'
    #x = '0 7200  72000.0 943000  315360000 3153600000'
    #y = '1000 1000.0 1000.0 360000 3600000 3600000'
  [../]
  [./conc]
    type = ParsedFunction
    expression = 'if(t>16000 & t<73000, 1.72, 0.25)'
    # value = 0.4
  [../]
  [./grad_func]
    type = ParsedFunction
    expression ='300.0 - z * 0.029'
  [../]
  [./conductivity_gradient]
    type = ParsedFunction
    expression ='1.5 - z * 0.00075'
  [../]
   [./csv_data]
    type = MoskitoConstant
    data_file = pc.csv
    direction = RIGHT
    format = columns
    execute_on = TIMESTEP_BEGIN
  [../]
  [./csv_datat]
    type = MoskitoConstant
    data_file = tc.csv
    direction = RIGHT_INCLUSIVE
    format = columns
    execute_on = TIMESTEP_BEGIN
  [../]
  [./csv_dataq]
    type = MoskitoConstant
    data_file = qc.csv
    direction = RIGHT_INCLUSIVE
    format = columns
    execute_on = TIMESTEP_BEGIN
  [../]
[]

[BCs]
  [./pleft]
    type = FunctionDirichletBC
    variable = p
    boundary = inlet
    function = csv_data
  [../]
  [./qleft]
    type = FunctionDirichletBC
    variable = q
    boundary = inlet
    function = csv_dataq
  [../]
  [./tleft]
    type = FunctionDirichletBC
    variable = T
    boundary = inlet
    function = csv_datat
  [../]
[]

[Variables]
  [./T]
    [./InitialCondition]
      type = FunctionIC
      function = '300.0 - z * 0.029'
      variable = T
    [../]
  [../]
  [./p]
    [./InitialCondition]
      type = FunctionIC
      function = '12000000 -10000 * z'
      variable = p
    [../]
  [../]
  [./q]
    initial_condition = 0.026
  [../]
[]

[Kernels]
  [./Tkernel]
    type = MoskitoEnergy_1p1c
    variable = T
    flowrate = q
    pressure = p
    #block = 'right_vertical_up right_vertical_bet right_vertical_down horizontal left_vertical'
    gravity_energy = false
  [../]
  [./Ttkernel]
    type = MoskitoTimeEnergy_1p1c
    variable = T
    flowrate = q
    pressure = p
    #block = 'right_vertical_up right_vertical_bet right_vertical_down horizontal left_vertical'
  [../]
  [./pkernel]
    type = MoskitoMass_1p1c
    variable = p
    flowrate = q
    temperature = T
    #block = 'right_vertical_up right_vertical_bet right_vertical_down horizontal left_vertical'
  [../]
  [./ptkernel]
    type = MoskitoTimeMass_1p1c
    variable = p
    temperature = T
    #block = 'right_vertical_up right_vertical_bet right_vertical_down horizontal left_vertical'
  [../]
  [./qkernel]
    type = MoskitoMomentum_1p1c
    variable = q
    pressure = p
    temperature = T
    #block = 'right_vertical_up right_vertical_bet right_vertical_down horizontal left_vertical'
  [../]
  [./qtkernel]
    type = MoskitoTimeMomentum_1p1c
    variable = q
    pressure = p
    temperature = T
    #block = 'right_vertical_up right_vertical_bet right_vertical_down horizontal left_vertical'
  [../]
  [./heat]
    type = MoskitoLatHeatIncFormation_1p
    variable = T
    #block = 'right_vertical_up right_vertical_bet right_vertical_down horizontal left_vertical'
  [../]
[]

[AuxVariables]
  [./HeatFlux]
      family = MONOMIAL
  [../]
[]


[Preconditioning]
  active = pn1
  [./p1]
    type = SMP
    full = true
    petsc_options_iname = '-pc_type -sub_pc_type -sub_pc_factor_shift_type'
    petsc_options_value = ' bjacobi  ilu          NONZERO                 '
  [../]
  [./pn1]
    type = SMP
    full = true
    petsc_options_iname = '-pc_type -sub_pc_type -sub_pc_factor_shift_type -snes_type -snes_linesearch_type'
    petsc_options_value = ' bjacobi  ilu          NONZERO                   newtonls   basic               '
  [../]
[]

[Executioner]
  type = Transient
  start_time = 0
  end_time = 630720000
  l_max_its = 100
  solve_type = NEWTON
  steady_state_detection = false
  [./TimeStepper]
    type = FunctionDT
    function = dts
  [../]
[]

[Outputs]
  file_base = gg_out
  exodus = true
  csv = true
[]

[Postprocessors]
  [belphip]
    type = PointValue
    variable = p
    point = '0 0 -5000'
    outputs = 'csv'
  []
  [belphit]
    type = PointValue
    variable = T
    point = '0 0 -5000'
    outputs = 'csv'
  []
  [belphiq]
    type = PointValue
    variable = q
    point = '0 0 -5000'
    outputs = 'csv'
  []
[]