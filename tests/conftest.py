"""Shared pytest configuration.

Forces an offscreen Qt platform (and a non-interactive matplotlib backend) *before*
any Qt/matplotlib import can happen, so importing sentinel_gui.py (which imports
PySide6 at module scope) works headless with no real display and no windows are
ever shown.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
