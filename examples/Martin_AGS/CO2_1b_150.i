[Mesh]
  type = FileMesh
  file = eavor1_2.msh
[]

[FluidProperties]
  [co2]
    type = CO2FluidProperties
  []
[]

[UserObjects]
  [./eos]
    #type = MoskitoEOS1P_Brine
    type = MoskitoEOS1P_FPModule
    fp = co2
  [../]
  [./viscosity]
    #type = MoskitoViscosityWaterVogel
    type = MoskitoEOS1P_FPVIS
    fp = co2
  [../]
[]

[Materials]
  [./injection_vertical]
    type = MoskitoFluidWell_1p1c
    pressure = p
    temperature = T
    flowrate = q
    well_direction = -z
    well_type = 1
    eos_uo = eos
    viscosity_uo = viscosity
    well_diameter = 0.3
    roughness_type = rough
    roughness = 1e-04
    gravity = '0 0 -9.8'
    block = 'vertical_downward'
    outputs = exodus
  [../]
  [./injection_vertical_lat1]
    type = MoskitoLatHeat_Inc_Formation_1p
    temperature_inner = T
    outer_diameters = '0.3 0.33 0.4'
    conductivities = '43.75 0.7'
    formation_density = 2500
    formation_heat_capacity = 1000
    formation_temperature_function = grad_func
    convective_thermal_resistance = true
    nondimensional_time_function = Hasan_Kabir_2012
    outputs = exodus
    block = 'vertical_downward'
    formation_thermal_conductivity = 2.5
  [../]
  [./injection_horizontal]
    type = MoskitoFluidWell_1p1c
    pressure = p
    temperature = T
    flowrate = q
    well_direction = x
    well_type = 1
    eos_uo = eos
    viscosity_uo = viscosity
    well_diameter = 0.4
    roughness_type = rough
    roughness = 1e-04
    gravity = '0 0 -9.8'
    block = 'Horizontal_down'
    outputs = exodus
  [../]
  [./injection_horizontal_lat]
    type = MoskitoLatHeat_Inc_Formation_1p
    temperature_inner = T
    outer_diameters = '0.4 0.401'
    conductivities = '3.0'
    formation_density = 2500
    formation_heat_capacity = 1000
    formation_temperature_function = grad_func
    convective_thermal_resistance = true
    nondimensional_time_function = Hasan_Kabir_2012
    outputs = exodus
    block = 'Horizontal_down'
    formation_thermal_conductivity = 2.5
  [../]
 [./production_horizontal]
    type = MoskitoFluidWell_1p1c
    pressure = p
    temperature = T
    flowrate = q
    well_direction = -x
    well_type = 1
    eos_uo = eos
    viscosity_uo = viscosity
    well_diameter = 0.4
    roughness_type = rough
    roughness = 1e-04
    gravity = '0 0 -9.8'
    block = 'Horizontal_up'
    outputs = exodus
  [../]
  [./production_horizontal_lat]
    type = MoskitoLatHeat_Inc_Formation_1p
    temperature_inner = T
    outer_diameters = '0.4 0.401'
    conductivities = '3.0'
    formation_density = 2500
    formation_heat_capacity = 1000
    formation_temperature_function = grad_func
    convective_thermal_resistance = true
    nondimensional_time_function = Hasan_Kabir_2012
    outputs = exodus
    block = 'Horizontal_up'
    formation_thermal_conductivity = 2.5
  [../]
[./production_vertical]
    type = MoskitoFluidWell_1p1c
    pressure = p
    temperature = T
    flowrate = q
    well_direction = z
    well_type = 1
    eos_uo = eos
    viscosity_uo = viscosity
    well_diameter = 0.3
    roughness_type = rough
    roughness = 1e-04
    gravity = '0 0 -9.8'
    block = 'vertical_upward'
    outputs = exodus
  [../]
  [./production_vertical_lat1]
    type = MoskitoLatHeat_Inc_Formation_1p
    temperature_inner = T
    outer_diameters = '0.3 0.33 0.4'
    conductivities = '43.75 0.7'
    formation_density = 2500
    formation_heat_capacity = 1000
    formation_temperature_function = grad_func
    convective_thermal_resistance = true
    nondimensional_time_function = Hasan_Kabir_2012
    outputs = exodus
    block = 'vertical_upward'
    formation_thermal_conductivity = 2.5
  [../]
