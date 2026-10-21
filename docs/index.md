---
hide:
  - navigation
---

# TANGO

**Techno-economic simulation of geothermal energy systems. TANGO couples reservoir, wells and surface plant in one modular simulator, solves them over the project's lifetime and computes the levelized cost of electricity or heat.**

![What will a geothermal project's electricity or heat cost over its life? You describe the parts, TANGO couples them into one system with its four system types, and you get LCOE or LCOH, net power, per-timestep results and the best designs](diagrams/hero.drawio.svg)

To install and run a first simulation, read [Install](guides/install.md) and [Run a simulation](guides/run.md). Developers start at [Architecture](architecture/index.md), [Runtime](runtime/index.md) and the [API reference](reference/index.md); every term is in the [Glossary](guides/glossary.md).

## What TANGO models

![Many simulations around one simulation; inside it the system with its models, system types, connectors to external simulators, and what each part takes in and gives out](diagrams/tango-couples-every-model.drawio.svg)

## How you use TANGO

![How you use TANGO in four steps: pick a model for each part, wire them into a workflow, run once, as a sweep or as an optimization, and read the results](diagrams/user-experience.drawio.svg)

## How the code is organized

![The tango package, the web app, AI assistant and data store that can connect to it, and the libraries and external simulators below it](diagrams/architecture-map.drawio.svg)
