[Mesh]
  type = FileMesh
  file = eavor6.msh
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
  [./b1]
    type = MoskitoFluidWell_1p1c
    pressure = p
    temperature = T
    flowrate = q
    well_direction = y
    well_type = 1
    eos_uo = eos
    viscosity_uo = viscosity
    well_diameter = 0.4
    roughness_type = rough
    roughness = 1e-04
    gravity = '0 0 -9.8'
    block = 'b1 b3 b7 bu9 bu5'
    outputs = exodus
  [../]
  [./b1_lat]
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
    block = 'b1 b3 b7 bu9 bu5'
    formation_thermal_conductivity = 2.5
  [../]
 [./b2]
    type = MoskitoFluidWell_1p1c
    pressure = p
    temperature = T
    flowrate = q
    well_direction = -y
    well_type = 1
    eos_uo = eos
    viscosity_uo = viscosity
    well_diameter = 0.4
    roughness_type = rough
    roughness = 1e-04
    gravity = '0 0 -9.8'
    block = 'b2 b5 b9 bu7 bu3'
    outputs = exodus
  [../]
  [./b2_lat]
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
    block = 'b2 b5 b9 bu7 bu3'
    formation_thermal_conductivity = 2.5
  [../]
  [./b4]
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
    block = 'b4 b6 b8 b10 b12 b14'
    outputs = exodus
  [../]
  [./b4_lat]
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
    block = 'b4 b6 b8 b10 b12 b14'
    formation_thermal_conductivity = 2.5
  [../] 
  [./bu19]
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
    block = 'bu4 bu6 bu8 bu10 bu12 bu14 bu1 bu2'
    outputs = exodus
  [../]
  [./bu19_lat]
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
    block = 'bu4 bu6 bu8 bu10 bu12 bu14 bu1 bu2'
    formation_thermal_conductivity = 2.5
  [../] 
[]

