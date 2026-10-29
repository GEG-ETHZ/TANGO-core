"""Pytest configuration shared by every test."""

import matplotlib

# Tests only write figures to files. A non-interactive backend avoids
# opening a GUI toolkit, which fails on runners without a working Tk
# install (GitHub's hosted Windows runners).
matplotlib.use("Agg")
