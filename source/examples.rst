TANGO Examples
==============

Below are practical examples that demonstrate the usage of TANGO.

Example 1: Simulating a Horizontal Well
---------------------------------------

.. code-block:: python

   from tango.units.native.well.horizontal_well import HorizontalWell

   well = HorizontalWell(length=500, diameter=10)
   well.simulate()

Example 2: Injection Well Configuration
---------------------------------------

.. code-block:: python

   from tango.units.native.well.injection_well import InjectionWell

   well = InjectionWell(injection_rate=300, pressure=5000)
   results = well.simulate()
   print(results)

Example 3: Running a CMG Workflow
---------------------------------

.. code-block:: python

   from tango.workflows.cmg_workflow import CMGWorkflow

   workflow = CMGWorkflow(config="config.json")
   workflow.run()

Check out the :doc:`api_reference` for detailed descriptions of the modules used in these examples.
