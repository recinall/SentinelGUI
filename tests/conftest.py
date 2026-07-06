"""Shared pytest configuration.

Forces an offscreen Qt platform (and a non-interactive matplotlib backend) *before*
any Qt/matplotlib import can happen, so importing the UI modules (e.g.
``sentinelgui.ui.main_window``, which imports PySide6 at module scope) works headless
with no real display and no windows are ever shown.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
