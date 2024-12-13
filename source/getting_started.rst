.. _getting-started:

Getting Started
===============

Welcome to the **TANGO** documentation! This guide will help you get started with setting up and using **TANGO** in your development environment. Whether you are installing via Docker or using `libmamba`, follow the instructions below to ensure a smooth setup process.

Installation
------------

We provide several ways to install **TANGO**. Choose the method that best fits your environment.

### Option 1: Install Using Docker

To use Docker, ensure you have Docker installed on your machine. Pull the official **TANGO** image:

.. code-block:: bash

   docker pull yourdockerhubusername/tango:latest

Run the container with:

.. code-block:: bash

   docker run -it --rm yourdockerhubusername/tango

You can also mount a local directory to the container for persistent storage:

.. code-block:: bash

   docker run -it --rm -v $(pwd):/app yourdockerhubusername/tango

### Option 2: Install via libmamba

**TANGO** can also be installed using `libmamba`. First, ensure `libmamba` is installed on your system. Then, install **TANGO**:

.. code-block:: bash

   mamba install tango

If you require additional dependencies for specific features, use the following command:

.. code-block:: bash

   mamba install tango-feature1 tango-feature2

For example, to install **TANGO** with all optional features:

.. code-block:: bash

   mamba install tango-all

Verify the installation by running:

.. code-block:: bash

   tango --version

Configuration
-------------

After installation, configure **TANGO** by creating a configuration file. By default, **TANGO** looks for a file named `tango.yaml` in the working directory.

Here's an example configuration file:

.. code-block:: yaml

   setting1: value1
   setting2: value2

Alternatively, you can pass configuration options as command-line arguments:

.. code-block:: bash

   tango --setting1 value1 --setting2 value2

Getting Started with Development
--------------------------------

### Step 1: Initialize Your Project

Run the following command to scaffold a new project:

.. code-block:: bash

   tango init my_project

This will create a directory `my_project` with the necessary boilerplate code and configuration.

### Step 2: Run Your First Command

After setting up your project, you can start using **TANGO**. For example:

.. code-block:: bash

   tango run --input inputfile.yml

### Step 3: Explore Advanced Features

Refer to the `features` section to explore advanced functionalities, including:

- Custom plugins
- API integrations
- Monitoring and logging

Troubleshooting
---------------

If you encounter issues during installation or setup, check the following:

1. Ensure your environment meets the prerequisites outlined in the `requirements` section.
2. Review the log files located in the `logs` directory for detailed error messages.
3. Visit the :doc:`faq` for common questions and solutions.

If the issue persists, open a ticket on our `GitHub Issues page <https://github.com/tango/issues>`_.

Next Steps
----------

Now that you've installed and configured **TANGO**, you are ready to:

- Read the :doc:`tutorials` guide for a hands-on tutorial.
- Explore the :doc:`TANGO API <modules>` for detailed API documentation.
- Learn about customization in the `customization` section.

For further assistance, refer to our `Community Support Forum <https://community.tango.com>`_ or contact our support team at `support@tango.com`.