[Functions]
  [./dts]
    type = PiecewiseLinear
    x = '0 10000  315360  31536000 630720000 946080000'
    y = '3600.0 3600.0 86400 9153600 1000000 2592000'
    # x = '0 864000  '
    # y = '86400.0 86400.0'
    #x = '0 72000  72000.0 943000  315360000 3153600000'
    #y = '10000 1000.0 1000.0 360000 3600000 3600000'
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
      data_file = pc_6b_15.csv
      direction = RIGHT
      format = columns
      execute_on = TIMESTEP_BEGIN
    [../]
    [./csv_datat]
      type = MoskitoConstant
      data_file = tc_6b_15.csv
      direction = RIGHT_INCLUSIVE
      format = columns
      execute_on = TIMESTEP_BEGIN
    [../]
    [./csv_dataq]
      type = MoskitoConstant
      data_file = qc_6b_15.csv
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

  [./pleft1]
    type = PostprocessorDirichletBC
    variable = p
    boundary = 'b1_inlet b2_inlet'
    postprocessor = belphip1
  [../]
  [./qleft1]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'b1_inlet b2_inlet'
    postprocessor = scaled_belphiq1
  [../]
  [./tleft1]
    type = PostprocessorDirichletBC
    variable = T
    boundary = 'b1_inlet b2_inlet'
    postprocessor = belphit1
  [../]

  [./pleft2]
    type = PostprocessorDirichletBC
    variable = p
    boundary = 'b3_inlet b4_inlet b5_inlet b6_inlet'
    postprocessor = belphip2
  [../]
  [./qleft21]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'b4_inlet b6_inlet'
    postprocessor = scaled_belphiq21
  [../]
  [./qleft22]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'b3_inlet b5_inlet'
    postprocessor = scaled_belphiq22
  [../]
  [./tleft2]
    type = PostprocessorDirichletBC
    variable = T
    boundary = 'b3_inlet b4_inlet b5_inlet b6_inlet'
    postprocessor = belphit2
  [../]

  [./pleft3]
    type = PostprocessorDirichletBC
    variable = p
    boundary = 'b7_inlet b8_inlet b9_inlet b10_inlet'
    postprocessor = belphip3
  [../]
  [./qleft31]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'b8_inlet b10_inlet'
    postprocessor = scaled_belphiq31
  [../]
  [./qleft32]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'b7_inlet b9_inlet'
    postprocessor = scaled_belphiq32
  [../]
  [./tleft3]
    type = PostprocessorDirichletBC
    variable = T
    boundary = 'b7_inlet b8_inlet b9_inlet b10_inlet'
    postprocessor = belphit3
  [../]

  [./pleft4]
    type = PostprocessorDirichletBC
    variable = p
    boundary = ' b12_inlet b14_inlet'
    postprocessor = belphip4
  [../]
  [./qleft41]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'b12_inlet b14_inlet'
    postprocessor = scaled_belphiq41
  [../]
  # [./qleft42]
  #   type = PostprocessorDirichletBC
  #   variable = q
  #   boundary = 'b11_inlet b13_inlet'
  #   postprocessor = scaled_belphiq42
  # [../]
  [./tleft4]
    type = PostprocessorDirichletBC
    variable = T
    boundary = ' b12_inlet  b14_inlet'
    postprocessor = belphit4
  [../]

  # [./pleft5]
  #   type = PostprocessorDirichletBC
  #   variable = p
  #   boundary = 'b15_inlet b16_inlet b17_inlet b18_inlet'
  #   postprocessor = belphip5
  # [../]
  # [./qleft51]
  #   type = PostprocessorDirichletBC
  #   variable = q
  #   boundary = 'b16_inlet b18_inlet'
  #   postprocessor = scaled_belphiq51
  # [../]
  # [./qleft52]
  #   type = PostprocessorDirichletBC
  #   variable = q
  #   boundary = 'b15_inlet b17_inlet'
  #   postprocessor = scaled_belphiq52
  # [../]
  # [./tleft5]
  #   type = PostprocessorDirichletBC
  #   variable = T
  #   boundary = 'b15_inlet b16_inlet b17_inlet b18_inlet'
  #   postprocessor = belphit5
  # [../]

  # [./pleft6]
  #   type = PostprocessorDirichletBC
  #   variable = p
  #   boundary = ' b20_inlet  b22_inlet'
  #   postprocessor = belphip6
  # [../]
  # [./qleft61]
  #   type = PostprocessorDirichletBC
  #   variable = q
  #   boundary = 'b20_inlet b22_inlet'
  #   postprocessor = scaled_belphiq61
  # [../]
  # # [./qleft62]
  # #   type = PostprocessorDirichletBC
  # #   variable = q
  # #   boundary = ' '
  # #   postprocessor = scaled_belphiq62
  # # [../]
  # [./tleft6]
  #   type = PostprocessorDirichletBC
  #   variable = T
  #   boundary = ' b20_inlet b22_inlet'
  #   postprocessor = belphit6
  # [../]

  # [./pleft7]
  #   type = PostprocessorDirichletBC
  #   variable = p
  #   boundary = 'bu15_inlet bu17_inlet'
  #   postprocessor = belphip73
  # [../]
  # [./qlefq7]
  #   type = PostprocessorDirichletBC
  #   variable = q
  #   boundary = 'bu15_inlet bu17_inlet'
  #   postprocessor = belphiq73
  # [../]
  # [./tleft7]
  #   type = PostprocessorDirichletBC
  #   variable = T
  #   boundary = 'bu15_inlet bu17_inlet'
  #   postprocessor = belphit73
  # [../]

  # [./pleft8]
  #   type = PostprocessorDirichletBC
  #   variable = p
  #   boundary = 'bu11_inlet bu13_inlet'
  #   postprocessor = belphip83
  # [../]
  # [./qlefq8]
  #   type = PostprocessorDirichletBC
  #   variable = q
  #   boundary = 'bu11_inlet bu13_inlet'
  #   postprocessor = belphiq83
  # [../]
  # [./tleft8]
  #   type = PostprocessorDirichletBC
  #   variable = T
  #   boundary = 'bu11_inlet bu13_inlet'
  #   postprocessor = belphit83
  # [../]

  [./pleft9]
    type = PostprocessorDirichletBC
    variable = p
    boundary = 'bu7_inlet bu9_inlet'
    postprocessor = belphip93
  [../]
  [./qlefq9]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'bu7_inlet bu9_inlet'
    postprocessor = belphiq93
  [../]
  [./tleft9]
    type = PostprocessorDirichletBC
    variable = T
    boundary = 'bu7_inlet bu9_inlet'
    postprocessor = belphit93
  [../]

  [./pleft10]
    type = PostprocessorDirichletBC
    variable = p
    boundary = 'bu3_inlet bu5_inlet'
    postprocessor = belphip103
  [../]
  [./qlefq10]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'bu3_inlet bu5_inlet'
    postprocessor = belphiq103
  [../]
  [./tleft10]
    type = PostprocessorDirichletBC
    variable = T
    boundary = 'bu3_inlet bu5_inlet'
    postprocessor = belphit103
  [../]

  [./pleft11]
    type = PostprocessorDirichletBC
    variable = p
    boundary = 'bu1_inlet bu2_inlet'
    postprocessor = belphip113
  [../]
  [./qlefq11]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'bu1_inlet bu2_inlet'
    postprocessor = belphiq113
  [../]
  [./tleft11]
    type = PostprocessorDirichletBC
    variable = T
    boundary = 'bu1_inlet bu2_inlet'
    postprocessor = belphit113
  [../]

  [./pleft12]
    type = PostprocessorDirichletBC
    variable = p
    boundary = 'return_inlet'
    postprocessor = belphip123
  [../]
  [./qlefq12]
    type = PostprocessorDirichletBC
    variable = q
    boundary = 'return_inlet'
    postprocessor = scaled_belphiq123
  [../]
  [./tleft12]
    type = PostprocessorDirichletBC
    variable = T
    boundary = 'return_inlet'
    postprocessor = belphit123
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
    initial_condition = 0.02
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
  [./rho]
    family = MONOMIAL
    order = FIRST
    initial_condition = 700.0
    outputs = exodus
  [../]
