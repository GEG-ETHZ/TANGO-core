"""Sweep every example config under examples/ and record whether it still runs.

This is a *validity* check, not a *value judgment*: it tells you which example
configs are mechanically broken (import errors, missing external tools,
crashes, hangs) versus which still execute cleanly. It does not tell you
whether a config is scientifically meaningful or worth keeping — that still
needs a human. See REPO_CLEANUP_AUDIT.md for the discussion this supports.

Each `.yml`/`.yaml` under examples/ is run in its own subprocess (so one
crash/hang can't take down the sweep) via the installed `tango_cli` /
`tango_next_cli` console scripts, with a per-file timeout. `--no-save` /
`validate` are used so the sweep doesn't scatter result files everywhere.

Usage:
    uv run python tools/sweep_examples.py
    uv run python tools/sweep_examples.py --timeout 60 --workers 8
    uv run python tools/sweep_examples.py --only examples/TANGO_paper
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
OUTPUT_DIR = REPO_ROOT / "tools" / "examples_sweep_output"

# examples/failing/ exists specifically to hold configs that are *supposed*
# to error out (see examples/failing/readme.md) — a non-zero exit there is
# expected, not a finding.
EXPECTED_TO_FAIL_DIRS = {"failing"}

# Configs that are mechanically broken for reasons outside this repo's control
# (an external tool / optional dependency this sweep doesn't install) or that
# use a feature slated for removal. A FAIL here isn't a finding — see the
# per-marker comment below for why each one is excluded rather than fixed.
KNOWN_UNSUPPORTED_MARKERS: dict[str, str] = {
    # Requires an external MOOSE + moskito2 install; every config using this
    # hardcodes one former contributor's local machine paths (including a
    # `moose_executable_path` *default* in src/tango/units/dataclasses.py
    # itself), so there's no portable path fix — needs an actual MOOSE
    # toolchain, which this environment doesn't have.
    "unit: 'moose'": "requires external MOOSE/moskito2 install (not available here)",
    # `addons.<Name>.active: 'yes'` covers two currently-broken-by-default
    # addons: ThermaGraph.execute() unconditionally imports PyQt5 and
    # launches a QApplication (an optional group, `uv sync --group
    # tango-app`, this sweep doesn't install — the docstring claims a
    # headless SVG batch mode exists, but the code always takes the GUI
    # path); Analyzer configs in the repo also hardcode one former
    # contributor's absolute `results_file` path (same class of issue as
    # the MOOSE paths above).
    "active: 'yes'": "addon requires PyQt5 (uv sync --group tango-app) or has a hardcoded personal path",
    # BatchSimulation (runner.py) is an undocumented, full-factorial-only
    # parameter sweep DSL being superseded by standalone DOE scripts
    # (see applications/*_sweep/) that support arbitrary sampling. It's also
    # currently broken independent of this (missing `save_dir` arg at the
    # Tango() call site) — not being fixed since the plan is to port these
    # configs to scripts instead.
    "batch_simulation:": "uses the deprecated BatchSimulation feature, being ported to scripts",
    # Orchestrator.hotmapsdispatch_runner() (src/tango/orchestrators/external.py:164)
    # hardcodes another former contributor's absolute path with no config
    # override at all — not even a per-example hardcode to fix, it's a
    # string literal inside the function body. Exports to an external
    # "Hotmaps dispatch" tool this repo doesn't have.
    "run_district_heating_simulator: 'yes'": "hardcoded path in orchestrators/external.py, no config override exists",
}


@dataclass
class SweepResult:
    """Outcome of attempting to run one example config."""

    path: str
    category: str  # "native", "tango_next", "expected_fail"
    status: str  # "PASS", "FAIL", "TIMEOUT", "EXPECTED_FAIL", "UNEXPECTED_PASS"
    duration_s: float
    returncode: int | None
    error_tail: str


def discover_configs(only: str | None) -> list[Path]:
    """Find every .yml/.yaml under examples/, optionally restricted to a subpath."""
    configs = sorted(EXAMPLES_DIR.rglob("*.yml")) + sorted(EXAMPLES_DIR.rglob("*.yaml"))
    if only:
        only_path = (REPO_ROOT / only).resolve()
        configs = [c for c in configs if only_path in c.resolve().parents or c.resolve() == only_path]
    return [c.relative_to(REPO_ROOT) for c in configs]


def _has_uncommented_marker(path: Path, marker: str) -> bool:
    """True if `marker` appears outside of a YAML comment in the file."""
    try:
        lines = (REPO_ROOT / path).read_text().splitlines()
    except OSError:
        return False
    for line in lines:
        code = line.split("#", 1)[0]
        if marker in code:
            return True
    return False


def categorize(path: Path) -> str:
    """Classify a config (given repo-root-relative, e.g. examples/failing/x.yml)."""
    parts = path.parts  # ("examples", ..., "file.yml")
    subdir = parts[1] if len(parts) > 2 else None
    if subdir in EXPECTED_TO_FAIL_DIRS:
        return "expected_fail"
    if subdir == "tango_next":
        return "tango_next"
    if any(_has_uncommented_marker(path, marker) for marker in KNOWN_UNSUPPORTED_MARKERS):
        return "expected_fail"
    return "native"


def build_command(path: Path, category: str) -> list[str]:
    """Build the subprocess command to attempt this config."""
    if category == "tango_next":
        return ["uv", "run", "tango_next_cli", "validate", str(path)]
    return ["uv", "run", "tango_cli", "-f", str(path), "--no-save", "--log-level", "ERROR"]


def run_one(path_str: str, timeout: float) -> SweepResult:
    """Run a single example config in a subprocess and record the outcome."""
    path = Path(path_str)
    category = categorize(path)
    cmd = build_command(path, category)

    start = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.monotonic() - start
        ok = proc.returncode == 0
        error_tail = "" if ok else "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-25:])

        if category == "expected_fail":
            status = "EXPECTED_FAIL" if not ok else "UNEXPECTED_PASS"
        else:
            status = "PASS" if ok else "FAIL"

        return SweepResult(path_str, category, status, duration, proc.returncode, error_tail)

    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        return SweepResult(path_str, category, "TIMEOUT", duration, None, f"exceeded {timeout}s timeout")


def write_report(results: list[SweepResult], timestamp: str, total: int) -> Path:
    """Write JSON + markdown reports for `timestamp` (in place) and return the markdown path.

    Safe to call repeatedly with a growing `results` list — e.g. after every
    completed config — so a report reflecting everything finished so far
    survives a Ctrl-C, crash, or closed terminal. `total` (the full config
    count) is threaded through so a partial report is labeled as partial
    rather than looking like a complete-but-small run.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUTPUT_DIR / f"sweep_{timestamp}.json"
    with json_path.open("w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    report_path = OUTPUT_DIR / f"sweep_{timestamp}.md"
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    in_progress_note = (
        f" **IN PROGRESS — {len(results)}/{total} configs done, report will keep updating.**"
        if len(results) < total
        else ""
    )
    lines = [
        "# Examples sweep report",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}. {len(results)}/{total} configs checked.{in_progress_note}",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    for status in ["PASS", "EXPECTED_FAIL", "FAIL", "TIMEOUT", "UNEXPECTED_PASS"]:
        if status in counts:
            lines.append(f"| {status} | {counts[status]} |")
    lines += ["", "## Findings that likely need a look", ""]

    noteworthy = [r for r in results if r.status in ("FAIL", "TIMEOUT", "UNEXPECTED_PASS")]
    if not noteworthy:
        lines.append("None — everything behaved as expected.")
    else:
        for r in sorted(noteworthy, key=lambda r: r.path):
            lines.append(f"### `{r.path}` — {r.status} ({r.duration_s:.1f}s)")
            lines.append("```")
            lines.append(r.error_tail or "(no output captured)")
            lines.append("```")
            lines.append("")

    lines += ["", "## Full results", "", "| Status | Duration (s) | Path |", "|---|---|---|"]
    for r in sorted(results, key=lambda r: (r.status, r.path)):
        lines.append(f"| {r.status} | {r.duration_s:.1f} | `{r.path}` |")

    report_path.write_text("\n".join(lines))
    return report_path


def main() -> int:
    """Discover, run, and report on all example configs."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-example timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of examples to run concurrently (default: 4)",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Restrict the sweep to a subdirectory/file under examples/",
    )
    args = parser.parse_args()

    configs = discover_configs(args.only)
    if not configs:
        print("No example configs found.")
        return 1

    print(f"Sweeping {len(configs)} example configs (timeout={args.timeout}s, workers={args.workers})...")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results: list[SweepResult] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, str(c), args.timeout): c for c in configs}
        try:
            for i, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                print(f"[{i}/{len(configs)}] {result.status:15s} {result.duration_s:6.1f}s  {result.path}")
                results.append(result)
                # Re-write after every completion so a Ctrl-C, crash, or closed
                # terminal only loses whatever's still in-flight, not the whole run.
                write_report(results, timestamp, len(configs))
        except KeyboardInterrupt:
            print(f"\nInterrupted after {len(results)}/{len(configs)} — partial report already saved.")
            raise

    report_path = write_report(results, timestamp, len(configs))
    print(f"\nReport written to {report_path.relative_to(REPO_ROOT)}")

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print("Summary:", counts)

    needs_attention = counts.get("FAIL", 0) + counts.get("TIMEOUT", 0) + counts.get("UNEXPECTED_PASS", 0)
    return 1 if needs_attention else 0


if __name__ == "__main__":
    sys.exit(main())
