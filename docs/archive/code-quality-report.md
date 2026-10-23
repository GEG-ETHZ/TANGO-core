# Code Quality Report

**Repo:** `tango-core-standalone`
**HEAD at time of report:** `629eb6b8d87df0f183c1fa30690e32c9f4066be3` (2026-06-08 12:48:54 +0000) — "Merge branch 'chore/template-sync-2026-06-01' into 'main'"

## Original prompt

> There are 4 main contributors to this repo:
> - chad baker (sometimes cbaker)
> - mortezaep (assume anything with morteza in the name is the same guy)
> - Allan Leal
> - Tsubasa Onishi
>
> I would be interested to have you got through the git history to make a report of who did what in terms of code quality, focusing on:
> - introducing sketchy use of `eval`, in some cases to mask equally sketchy circular imports
> - using hard coded unit conversions instead of stuff in src/tango/core/constants.py
> - using incorrect or no type hints
> - any other bad coding practices
>
> Rate everyone on a 0-10 scale, where 0 is really bad coding and 10 is excellent coding. Take your time.

Follow-up request: dump the report here with the prompt and HEAD commit at the top, and add a section comparing this repo's Chad Baker findings against his subsequent, largely-solo work in the sibling repo `tango-core` (which `tango-core-standalone` forked from at the HEAD commit above).

Methodology: parallel git-blame-attributed audits across four dimensions (sketchy `eval`/circular-import workarounds, hardcoded unit conversions vs. `constants.py`, type-hint coverage/correctness, and general bad practices), sampled broadly across `src/tango/` and cross-referenced with commit history. Only the four requested people are scored; other contributors (Anton Kulik, pwhuang, dmcswe, Nicolás Rangel, etc.) are excluded even where their code intersects.

---

## 1. `eval`/`exec` and circular-import masking

**Tsubasa Onishi** originated the pattern (2023): `eval(f"SurfaceModelAdams{...}")` in `workflow.py`, built on `from tango.models.adams import *` wildcard imports acting as a substitute for a real class registry — including at least one case where the eval'd string is built directly from user-supplied workflow-dict values. This is exactly the "eval masking circular imports" pattern flagged in the prompt, and it's the origin of the lineage that propagated into `runner.py`/`utils.py`/`native_workflow.py`.

**Morteza** is responsible for the worst *currently-surviving* instances: `optimizerr.py:232` `exec(f"{param_path} = {value}")` with no sandboxing, plus three unrestricted `eval()` calls in the same file resolving config-derived parameter paths, and a somewhat-safer namespace-restricted `eval()` in `function_evaluator.py`. He also added an `importlib.import_module()` auto-discovery pattern for addons — same "avoid explicit coupling" motive, not eval, but same smell. Notably, `function_evaluator.py` also contains a genuinely well-built AST-walking safe expression evaluator alongside the raw `eval` calls — so he knows the right pattern and didn't apply it consistently.

**Chad Baker** is the one who progressively eliminated essentially all of this over 2025–2026, with commit messages explicitly naming the security risk ("eval allows users to execute arbitrary code... e.g. to delete all of the ~/ directory") and replacing dynamic dispatch with explicit imports/registries "to enable static type checking (mypy), IDE navigation, easier refactoring." This is a real, well-documented cleanup effort.

**Allan Leal** — no occurrences found.

---

## 2. Hardcoded unit conversions vs. `constants.py`

Widespread problem, concentrated overwhelmingly in **Morteza's** code: `utils.py`, `surface.py`, `economic.py`, `ORC.py`, `flexible_pp.py`, and the entire `ThermaGraph` addon repeatedly hardcode `* 1e5`, `* 1e3`, `+273.15`, `/8760`, `/31536000.0` etc. instead of importing `BAR_TO_PA`, `C_TO_K`, `YEAR_TO_HOUR`, `SECOND_TO_YEAR`. Several files (`surface.py`, `economic.py`'s `exploration.py`) never import `constants.py` at all despite dozens of conversions. Worst single case: `economic.py:631` hardcodes `/1000 * 8760` two lines above a correct `W_TO_KW * YEAR_TO_HOUR` usage in the same function — proof the constant was known and available at write time.