[]

[AuxKernels]
  [./rho_variable]
    type = MaterialRealAux
    property = density
    variable = rho
    # boundary = b8_inlet 
    # execute_on = timestep_end
    execute_on = timestep_begin
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
  # l_max_its = 10
  nl_max_its = 100
  solve_type = NEWTON
  # nl_abs_tol = 1e-2
  steady_state_detection = false
  
  [./TimeStepper]
    type = FunctionDT
    function = dts
    # cutback_factor_at_failure = 2
  [../]
[]


# [Outputs]
#   exodus = true
#   print_linear_residuals = true
# []

[Outputs]
  # execute_on = 'timestep_end'
  file_base = 'CO2_6b_15_out'
  exodus = true
  csv = true
  print_linear_residuals = false
[]

[Postprocessors]
  [belphip1]
    type = PointValue
    variable = p
    point = '400 0 -5000'
    execute_on = 'timestep_begin'
    outputs = 'csv'
  []
  [belphit1]
    type = PointValue
    variable = T
    point = '400 0 -5000'
    execute_on = 'timestep_begin'
    outputs = 'csv'
  []
  [belphiq1]
    type = PointValue
    variable = q
    point = '400 0 -5000'
    execute_on = 'timestep_begin'
    outputs = 'csv'
  []
  [./scaled_belphiq1]
    type = ScalePostprocessor
    value = belphiq1
    scaling_factor = 0.5
    execute_on = 'timestep_begin'
    outputs = 'csv'
  [../]


  [belphip2]
    type = PointValue
    variable = p
    point = '550 150 -5000'
    execute_on = 'timestep_begin'
    outputs = 'csv'
  []
  [belphit2]
    type = PointValue
    variable = T
    point = '550 150 -5000'
    execute_on = 'timestep_begin'
    outputs = 'csv'
  []
  [belphiq2]
    type = PointValue
    variable = q
    point = '550 150 -5000'
    execute_on = 'timestep_begin'
    outputs = 'csv'
  []
  [./scaled_belphiq21]
    type = ScalePostprocessor
    value = belphiq2
    scaling_factor = 0.3333333333333333
    execute_on = 'timestep_begin'
    # outputs = 'csv'
    # execute_on = 'initial timestep_end'
[../]
[./scaled_belphiq22]
  type = ScalePostprocessor
  value = belphiq2
  scaling_factor = 0.6666666666666666
  outputs = 'csv'
  # execute_on = 'initial timestep_end'
  execute_on = 'timestep_begin'
[../]

