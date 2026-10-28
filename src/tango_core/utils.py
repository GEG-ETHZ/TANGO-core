# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Small helpers shared by the sweep and optimization scripts in applications/."""


def print_datetime() -> None:
    """Print the current datetime (YYYY-MM-DD HH:MM:SS) on its own line."""
    from datetime import datetime

    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# Short alias for liberal use in sweep scripts (e.g. logging wall-clock start
# time in SLURM job output, where queue wait time isn't otherwise visible).
print_dt = print_datetime