**Chad Baker**, while doing the large `8b828ae2` refactor pass, added *new* hardcoded conversions in files that already `import` the relevant constant (`flexible_pp.py:871` imports `PA_TO_BAR` but uses `/100_000.0`; `BC_calculator.py:340` imports `W_TO_MW` but uses `/1000000.0`) — a more damning pattern than Morteza's, since the constant was sitting right there in the same file's import line. Also found one likely real bug (not just style): `arangodb_manager.py` mixes `/1000000.0` (Pa→MPa) and `/10` (bar→MPa) for values both labeled `"pressure_mpa"` — worth a correctness look independent of this audit.

**Tsubasa Onishi** — only legacy pre-`constants.py` code (2023, superseded by later rewrites); not a fair charge against current practice.

**Allan Leal** — none found.

---

## 3. Type hints

| Author | Sampled | Fully hinted | Partial | None | Incorrect |
|---|---|---|---|---|---|
| Morteza | ~45 | ~10 | ~20 | ~12 | ~4-5 |
| Chad Baker | ~35 | ~22 | ~6 | ~3 | ~4 |
| Tsubasa Onishi | ~30 | ~11 | ~14 | ~3 | ~2 |
| Allan Leal | 4 (full sample) | 0 | 4 | 0 | 0 |

Project has a `[tool.mypy]` config but **no CI enforcement**, so it's aspirational only.

