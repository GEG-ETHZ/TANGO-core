[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 150
    ny = 100
    xmin = -2500
    xmax = 2500
    ymin = -1300
    ymax = 1300
  []
  [injection_node]
    input = gen
    type = ExtraNodesetGenerator
    new_boundary = injection_node
    coord = '-500 0 0'
  []
[]

[GlobalParams]
  PorousFlowDictator = dictator
  gravity = '0 0 0'
[]

[Variables]
  [porepressure]
    initial_condition = 50E6
  []
  [temperature]
    initial_condition = 423.15
    scaling = 1E-6 # fluid enthalpy is roughly 1E6
  []
[]

 [BCs]
   [temperature]
     type = DirichletBC
     variable = temperature
     value = 423.15
     boundary = 'left right top bottom'
   []
   [pressure]
    type = DirichletBC
    variable = porepressure
    value = 52000000
    boundary = injection_node
  []
 []

[Functions]
  [mass_flux_in_func]
    type = ParsedFunction
    expression = '10'
  []
  [mass_flux_out_func]
    type = ParsedFunction
    expression = '-10'
  []
  [T_in_func]
    type = ParsedFunction
    expression = '313.15'
  []
  [./csv_data]
    type = Moskito2Constant
    data_file = pc.csv
    direction = RIGHT
    format = columns
    execute_on = TIMESTEP_BEGIN
  [../]
  [./csv_datat]
    type = Moskito2Constant
    data_file = tc.csv
    direction = RIGHT_INCLUSIVE
    format = columns
    execute_on = TIMESTEP_BEGIN
  [../]
  [./csv_dataq]
    type = Moskito2Constant
    data_file = qc.csv
    direction = RIGHT_INCLUSIVE
    format = columns
    execute_on = TIMESTEP_BEGIN
  [../]
[]

[Kernels]
  [mass_dot]
    type = PorousFlowMassTimeDerivative
    fluid_component = 0
    variable = porepressure
  []
  [mass_flux]
    type = PorousFlowAdvectiveFlux
    fluid_component = 0
    variable = porepressure
  []
  [energy_dot]
    type = PorousFlowEnergyTimeDerivative
    variable = temperature
  []
  [heat_advection]
    type = PorousFlowHeatAdvection
    variable = temperature
  []
  [heat_conduction]
    type = PorousFlowHeatConduction
    variable = temperature
  []
[]

[Postprocessors]
  [mass_flux_in]
    type = FunctionValuePostprocessor
    function = mass_flux_in_func
    execute_on = 'initial timestep_begin'
  []
  [mass_flux_out]
    type = FunctionValuePostprocessor
    function = mass_flux_out_func
    execute_on = 'initial timestep_begin'
  []
  [T_in]
    type = FunctionValuePostprocessor
    function = T_in_func
    execute_on = 'initial timestep_begin'
  []
  [./temp_pro]
    type = PointValue
    point = '500 0 0'
    variable = 'temperature'
  [../]
    [belphip]
      type = PointValue
      variable = porepressure
      point = '1500 0 0'
      outputs = 'csv'
    []
    [belphit]
      type = PointValue
      variable = temperature
      point = '1500 0 0'
      outputs = 'csv'
    []
[]

[UserObjects]
  [dictator]
    type = PorousFlowDictator
    porous_flow_vars = 'temperature porepressure'
    number_fluid_phases = 1
    number_fluid_components = 1
  []
  [pc]
    type = PorousFlowCapillaryPressureConst
  []
	[injected_mass]
    type = PorousFlowSumQuantity
  []
  [produced_mass]
    type = PorousFlowSumQuantity
  []
  [produced_heat]
    type = PorousFlowSumQuantity
  []
    [produced_mass_H2O1]
    type = PorousFlowSumQuantity
  []

  [produced_heat1]
    type = PorousFlowSumQuantity
  []
[]

[FluidProperties]
  [the_simple_fluid]
    type = SimpleFluidProperties
    thermal_expansion = 7E-4
    bulk_modulus = 2.5E9
    viscosity = 5E-4
    density0 = 1000
    cv = 4000.0
    cp = 4000.0
  []
[]

[Materials]
  [temperature]
    type = PorousFlowTemperature
    temperature = temperature
  []
  [phase]
    type = PorousFlow1PhaseP
    porepressure = porepressure
    capillary_pressure = pc
  []
  [massfrac]
    type = PorousFlowMassFraction
  []
  [water]
    type = PorousFlowSingleComponentFluid
    fp = the_simple_fluid
    phase = 0
  []
  [porosity]
    type=PorousFlowPorosityConst
    porosity = 0.01
  []
  [permeability]
    type = PorousFlowPermeabilityConst
    permeability = '8e-13 0 0  0 8e-13 0  0 0 8e-13'
  []
  [relperm]
    type = PorousFlowRelativePermeabilityCorey
    n = 0
    phase = 0
  []
  [thermal_conductivity]
    type = PorousFlowThermalConductivityIdeal
    dry_thermal_conductivity = '2.5 0 0  0 2.5 0  0 0 2.5'
  []
  [internal_energy]
    type = PorousFlowMatrixInternalEnergy
    specific_heat_capacity = 920
    density = 2600
  []
  [undrained_density]
    type = GenericConstantMaterial
    prop_names = density
    prop_values = 2400
  []
[]

[Preconditioning]
  active = basic
  [basic]
    type = SMP
    full = true
    petsc_options = '-ksp_diagonal_scale -ksp_diagonal_scale_fix'
    petsc_options_iname = '-pc_type -sub_pc_type -sub_pc_factor_shift_type -pc_asm_overlap'
    petsc_options_value = ' asm      lu           NONZERO                   2'
  []
  [preferred_but_might_not_be_installed]
    type = SMP
    full = true
    petsc_options_iname = '-pc_type -pc_factor_mat_solver_package'
    petsc_options_value = ' lu       mumps'
  []
[]

[Executioner]
  type = Transient
  [./TimeStepper]
    type = IterationAdaptiveDT
    dt = 3600
    growth_factor = 1.1
  [../]
  dtmax = 8640000
  end_time = 315360000
  solve_type = NEWTON
[]

[Outputs]
  file_base = pf_out
  exodus = true
  csv = true
[]

[DiracKernels]
  [inject_mass]
    type = PorousFlowPointSourceFromPostprocessor
    variable = porepressure
    mass_flux = mass_flux_in
    point = '-500 0 0'
  []
  [inject_heat]
    type = PorousFlowPointEnthalpySourceFromPostprocessor
    variable = temperature
    mass_flux = mass_flux_in
    point = '-500 0 0'
    T_in = T_in
    pressure = porepressure
    fp = the_simple_fluid
  []

  [produce_H2O_1]
    type = PorousFlowPolyLineSink
    SumQuantityUO = produced_mass_H2O1
    fluxes = 10
    p_or_t_vals = 0.0
    line_length = 1.0
    point_file = /Users/morteza/Documents/projects/moose/modules/porous_flow/1.bh
    variable = porepressure
  []

  [remove_heat_at_production_well_1]
    type = PorousFlowPolyLineSink
    SumQuantityUO = produced_heat1
    fluxes = 10
    p_or_t_vals = 0.0
    line_length = 1.0
    use_enthalpy = true
    point_file = /Users/morteza/Documents/projects/moose/modules/porous_flow/1.bh
    variable = temperature
  []
[]


# [Executioner]
#   type = Transient
#   solve_type = Newton
#   end_time = 900000000
#   # dt = 2E5
#   dt = 2E5
#   nl_abs_tol = 1e-9
# []


# [Postprocessors]
#   [belphip]
#     type = PointValue
#     variable = porepressure
#     point = '1500 0 0'
#     outputs = 'csv'
#   []
#   [belphit]
#     type = PointValue
#     variable = temperature
#     point = '1500 0 0'
#     outputs = 'csv'
#   []
# []

# [Postprocessors]
#   [belphip]
#     type = PointValue
#     variable = porepressure
#     point = '1500 0 0'
#     outputs = 'csv'
#   []
#   [belphit]
#     type = PointValue
#     variable = temperature
#     point = '1500 0 0'
#     outputs = 'csv'
#   []
# []
