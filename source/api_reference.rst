TANGO API Reference
====================

This documentation provides detailed, technical information about the various modules in the TANGO framework. The modules are organized into three sections: Core Modules, Unit Models, and Advanced Modules.

Core Modules
------------

These modules form the core functionality of the TANGO framework.

.. _tango_core_stream:

.. automodule:: tango.core.stream
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_core_unit:

.. automodule:: tango.core.abstracts.unit
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: init_inlet_state, init_state, set_inlet_stream, set_outlet_stream, stream_interface, update_inlet_state, update_outlet_streams

.. _tango_core_workflow:

.. automodule:: tango.core.abstracts.workflow
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _init_econ_unit, _init_system, economic_unit, execute, orchestrator

.. _tango_core_orchestrator:

.. automodule:: tango.core.abstracts.orchestrator
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _build_graph, _graph_check, _init_edges, _init_nodes, _input_check, _is_terminal, _next_nodes, _process_specs, _reset, _set_node_object, _source_nodes, _update_node, execute

.. _tango_core_constants:

.. automodule:: tango.core.constants
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_core_fluidstate:

.. automodule:: tango.core.fluidstate
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_core_runner:

.. automodule:: tango.runner
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _initialize_workflow, start

.. _tango_core_cli:

.. automodule:: tango.tango_cli
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: execute

.. _tango_core_time_stepper:

.. automodule:: tango.time_stepper
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: sample

.. _tango_core_utils:

.. automodule:: tango.utils
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_workflow_native:

.. automodule:: tango.workflows.native_workflow
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: execute

.. _tango_orchestrator_native:

.. automodule:: tango.orchestrators.native
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: balanced, update, update_time_dependent_vars, max_itr_reached, _update_injection_well_inlet_P

.. _tango_orchestrator_external:

.. automodule:: tango.orchestrators.external
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _read_csv_file, update, update_time_dependent_vars

.. .. _tango_core_cmg_system:

.. .. automodule:: tango.orchestrators.cmg
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :exclude-members: _build_graph, _init_edges, _init_nodes, SystemCMG, SystemCMG.stream_interface


Unit Models
-----------

These modules are related to the modeling and simulation of wells, fracing, and associated processes.

.. _tango_units_check_fracing:

.. automodule:: tango.units.check_fracing
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_native_well_base:

.. automodule:: tango.units.native.well.base
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_native_well_horizontal_well:

.. automodule:: tango.units.native.well.horizontal_well
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_native_well_injection_well:

.. automodule:: tango.units.native.well.injection_well
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :inherited-members:
    :show-inheritance:

.. _tango_units_native_well_production_well:

.. automodule:: tango.units.native.well.production_well
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_native_well_production_well_pump:

.. automodule:: tango.units.native.well.production_well_pump
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_native_reservoir:

.. automodule:: tango.units.native.reservoir
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_native_base_surface:

.. automodule:: tango.units.native.surface.base
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_native_CPG_surface:

.. automodule:: tango.units.native.surface.CPG
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _specs_post_processor, get_dP_pump, init_stream_interface, process_stream, update_dP_pump

.. _tango_units_native_ORC_surface:

.. automodule:: tango.units.native.surface.ORC
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _specs_post_processor, get_dP_pump, init_stream_interface, process_stream, update_dP_pump, _update_state_fluid, overwrite_state_pipe

.. _tango_units_native_DH_surface:

.. automodule:: tango.units.native.surface.DH
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: process_stream, init_stream_interface

.. _tango_units_external_dwsim:

.. automodule:: tango.units.external.DWSIM.CPG
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_native_moose_base:

.. automodule:: tango.units.external.MOOSE.base
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _generate_moose_input, _interface_instance, stream_interface

.. _tango_units_native_moose_reservoir:

.. automodule:: tango.units.external.MOOSE.reservoir.reservoir
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _compute_area, _compute_initial_pressure, _compute_initial_temperature, _initialize_mdot_mult, init_stream_interface, process_stream

.. _tango_units_native_moose_well:

.. automodule:: tango.units.external.MOOSE.well.well
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: get_diameter, get_probability_of_success, get_well_length, init_stream_interface, process_stream

.. _tango_units_cmg_base:

.. automodule:: tango.units.cmg.base
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _get_program, _parse_args, stream_interface, inputfilepath, nosim, np, queue, version

.. _tango_units_cmg_coflow:

.. automodule:: tango.units.cmg.coflow
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_cmg_gem:

.. automodule:: tango.units.cmg.gem
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_cmg_imex:

.. automodule:: tango.units.cmg.imex
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. .. _tango_units_native_AGS_surface:

.. .. automodule:: tango.units.native.surface.AGS
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :inherited-members:
    :show-inheritance:

.. _tango_units_native_reader:

.. automodule:: tango.units.native.unit_reader
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_economic:

.. .. automodule:: tango.units.native.economic.economic
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: OPEX_cost_fraction, PPI_table, capacity_factor, cost_multiplier_table, discount_rate, horizontal_well_cost_multiplier, monitoring_well_diameter, monitoring_well_probability_of_success, num_characterization_wells, project_maturity, type, well_cost_model, wellbore_solver, _compatibility_check, _initialize_units, _process_specs, _set_unit_dict

.. _tango_units_permitting_cost:

.. automodule:: tango.units.native.economic.permitting
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_exploration_cost:

.. automodule:: tango.units.native.economic.exploration
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_wells_cost:

.. automodule:: tango.units.native.economic.wells
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_units_surface_cost:

.. automodule:: tango.units.native.economic.surface
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: _compute_surface_pipe_total_length, execute, _compute_heat_exchanger_cost, _compute_recuperator_cost, _execute_CPG, _execute_ORC, _get_pump_material_cost_multiplier, _get_tower_design_coefficient, _get_turbine_cost_multiplier, _initialize_constants


Advanced Modules
----------------

These modules provide advanced functionality, including workflows and orchestrators.

.. .. _tango_models_adams_closed_loop_systems_test:

.. .. automodule:: tango.models.adams.closed_loop_systems_test
    :members:
    :undoc-members:
    :special-members: __init__
    :inherited-members:
    :show-inheritance:

.. .. _tango_orchestrators_cmg:

.. .. automodule:: tango.orchestrators.cmg
    :members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. .. _tango_workflows_cmg_workflow:

.. .. automodule:: tango.workflows.cmg_workflow
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. .. _tango_interface_dwsim:

.. .. automodule:: tango.interfaces.tango_dwsim_interface
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:

.. _tango_interface_moose:

.. automodule:: tango.interfaces.tango_moose_interface
    :members:
    :private-members:
    :undoc-members:
    :special-members: __init__
    :show-inheritance:
    :exclude-members: run
