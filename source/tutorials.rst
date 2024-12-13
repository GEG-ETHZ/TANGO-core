.. _tango-tutorial:

TANGO Tutorial
===============

Embark on your journey with **TANGO**, a cutting-edge simulation tool tailored for subsurface modeling. This tutorial is designed to guide you step-by-step through configuring and executing a simulation. By leveraging the provided YAML configuration file, you'll gain a comprehensive understanding of TANGO's capabilities and workflows.

Overview
--------

The following steps outline the process of running a simulation with TANGO:

1. Understand the YAML input structure.
2. Modify the input file as needed.
3. Run the simulation using TANGO.
4. Analyze the output.

Input File Structure
--------------------

The YAML file serves as the input for TANGO and defines the simulation graph, physical properties, and scheduling parameters. Below is an explanation of each section in the provided YAML file:

### Graph Definition

The `graph` section defines the nodes (components) and edges (connections) of the simulation. Each node has a `type` and `unit`. For example:

.. code-block:: yaml

   graph:
     nodes:
       inj_1:  # root node
         type: 'injection_well'
         unit: 'native'
       reservoir:
         type: 'reservoir'
         unit: 'native'
       prd_1:
         type: 'production_well'
         unit: 'native'
       surface:
         type: 'surface'
         unit: 'native_CPG'

Edges specify the flow paths:

.. code-block:: yaml

     edges:
       1:
         source: 'surface'
         target: 'inj_1'
       2:
         source: 'inj_1'
         target: 'reservoir'
       3:
         source: 'reservoir'
         target: 'prd_1'
       4:
         source: 'prd_1'
         target: 'surface'

### Simulation Input

The `runspec` section defines the simulation title and workflow:

.. code-block:: yaml

   runspec:
     title: 'CPG DOUBLET'
     workflow: 'native'

The `props` section specifies physical properties of fluids and rocks:

.. code-block:: yaml

   props:
     fluid_name: 'CO2'
     brine_density: 1000 # kg/m3
     rock_density: 2650.0 # kg/m3
     rock_cp: 1000.0  # specific heat capacity (J/(kg*K))
     rock_k: 2.1  # thermal conductivity (W/(m*K))
     thermal_gradient: 0.035  # degC/m

### Surface and Reservoir Parameters

Define surface and reservoir characteristics:

.. code-block:: yaml

   surface:
     surface_temperature: 288.15  # K
     surface_pressure: 100_000  # Pa
     pipe_diameter: 0.41 # m
     approach_temperature: 7.0  # K
     condensation_pressure_offset: 50_000.0  # Pa
     eta_turbine: 0.78  # (-)

   reservoir:
     reservoir_depth: 2500.0 # m
     thickness: 300.0 # m
     permeability: 5.0e-14    # m2 ~50mD
     porosity: 0.1
     hydro_static_pressure: 25000000
     over_pressure_percentage: 20

### Well Parameters

Well parameters for injection and production wells:

.. code-block:: yaml

   injection_well:
     well_length: 2500.0 # m
     diameter: 0.410 # m
     well_length_seq: [2500.0]
     well_diameter_seq: [0.410]

   production_well:
     well_length: 2500.0 # m
     diameter: 0.410 # m
     well_length_seq: [2500.0]
     well_diameter_seq: [0.410]

### Scheduling and Economics

Schedule parameters define the timeline and operational constraints:

.. code-block:: yaml

   schedule:
     bc_iteration_checkpoint: production_well_bottom
     mass_flow_rate: 200.0  # kg/s (injection rate per pattern)
     well_pattern: 'DOUBLET' # doublet, inverted_5spot, 5spot
     well_spacing: 707.0 # m (inj-prod pair)
     well_pattern_dimens: [1,1] # [num_patterns_x_dir, num_patterns_y_dir]
     start_date: '2019-01-01' # Year-mm-dd
     time:
       type: ConstantDT
       num_tsteps: 5 # number of time steps
       dt: 1.0  # time step increment (year)

Economic parameters (optional):

.. code-block:: yaml

   economic:
     type: 'native'
     project_maturity: 'green_field' # brown_field or green_field
     discount_rate: 0.095

Running the Simulation
----------------------

To run the simulation with TANGO, follow these steps:

1. Save the YAML file as `input.yaml` in your working directory.
2. Execute the simulation using the following command:

.. code-block:: bash

   tango run --input input.yaml --output output_directory

3. Monitor the progress in the terminal or the log files generated in the `output_directory`.

Analyzing the Results
---------------------

After the simulation completes, TANGO generates output files containing detailed results. These may include:

- **Flow data**: Fluid and heat flow rates over time.
- **Performance metrics**: Efficiency, pressure drops, and thermal performance.
- **Economic evaluation**: Net present value (NPV) and other economic indicators.

Use the `analyzer-tool` to visualize and interpret these results.

Next Steps
----------

- Modify the YAML file to test different scenarios and configurations.
- Explore advanced features such as custom workflows and API integration.
- Refer to the :doc:`examples` and :doc:`TANGO API <modules>`  for a detailed explanation of all parameters.

For additional help, visit our `Community Support Forum <https://community.yourtango.com>`_ or contact `support@tango.com`.
