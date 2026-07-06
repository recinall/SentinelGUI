"""Shared pytest configuration.

Forces an offscreen Qt platform (and a non-interactive matplotlib backend) *before*
any Qt/matplotlib import can happen, so importing the UI modules (e.g.
``sentinelgui.ui.main_window``, which imports PySide6 at module scope) works headless
with no real display and no windows are ever shown.
"""

import os
import tempfile

import pytest

# None of the imports above pull in PySide6/matplotlib, so the environment below is still
# set before the first Qt import (which only happens inside the fixtures/tests).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

# Redirect the platform config dir to a throwaway location *before* any Qt import, so the
# native ``QSettings(org, app)`` the theme uses never touches the developer's real config
# (theme-persistence tests would otherwise leak a saved mode into ``~/.config``).
_SETTINGS_DIR = tempfile.mkdtemp(prefix="sentinelgui-test-settings-")
os.environ["XDG_CONFIG_HOME"] = _SETTINGS_DIR  # Linux/CI
os.environ["APPDATA"] = _SETTINGS_DIR  # Windows fallback


@pytest.fixture(scope="session")
def qapp():
    """A single shared QApplication for tests that need a live app instance."""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
