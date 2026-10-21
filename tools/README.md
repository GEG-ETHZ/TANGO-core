# `tools/`

Repo maintenance scripts. None of them is part of the `tango` package.

| Script | What it does | Run by |
|---|---|---|
| `check_remote_up_to_date.py` | Fails fast when the remote has commits you lack | pre-push hook |
| `hash_tango.py` | Regenerates `src/tango.hash`, the single file DVC stages depend on | pre-commit hook on `src/tango/` |
| `check_full_tests_before_tag_push.py` | Requires `just test --all` before a `vX.Y.Z` tag is pushed | pre-push hook |
| `check_licenses.py` | Generates and checks third-party license compliance (`licenses.json`, `conda_and_pip_package_licenses.csv`) | by hand, before a release |
| `run_tango_profile.py` | Runs one example config, optionally under cProfile (`--profile`) | by hand |
| `readme_assets.py` | Draws the README banner (light and dark) into `docs/assets/` | `just diagrams` |
| `diagrams/` | Draws the editable diagrams in `docs/diagrams/`: `system_key.py`, `hero.py`, `system.py`, `user_experience.py`, `architecture_map.py` print draw.io XML, `build.py` exports them with the `drawio` CLI; `drawio.py`, `system_key.py`, `loop.py` and `parts.py` hold the shared builder, pictogram, loop graphic and the list of models | `just diagrams` |

Hook wiring is in [`.pre-commit-config.yaml`](https://github.com/GEG-ETHZ/TANGO-core/blob/main/.pre-commit-config.yaml).