[belphip3]
  type = PointValue
  variable = p
  point = '550 350 -5000'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphit3]
  type = PointValue
  variable = T
  point = '550 350 -5000'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphiq3]
  type = PointValue
  variable = q
  point = '550 350 -5000'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[./scaled_belphiq31]
  type = ScalePostprocessor
  value = belphiq3
  scaling_factor = 0.50
  # outputs = 'csv'
  # execute_on = 'initial timestep_end'
  execute_on = 'timestep_begin'
[../]
[./scaled_belphiq32]
type = ScalePostprocessor
value = belphiq3
scaling_factor = 0.50
outputs = 'csv'
# execute_on = 'initial timestep_end'
execute_on = 'timestep_begin'
[../]

[belphip4]
  type = PointValue
  variable = p
  point = '550 550 -5000'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphit4]
  type = PointValue
  variable = T
  point = '550 550 -5000'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphiq4]
  type = PointValue
  variable = q
  point = '550 550 -5000'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[./scaled_belphiq41]
  type = ScalePostprocessor
  value = belphiq4
  scaling_factor = 1.0
  # outputs = 'csv'
  execute_on = 'timestep_begin'
[../]
[./scaled_belphiq42]
type = ScalePostprocessor
value = belphiq4
scaling_factor = 1.0
outputs = 'csv'
# execute_on = 'initial timestep_end'
execute_on = 'timestep_begin'
[../]

# [belphip5]
#   type = PointValue
#   variable = p
#   point = '550 750 -5000'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphit5]
#   type = PointValue
#   variable = T
#   point = '550 750 -5000'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphiq5]
#   type = PointValue
#   variable = q
#   point = '550 750 -5000'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [./scaled_belphiq51]
#   type = ScalePostprocessor
#   value = belphiq5
#   scaling_factor = 0.3333333333333333
#   # outputs = 'csv'
#   # execute_on = 'initial timestep_end'
#   execute_on = 'timestep_begin'
# [../]
# [./scaled_belphiq52]
# type = ScalePostprocessor
# value = belphiq5
# scaling_factor = 0.6666666666666666
# outputs = 'csv'
# # execute_on = 'initial timestep_end'
# execute_on = 'timestep_begin'
# [../]

# [belphip6]
#   type = PointValue
#   variable = p
#   point = '550 950 -5000'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphit6]
#   type = PointValue
#   variable = T
#   point = '550 950 -5000'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphiq6]
#   type = PointValue
#   variable = q
#   point = '550 950 -5000'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [./scaled_belphiq61]
#   type = ScalePostprocessor
#   value = belphiq6
#   scaling_factor = 0.50
#   # outputs = 'csv'
#   # execute_on = 'initial timestep_end'
#   execute_on = 'timestep_begin'
# [../]
# [./scaled_belphiq62]
# type = ScalePostprocessor
# value = belphiq6
# scaling_factor = 0.50
# outputs = 'csv'
# # execute_on = 'initial timestep_end'
# execute_on = 'timestep_begin'
# [../]

# [belphip71]
#   type = PointValue
#   variable = p
#   point = '550 960 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphit71]
#   type = PointValue
#   variable = T
#   point = '550 960 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphiq71]
#   type = PointValue
#   variable = q
#   point = '550 960 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphir71]
#   type = PointValue
#   variable = rho
#   point = '550 960 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []

# [belphip72]
#   type = PointValue
#   variable = p
#   point = '550 950 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphit72]
#   type = PointValue
#   variable = T
#   point = '550 950 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphiq72]
#   type = PointValue
#   variable = q
#   point = '550 950 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphir72]
#   type = PointValue
#   variable = rho
#   point = '550 950 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []

# [belphiq73]
#     type = ParsedPostprocessor
#     function = 'belphiq72'
#     pp_names = 'belphiq72'
#     execute_on = 'timestep_begin'
#     # constant_names = 'mu'
#     # constant_expressions = '4'
# []
# [belphip73]
#   type = ParsedPostprocessor
#   function = 'max(0, belphip72)'
#   pp_names = ' belphip72'
#   execute_on = 'timestep_begin'
#   # constant_names = 'mu'
#   # constant_expressions = '4'
# []
# [belphit73]
#   type = ParsedPostprocessor
#   function = '(belphiq72*belphir72*belphit72)/(belphir72*belphiq72)'
#   pp_names = ' belphip72 belphiq72 belphir72 belphit72'
#   execute_on = 'timestep_begin'
#   # constant_names = 'mu'
#   # constant_expressions = '4'
# []

