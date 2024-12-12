Getting Started with TANGO
==========================

This guide will help you set up TANGO and introduce you to its key features.

Installation
------------

To install TANGO, use pip:

.. code-block:: bash

   pip install tango-framework

Dependencies
------------

Ensure you have the following prerequisites installed:
- Python 3.7 or higher
- Required Python libraries (automatically installed with pip)

Basic Usage
-----------

Here’s how you can use TANGO:

1. **Create a Stream:**

   .. code-block:: python

      from tango.core import Stream

      stream = Stream()
      stream.run()

2. **Run a Simulation:**

   .. code-block:: python

      from tango.simulations import run_simulation

      results = run_simulation(config="config.json")

Next Steps
----------

- Explore the :doc:`api_reference` to learn more about the framework.
- Try out the :doc:`examples` for practical implementations.
- Follow the :doc:`tutorials` for a deep dive into TANGO's capabilities.