[]

[Functions]
  [./dts]
    type = PiecewiseLinear
    x = '0 10000  315360  31536000 630720000 946080000'
    y = '3600.0 3600.0 86400 9153600 1000000 2592000'
    #x = '0 7200  72000.0 943000  315360000 3153600000'
    #y = '1000 1000.0 1000.0 360000 3600000 3600000'
  [../]
  [./conc]
    type = ParsedFunction
    value = 'if(t>16000 & t<73000, 1.72, 0.25)'
    # value = 0.4
  [../]
  [./grad_func]
    type = ParsedFunction
    value ='288.15 - z * 0.03'
  [../]
  [./conductivity_gradient]
    type = ParsedFunction
    value ='1.5 - z * 0.00075'
  [../]
    [./csv_data]
      type = MoskitoConstant
      data_file = pc150.csv
      direction = RIGHT
      format = columns
      execute_on = TIMESTEP_BEGIN
    [../]
    [./csv_datat]
      type = MoskitoConstant
      data_file = tc150.csv
      direction = RIGHT_INCLUSIVE
      format = columns
      execute_on = TIMESTEP_BEGIN
    [../]
    [./csv_dataq]
      type = MoskitoConstant
      data_file = qc150.csv
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
  [./pleft2]
    type = PostprocessorDirichletBC
    variable = p
    boundary = 'ax1'
    postprocessor = belphip
  [../]
  [./qleft2]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'ax1'
    postprocessor = belphiq
  [../]
  [./tleft2]
    type = PostprocessorDirichletBC
    variable = T
    boundary = 'ax1'
    postprocessor = belphit
  [../]
[]

[Variables]
  [./T]
    [./InitialCondition]
      type = FunctionIC
      function = '283.15 - z * 0.03'
      variable = T
    [../]
  [../]
  [./p]
    [./InitialCondition]
      type = FunctionIC
      function = '10000000 -10000 * z'
      variable = p
    [../]
  [../]
  [./q]
    initial_condition = 0.002
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
  end_time = 946080000
  l_max_its = 100
  solve_type = NEWTON
  steady_state_detection = false
  nl_abs_tol = 1e-5
  [./TimeStepper]
    type = FunctionDT
    function = dts
  [../]
[]

# [Outputs]
#   exodus = true
#   print_linear_residuals = true
# []

[Outputs]
  # execute_on = 'timestep_end'
  file_base = 'CO2_1b_150_out'
  exodus = true
  csv = true
[]

[Postprocessors]
  [belphip]
    type = PointValue
    variable = p
    point = '3300 0 -10000'
    execute_on = 'timestep_begin'
    # outputs = 'csv'
  []
  [belphit]
    type = PointValue
    variable = T
    point = '3300 0 -10000'
    execute_on = 'timestep_begin'
    # outputs = 'csv'
  []
  [belphiq]
    type = PointValue
    variable = q
    point = '3300 0 -10000'
    execute_on = 'timestep_begin'
    # outputs = 'csv'
  []
  [belphippp]
    type = PointValue
    variable = p
    point = '200 0 0'
    outputs = 'csv'
    execute_on = 'timestep_begin'
  []
  [belphittt]
    type = PointValue
    variable = T
    point = '200 0 0'
    outputs = 'csv'
    execute_on = 'timestep_begin'
  []
  [belphiqqq]
    type = PointValue
    variable = q
    point = '200 0 0'
    outputs = 'csv'
    execute_on = 'timestep_begin'
  []
[]