# [belphip81]
#   type = PointValue
#   variable = p
#   point = '550 760 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphit81]
#   type = PointValue
#   variable = T
#   point = '550 760 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphiq81]
#   type = PointValue
#   variable = q
#   point = '550 760 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphir81]
#   type = PointValue
#   variable = rho
#   point = '550 760 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []

# [belphip82]
#   type = PointValue
#   variable = p
#   point = '550 750 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphit82]
#   type = PointValue
#   variable = T
#   point = '550 750 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphiq82]
#   type = PointValue
#   variable = q
#   point = '550 750 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphir82]
#   type = PointValue
#   variable = rho
#   point = '550 750 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []

# [belphiq83]
#   type = ParsedPostprocessor
#   function = ' belphiq82'
#   pp_names = ' belphiq82'
#   execute_on = 'timestep_begin'
#   # constant_names = 'mu'
#   # constant_expressions = '4'
# []
# [belphip83]
#   type = ParsedPostprocessor
#   function = 'max(0, belphip82)'
#   pp_names = ' belphip82'
#   execute_on = 'timestep_begin'
#   # constant_names = 'mu'
#   # constant_expressions = '4'
# []
# [belphit83]
#   type = ParsedPostprocessor
#   function = '(belphiq82*belphir82*belphit82)/( belphir82*belphiq82)'
#   pp_names = ' belphip82 belphiq82 belphir82 belphit82'
#   execute_on = 'timestep_begin'
#   # constant_names = 'mu'
#   # constant_expressions = '4'
# []

# [belphip91]
#   type = PointValue
#   variable = p
#   point = '550 560 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphit91]
#   type = PointValue
#   variable = T
#   point = '550 560 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphiq91]
#   type = PointValue
#   variable = q
#   point = '550 560 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []
# [belphir91]
#   type = PointValue
#   variable = rho
#   point = '550 560 -4800'
#   execute_on = 'timestep_begin'
#   outputs = 'csv'
# []

[belphip92]
  type = PointValue
  variable = p
  point = '550 550 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphit92]
  type = PointValue
  variable = T
  point = '550 550 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphiq92]
  type = PointValue
  variable = q
  point = '550 550 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphir92]
  type = PointValue
  variable = rho
  point = '550 550 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]

[belphiq93]
  type = ParsedPostprocessor
  function = ' belphiq92'
  pp_names = ' belphiq92'
  execute_on = 'timestep_begin'
  # constant_names = 'mu'
  # constant_expressions = '4'
[]
[belphip93]
  type = ParsedPostprocessor
  function = 'max(0, belphip92)'
  pp_names = ' belphip92'
  execute_on = 'timestep_begin'
  # constant_names = 'mu'
  # constant_expressions = '4'
[]
[belphit93]
  type = ParsedPostprocessor
  function = '( belphiq92*belphir92*belphit92)/( belphir92*belphiq92)'
  pp_names = ' belphip92 belphiq92 belphir92 belphit92'
  execute_on = 'timestep_begin'
  # constant_names = 'mu'
  # constant_expressions = '4'
[]

[belphip101]
  type = PointValue
  variable = p
  point = '550 360 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphit101]
  type = PointValue
  variable = T
  point = '550 360 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphiq101]
  type = PointValue
  variable = q
  point = '550 360 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphir101]
  type = PointValue
  variable = rho
  point = '550 360 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]

[belphip102]
  type = PointValue
  variable = p
  point = '550 350 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphit102]
  type = PointValue
  variable = T
  point = '550 350 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphiq102]
  type = PointValue
  variable = q
  point = '550 350 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphir102]
  type = PointValue
  variable = rho
  point = '550 350 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]

[belphiq103]
  type = ParsedPostprocessor
  function = 'belphiq101 + belphiq102'
  pp_names = 'belphiq101 belphiq102'
  execute_on = 'timestep_begin'
  # constant_names = 'mu'
  # constant_expressions = '4'
[]
[belphip103]
  type = ParsedPostprocessor
  function = 'max(belphip101, belphip102)'
  pp_names = 'belphip101 belphip102'
  execute_on = 'timestep_begin'
  # constant_names = 'mu'
  # constant_expressions = '4'
