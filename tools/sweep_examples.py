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


def categorize(path: Path) -> str:
    """Classify a config (given repo-root-relative, e.g. examples/failing/x.yml)."""
    parts = path.parts  # ("examples", ..., "file.yml")
    subdir = parts[1] if len(parts) > 2 else None
    if subdir in EXPECTED_TO_FAIL_DIRS:
        return "expected_fail"
    if subdir == "tango_next":
        return "tango_next"
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


def write_report(results: list[SweepResult]) -> Path:
    """Write timestamped JSON + markdown reports and return the markdown path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    json_path = OUTPUT_DIR / f"sweep_{timestamp}.json"
    with json_path.open("w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    report_path = OUTPUT_DIR / f"sweep_{timestamp}.md"
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    lines = [
        "# Examples sweep report",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}. {len(results)} configs checked.",
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

    results: list[SweepResult] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, str(c), args.timeout): c for c in configs}
        for i, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            print(f"[{i}/{len(configs)}] {result.status:15s} {result.duration_s:6.1f}s  {result.path}")
            results.append(result)

    report_path = write_report(results)
    print(f"\nReport written to {report_path.relative_to(REPO_ROOT)}")

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print("Summary:", counts)

    needs_attention = counts.get("FAIL", 0) + counts.get("TIMEOUT", 0) + counts.get("UNEXPECTED_PASS", 0)
    return 1 if needs_attention else 0


if __name__ == "__main__":
    sys.exit(main())
