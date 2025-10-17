[Mesh]
  type = FileMesh
  file = inj.msh
[]

[UserObjects]
  [./viscosity]
    type = MoskitoViscosityWaterSmith
  [../]
  [./eos]
    type = MoskitoEOS1P_Brine
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
    well_diameter = 0.244475
    roughness_type = rough
    roughness = 1e-04
    gravity = '0 0 -9.8'
    # block = l0_430
    # outputs = exodus
  [../]
  [./lat-5000-4950]
    type = MoskitoLatHeat_Inc_Formation_1p
    temperature_inner = T
    outer_diameters = '0.244475 0.274475 0.346075 0.376075 0.473075 0.503075 0.5588'
    conductivities = '43.75 0.7 43.75 0.7 43.75 0.7'
    formation_density = 2500
    formation_heat_capacity = 1000
    formation_temperature_function = grad_func
    convective_thermal_resistance = true
    nondimensional_time_function = Hasan_Kabir_2012
    # outputs = exodus
    block = '5000_4950'
    formation_thermal_conductivity = 2.8
  [../]
  [./lat-4950-3000]
    type = MoskitoLatHeat_Inc_Formation_1p
    temperature_inner = T
    outer_diameters = '0.244475 0.274475 0.346075 0.376075 0.4318'
    conductivities = '43.75 0.7 43.75 0.7'
    formation_density = 2500
    formation_heat_capacity = 1000
    formation_temperature_function = grad_func
    convective_thermal_resistance = true
    nondimensional_time_function = Hasan_Kabir_2012
    # outputs = exodus
    block = '4950_3000'
    formation_thermal_conductivity = 2.8
  [../]
  [./lat-3000-200]
    type = MoskitoLatHeat_Inc_Formation_1p
    temperature_inner = T
    outer_diameters = '0.244475 0.274475 0.31115'
    conductivities = '43.75 0.7'
    formation_density = 2500
    formation_heat_capacity = 1000
    formation_temperature_function = grad_func
    convective_thermal_resistance = true
    nondimensional_time_function = Hasan_Kabir_2012
    # outputs = exodus
    block = '3000_200'
    formation_thermal_conductivity = 2.8
  [../]
  [./lat-200-0]
    type = MoskitoLatHeat_Inc_Formation_1p
    temperature_inner = T
    outer_diameters = '0.244475 0.245475'
    conductivities = '2.8'
    formation_density = 2500
    formation_heat_capacity = 1000
    formation_temperature_function = grad_func
    convective_thermal_resistance = true
    nondimensional_time_function = Hasan_Kabir_2012
    # outputs = exodus
    block = '200_0'
    formation_thermal_conductivity = 2.8
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
    expression ='283.15 - (z-5000) * 0.03'
  [../]
  [./conductivity_gradient]
    type = ParsedFunction
    expression ='1.5 - (z-5000) * 0.00075'
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
    function = '0.01'
  [../]
  [./tleft]
    type = FunctionDirichletBC
    variable = T
    boundary = inlet
    function = csv_datat
  [../]
  # [./tleft]
  #   type = DirichletBC
  #   variable = T
  #   boundary = inlet
  #   value = 320.0
  # [../]
  #   [./pleft]
  #     type = DirichletBC
  #     variable = p
  #     boundary = inlet
  #     value = 3000000
  #   [../]
  #     [./qleft]
  #       type = DirichletBC
  #       variable = q
  #       boundary = inlet
  #       value = 0.01
  #     [../]
[]

[Variables]
  [./T]
    [./InitialCondition]
      type = FunctionIC
      function = '283.15 - (z-5000) * 0.03'
      variable = T
    [../]
  [../]
  [./p]
    [./InitialCondition]
      type = FunctionIC
      function = '21000000 -10000 * (z-5000)'
      variable = p
    [../]
  [../]
  [./q]
    initial_condition = 0.008
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

[Postprocessors]
  [./P_value]
    type = PointValue
    variable = p
    point = '-500 0 0'
  [../]
  [./T_value]
    type = PointValue
    variable = T
    point = '-500 0 0'
  [../]
  [./Q_value]
    type = PointValue
    variable = p
    point = '-500 0 0'
  [../]
[]

[Executioner]
  type = Transient
  start_time = 0
  end_time = 1576800
  l_max_its = 100
  nl_abs_tol = 1e-6
  solve_type = NEWTON
  steady_state_detection = false
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
  file_base = injection_out
  exodus = true
[]

[MultiApps]
  [./coupled]
    positions = '-500 0 0'
    type = TransientMultiApp
    # input_files = /Users/morteza/Documents/projects/moskito2/peace2.i
    input_files = /Users/morteza/Documents/projects/moskito2/pf.i
    app_type = PorousFlowApp
    execute_on = TIMESTEP_END
    library_path = /Users/morteza/Documents/projects/moose/modules/porous_flow/lib
    sub_cycling = true
  [../]
[]

[Transfers]
  [P_transfer]
    type = MultiAppPostprocessorTransfer
    to_multi_app = coupled
    from_postprocessor = P_value
    to_postprocessor = P_receiver2
  []
  [T_transfer]
    type = MultiAppPostprocessorTransfer
    to_multi_app = coupled
    from_postprocessor = T_value
    to_postprocessor = T_receiver2
  []
  [Q_transfer]
    type = MultiAppPostprocessorTransfer
    to_multi_app = coupled
    from_postprocessor = Q_value
    to_postprocessor = Q_receiver2
  []
[]