[]
[belphit103]
  type = ParsedPostprocessor
  function = '(belphiq101*belphir101*belphit101 + belphiq102*belphir102*belphit102)/(belphir101*belphiq101 + belphir102*belphiq102)'
  pp_names = 'belphip101 belphiq101 belphir101 belphit101 belphip102 belphiq102 belphir102 belphit102'
  execute_on = 'timestep_begin'
  # constant_names = 'mu'
  # constant_expressions = '4'
[]


[belphip111]
  type = PointValue
  variable = p
  point = '550 160 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphit111]
  type = PointValue
  variable = T
  point = '550 160 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphiq111]
  type = PointValue
  variable = q
  point = '550 160 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphir111]
  type = PointValue
  variable = rho
  point = '550 160 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]

[belphip112]
  type = PointValue
  variable = p
  point = '550 150 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphit112]
  type = PointValue
  variable = T
  point = '550 150 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphiq112]
  type = PointValue
  variable = q
  point = '550 150 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphir112]
  type = PointValue
  variable = rho
  point = '550 150 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]

[belphiq113]
  type = ParsedPostprocessor
  function = 'belphiq111 + belphiq112'
  pp_names = 'belphiq111 belphiq112'
  execute_on = 'timestep_begin'
  # constant_names = 'mu'
  # constant_expressions = '4'
[]
[belphip113]
  type = ParsedPostprocessor
  function = 'max(belphip111, belphip112)'
  pp_names = 'belphip111 belphip112'
  execute_on = 'timestep_begin'
  # constant_names = 'mu'
  # constant_expressions = '4'
[]
[belphit113]
  type = ParsedPostprocessor
  function = '(belphiq111*belphir111*belphit111 + belphiq112*belphir112*belphit112)/(belphir111*belphiq111 + belphir112*belphiq112)'
  pp_names = 'belphip111 belphiq111 belphir111 belphit111 belphip112 belphiq112 belphir112 belphit112'
  execute_on = 'timestep_begin'
  # constant_names = 'mu'
  # constant_expressions = '4'
[]

[belphip123]
  type = PointValue
  variable = p
  point = '400 0 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphit123]
  type = PointValue
  variable = T
  point = '400 0 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[belphiq123]
  type = PointValue
  variable = q
  point = '400 0 -4800'
  execute_on = 'timestep_begin'
  outputs = 'csv'
[]
[./scaled_belphiq123]
  type = ScalePostprocessor
  value = belphiq123
  scaling_factor = 2.0
  execute_on = 'timestep_begin'
  outputs = 'csv'
[../]




  # [belphir4600]
  #   type = PointValue
  #   variable = rho
  #   point = '0 0 -4600'
  #   execute_on = 'timestep_begin'
  #   # outputs = 'csv'
  # []
  # [belphir3100]
  #   type = PointValue
  #   variable = rho
  #   point = '0 0 -100'
  #   execute_on = 'timestep_begin'
  #   # outputs = 'csv'
  # []
  # [belphiq4600]
  #   type = PointValue
  #   variable = q
  #   point = '0 0 -4600'
  #   execute_on = 'timestep_begin'
  #   # outputs = 'csv'
  # []
  # [belphiq3100]
  #   type = PointValue
  #   variable = q
  #   point = '0 0 -100'
  #   execute_on = 'timestep_begin'
  #   # outputs = 'csv'
  # []
  # [mass_rate_pp4600]
  #   type = ParsedPostprocessor
  #   function = 'belphir4600 * belphiq4600'
  #   pp_names = 'belphir4600 belphiq4600'
  #   # function = 'L2_norm + 3*L1_norm + mu'
  #   # pp_names = 'L2_norm L1_norm'
  #   # constant_names = 'mu'
  #   # constant_expressions = '4'
  # []
  # [mass_rate_pp3100]
  #   type = ParsedPostprocessor
  #   function = 'belphir3100 * belphiq3100'
  #   pp_names =  'belphir3100 belphiq3100'
  #   # function = 'L2_norm + 3*L1_norm + mu'
  #   # pp_names = 'L2_norm L1_norm'
  #   # constant_names = 'mu'
  #   # constant_expressions = '4'
  # []
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
