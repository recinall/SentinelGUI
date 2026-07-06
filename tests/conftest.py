"""Shared pytest configuration.

Forces an offscreen Qt platform (and a non-interactive matplotlib backend) *before*
any Qt/matplotlib import can happen, so importing the UI modules (e.g.
``sentinelgui.ui.main_window``, which imports PySide6 at module scope) works headless
with no real display and no windows are ever shown.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_qsettings(tmp_path_factory):
    """Redirect QSettings to a throwaway dir so theme-persistence tests never touch
    the developer's real ``~/.config``."""
    from PySide6.QtCore import QSettings

    path = str(tmp_path_factory.mktemp("qsettings"))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, path)
    yield


@pytest.fixture(scope="session")
def qapp():
    """A single shared QApplication for tests that need a live app instance."""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
