# Adding or changing a component

Read the [TANGO commandments](https://github.com/GEG-ETHZ/TANGO-core/blob/main/CONTRIBUTING.md#tango-commandments) first; this file only says where each applies when you touch `components/`.

1. **Subclass the right base.** `WellComponent`, `ReservoirComponent`, `SurfaceComponent` or `EconomicComponent`, each in its subpackage's `base.py`. Implement `solve(self, inlet: Stream)`; it reads `inlet` and writes `self.outlet` and `self.state`, nothing else.
2. **Config fields are pydantic fields** on the class, named as in the YAML (rules *object == config* and *schemas defined in code*). Derived values go in `init()`, which `from_dict` calls. Do not redeclare `common` or the layout-derived keys (`well_spacing`, `well_pattern`, `dt_years`, `target_extraction_pressure`); `Workflow` threads those in.
3. **Mutable values live in a `*State` dataclass** as `LockedState` fields (rule *mutation is guarded*), and every `*State` field has a `list` twin in a `*History` class appended in `record()` (rule *history is recordable*). `tests/unit/test_state_history_parity.py` enforces the pairing. Follow `reservoir/lumped.py` (`LumpedReservoirState`, `LumpedReservoirHistory`).
4. **Register it.** Add `("<type>", "<variant>"): YourClass` to `COMPONENT_REGISTRY` in `registry.py`.
5. **Cover it with a config.** Add or extend a file in `example_configs/` and make sure a regression test runs it (rule *example configs are regression-covered*).
6. **Update the docs** in the same change: the table in `README.md` here and the variants table in `docs/architecture/components.md`.