- **Morteza**: whole files with zero annotations (`function_evaluator.py`, most of `optimizerr.py`), plus the recurring `X: str = None` mistake (should be `str | None = None`) across `ORC.py`, `CPG.py`, `cmg/base.py`.
- **Chad Baker**: the *best* hinted code in the repo dates to his later work (`utils.py`'s parameter-handling functions, precise `dict[str, Any]`/`tuple[...]` generics) — but also one clearly wrong signature (`wells.py:202`, `d: list = 0.0`, type says list, default is float) that survived a "ruff cleanup" commit untouched, plus a couple of lazy `-> object` returns.
- **Tsubasa Onishi**: mostly partial (era-appropriate for 2023), including `merge_object_dict(obj, dict)` which shadows the builtin `dict` as a parameter name.
- **Allan Leal**: tiny footprint, foundational `fluidstate.py` — consistently typed params, just missing `-> None` on setters. Clean but a very small sample.

---

## 4. Other bad practices

- **Wildcard imports (`from x import *`)** — systemic, ~17 occurrences. Originated by **Tsubasa Onishi** (CMG unit modules, `AGS.py`), continued by **Chad Baker** (`MOOSE/base.py`, `orchestrators/cmg.py`, `DWSIM/CPG.py`). The ruff config explicitly ignores `F403/F405` rather than fixing this.
- **Bare `except:`** swallowing errors — found in code by all three: **Morteza** (`unit.py`, `surface/base.py`, `utils.py:1028`, no logging), **Tsubasa** (`utils.py:965` discards traceback with no `from err`; `economic.py:539` silent `continue`), **Chad Baker** (`arangodb_manager.py:734`).
- **Extremely long/deeply-nested function**: `BC_calculator.py`'s `iterator()` — ~440 lines, 10+ levels of nesting, a pile of unexplained magic numbers (`200`, `0.0001`, `0.5`, `1.5`, a *different* `10` iteration cap elsewhere in the same function) — all **Morteza**.
- **Print statements in library code instead of logging**: heavily **Morteza** (`optimizerr.py`, `utils.py` debug dumps, `license_check.py`).
- **Duplicated table-generation logic** triplicated across `native_workflow.py` (twice, **Chad Baker**) and `flexible_pp.py` (**Morteza**) instead of one shared helper.
- **Assert used for real runtime validation** (stripped under `-O`): `core/errors.py:283-285`, **Chad Baker**.
- **Dead code**: 0-byte `tests/regtest/test_cmg.py` left by **Tsubasa Onishi**, never cleaned up by anyone since.
- Notable *good* practices: **Chad Baker**'s exception hierarchy (`core/errors.py`) and disciplined dataclass usage (`units/dataclasses.py`); **Tsubasa Onishi**'s centralized `core/config.py` constants; consistent `raise ... from err` chaining in some of **Morteza**'s code.

---

## Scorecard

| Author | Score | Rationale |
|---|---|---|
| **Chad Baker** | **7/10** | Clearly the strongest and most self-aware contributor — actively fixed the eval/wildcard-import/circular-import mess left by others, writes the best-typed and best-structured code in the repo (dataclasses, exception hierarchy, transparent ruff-ignore documentation). Docked for self-inflicted inconsistencies during his own cleanup passes (hardcoding conversions in files where he'd just imported the correct constant), one clearly wrong type signature that survived a "cleanup" commit, an `assert` used for real validation, and continuing (not originating) the wildcard-import pattern in a few files. |
| **Allan Leal** | **7/10** | Small, foundational contribution (~110 lines, core `fluidstate.py`) with no red flags in any category — no eval, no hardcoded units, no bad practices found, type hints partial but consistent. Not scored higher only because the sample is too small to demonstrate track record across the harder parts of the codebase. |
| **Tsubasa Onishi** | **4/10** | Originated the specific eval-masking-circular-imports pattern this report was triggered by, plus the systemic wildcard-import style still present in CMG modules, and a traceback-discarding bare except. Partially offset by reasonable era-appropriate type hints and authorship of the well-organized `core/config.py`. Limited footprint (~1,100 lines) means the damage is contained but the *pattern* it established was costly later. |
| **Morteza** | **3/10** | Heaviest contributor and the source of most current problems: the most dangerous surviving `eval`/`exec` calls (unsandboxed, config/input-driven), pervasive hardcoded unit conversions duplicating an existing `constants.py` (including in files that already import it), the weakest type-hint coverage, a 440-line/10-level-deep function full of unexplained magic numbers, silent bare excepts, and stray `print()` debugging left in library code. Some redeeming patterns (exception chaining, a well-built safe expression evaluator sitting next to the unsafe `eval` calls) show the capability is there but isn't applied consistently. |

**Caveat on objectivity**: since Chad Baker is also the person who requested this report, findings against him were not softened — the `wells.py` type-signature bug, the imported-but-unused-constant inconsistencies, and the assert-for-validation issue are all real and independently verifiable via the file:line references above.

---

## Addendum: Chad Baker's subsequent solo work in `tango-core`

`tango-core-standalone` forked from a sibling repo, `tango-core` (remotes: `github.com/GEG-ETHZ/TANGO`, `gitlab.ethz.ch/geg/tango-projects/tango-core`), at the HEAD commit noted above. Since that fork (2025-12-02 through 2026-08-03), `tango-core` has continued with ~250 more commits, of which **241 are authored solely by Chad Baker** — a clean, largely single-author dataset to check whether the patterns found above (categories 1-4) persisted, regressed, or improved once he was working without the rest of the team's code to react against. Most of this work is a new package, `tango` (34 files, ~4,450 lines), built substantially from scratch, alongside continued cleanup of the legacy `src/tango` tree.

**1. `eval`/`exec`** — Fully resolved. Commits `9c4eec1` and `8b579a8` (early Dec 2025) removed the last `eval()`-based dynamic class resolution (in `src/tango/core/config.py`/`utils.py`), replacing it with a proper class registry and dependency injection. A live grep of the repo confirms zero `eval(`/`exec(`/`__import__`/`importlib.import_module` in anything Chad touched post-fork; the only remaining raw calls are in legacy `optimizerr.py`, outside his post-fork changes (i.e., not yet touched, not a new regression).

**2. Hardcoded units** — Real improvement, not perfect. `tango` has its own `constants.py` with named SI-prefix/conversion constants (`MEGA`, `PA_TO_MPA`, `W_TO_MW`, `YEAR_TO_SECOND`, etc.) and an explicit docstring instructing that conversions be named, not magic numbers. Mostly followed, but the exact failure mode from the original report recurs in miniature: `well/numerical.py:418` and `well/lumped.py:311` both hardcode `* 1e6` for MPa→Pa despite the file already importing other constants from the same module — the two files also duplicate the surrounding pump-boost logic near-verbatim, so it's a shared bug plus a missed-constant issue in one move.

**3. Type hints & tooling** — The clearest structural improvement. `mypy src/tango` currently passes clean (0 issues across 34 files), and unlike the standalone repo's unenforced `[tool.mypy]` config, it's now actually gated: a real `.pre-commit-config.yaml` (ruff on commit; mypy + pytest on push) and `.gitlab-ci.yml` (ruff/mypy/pytest on every MR). Only 5 `type: ignore` comments in the whole new package, all narrowly scoped and justified. Caveat: `disallow_untyped_defs` and the mypy `exclude` are scoped to `tango.*` only — legacy `src/tango` (where most of the issues in this report live) remains unchecked and unenforced.

**4. Other practices** — No bare `except:`, no wildcard imports, no mutable default args, no stray `print()` in library code (one CLI-appropriate print found), no assert-for-validation. Two honestly self-flagged but unresolved rough edges: a vague variable name (`test_p`) and a TODO comment admitting the author didn't fully understand his own `auto_flow_modes` logic — both shipped as-is rather than fixed, which is transparent but still a real clarity gap.

**Overall trend**: clear continued improvement rather than stagnation or regression. A concentrated December 2025 cleanup phase (finishing the eval/wildcard-import removal, fixing builtin-shadowing) was followed by a new, CI-enforced, well-typed package built with meaningfully more engineering discipline than either the pre-fork legacy code or the standalone-repo snapshot audited above — tempered by one recurring duplication/magic-number lapse and a couple of candidly unresolved gaps in the newest code. This is consistent with, and reinforces, the 7/10 rating above: strongest of the four in the original report, and the trajectory since the fork point is upward rather than flat.

### `LockedState` and round-trip (de)serialization — a design win the categories above don't capture

The first pass of this addendum was scoped too narrowly to the four bad-practice categories from the original prompt and missed the most notable *positive* architectural decision in `tango`: `src/tango/core/locked_state.py`'s `LockedState[T]` wrapper, and the state-management scheme built around it.

The problem it solves is real and specific to this domain: iterative multi-component solvers that mix a convergence loop with a timestep loop are prone to a state variable being read before its upstream dependency updates, or written twice in one timestep — bugs that don't show up as obviously-wrong code, only as wrong *results*, and only sometimes. Rather than relying on caller discipline (comments, review, hoping every orchestrator gets the solve order right), the constraint is embedded in the data itself: every state field is a `LockedState[T]` with an explicit `fresh`/`stale` status, `get_fresh()`/`get_stale()` assert the expected status before returning a value, and `update()` raises `DoubleWriteError` on a second write in the same timestep. The failure mode moves from "silently wrong number three components downstream" to "immediate exception at the call site that wrote or read at the wrong time."

Three points worth crediting explicitly:

1. **Honest, layered bypass documentation instead of false guarantees.** The module docstring lays out exactly three enforcement layers (`__slots__` blocking attribute addition, double-underscore name-mangling forcing `ls._LockedState__value = x` as the only escape hatch, and `frozen=True` on every containing dataclass to stop whole-field replacement) and then has a dedicated "What is still NOT prevented" section admitting the mangled-name escape hatch always works in Python and explaining *why* it's not worth closing (an `__setattr__` override would force every internal write through `object.__setattr__` for zero practical benefit, since anyone reaching through name mangling already knows they're bypassing a safety mechanism). This is the right way to document a safety mechanism with known limits — no overselling.

2. **Transparent Pydantic v2 serialization via `__get_pydantic_core_schema__`.** `LockedState(v)` serializes to the bare value `v` with no wrapper metadata, so a saved YAML/JSON/msgpack checkpoint is just plain floats/lists — readable, diffable, and stable independent of the wrapper's internal implementation — while deserialization reconstructs a fresh `LockedState` transparently. This is a non-obvious pydantic integration (custom core schema, not just a validator) done correctly.

3. **The round-trip tests actually earn the claim.** `tests/unit/test_serde_roundtrip.py` (6 tests) and `tests/unit/test_locked_state.py` (13 tests) don't just check that `model_dump()` produces the right shape — they verify `LockedState[float]` *and* `LockedState[list[float]]` fields (cell arrays) survive `model_dump()` → `from_dict(dump, skip_init=True)` with values preserved via `pytest.approx`, status resets to fresh, and a scalar accumulator field (`energy_extracted`) survives a **multi-timestep** round-trip, not just a single solve. `test_graph_surface_roundtrip_then_resolve` goes a step further and proves that a component holding a private, non-serialized TESPy network can be checkpointed, restored, and `solve()`d again — i.e., that `init()` correctly rebuilds derived state from the serialized config rather than silently depending on stale private attributes surviving the round-trip. That's the test that actually catches the class of bug ("looks restored, is secretly broken") that round-trip serialization code is most prone to.

This doesn't change the numeric score in the original report (which was scoped to the standalone repo, not `tango`), but it does mean the "continued improvement" conclusion above understates things: this isn't just cleanup of old mistakes, it's new load-bearing infrastructure designed around a specific, previously-undetected class of bug, documented candidly about its own limits, and backed by tests that check the property that actually matters (does a restored object behave identically, including under further mutation) rather than just that serialization doesn't crash.
