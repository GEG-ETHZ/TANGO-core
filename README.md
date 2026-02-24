# Techno-economic ANalysis of Geoenergy Operations (TANGO)
![Tango Logo](./tango-logo.svg)

## General users

### Installation

If you have not previously done so, install `uv`: https://docs.astral.sh/uv/getting-started/installation/.

### Examples

You can run anything in the `./examples/` folder with, e.g. `uv run tango_cli -f examples/flexible_SF_manual.yml`. A future update will also provide run scripts.

## Developers and Internal Users

Note that these instructions have been verified to work on Euler.

### Installation

If you have not previously done so, install `uv`: https://docs.astral.sh/uv/getting-started/installation/.

### Testing

Run `uv run pytest -v` in the root directory
(i.e. the same directory as this file) to verify everything works. This will
automatically create an environment, install all the dependencies, and run
`pytest` within the environment with developer dependencies installed.

### Branching Strategy
See [CONTRIBUTING](./CONTRIBUTING.md)
