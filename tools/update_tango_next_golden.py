"""Regenerate golden (known-good) tango_next snapshots for the old/new parity tests.

Run this only after confirming a tango_next change is an *intentional*
physics change — review the resulting JSON diff as you would review any
other test-value change. See the "new vs. golden" section of
tests/regtest/test_old_new_parity.py's module docstring for why this
snapshot exists alongside the old-tango comparison.

Usage: uv run python tools/update_tango_next_golden.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
PARITY_TEST_PATH = REPO_ROOT / "tests" / "regtest" / "test_old_new_parity.py"


def _load_parity_test_module():
    """Import test_old_new_parity.py by file path (tests/ isn't a package)."""
    spec = importlib.util.spec_from_file_location("test_old_new_parity", PARITY_TEST_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load spec for {PARITY_TEST_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    """Regenerate the golden JSON snapshot for every implemented parity case.

    Also regenerates the ``_8yr`` fast-companion snapshot
    (``test_old_new_parity_fast``'s own golden check, SF case only today)
    — that test hardcodes ``num_tsteps=N_TSTEPS_FAST`` rather than reusing
    a ``ParityCase``, so it isn't covered by the loop below on its own.
    If a future case grows its own fast companion, add its stem here too.
    """
    mod = _load_parity_test_module()
    mod.GOLDEN_DIR.mkdir(exist_ok=True)

    for case in mod.PARITY_CASES:
        if case.new_yml is None:
            continue
        result = mod._run_tango_next(mod.EXAMPLES_NEW / case.new_yml)  # noqa: SLF001
        path = mod.GOLDEN_DIR / f"{Path(case.new_yml).stem}.json"
        path.write_text(json.dumps(result, indent=2) + "\n")
        print(f"wrote {path}")  # noqa: T201

    fast_result = mod._run_tango_next(  # noqa: SLF001
        mod.EXAMPLES_NEW / "hydro_sf_electric.yml",
        num_tsteps=mod.N_TSTEPS_FAST,
    )
    fast_path = mod.GOLDEN_DIR / "hydro_sf_electric_8yr.json"
    fast_path.write_text(json.dumps(fast_result, indent=2) + "\n")
    print(f"wrote {fast_path}")  # noqa: T201


if __name__ == "__main__":
    main()
