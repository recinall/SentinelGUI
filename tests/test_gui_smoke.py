"""Characterization / smoke tests for the assembled main window (``Sentinel2GUI``).

Constructs the real window under the offscreen Qt platform (set process-wide by
``tests/conftest.py``) and freezes GUI-observable facts that must survive the split
of the monolith into ``ui/tabs`` + ``ui/widgets``: the tab structure, the field
defaults, the AOI parsing, the initial disabled state of the Process button, the
Select/Clear-All behavior over the index checkboxes, and the log-line format.

Nothing here touches the network or rasterio and no worker is ever started
(``.start()`` is never called), so each test only exercises widget construction and
plain in-process methods. A single ``QApplication`` is shared for the whole module.

The tests are split one-per-future-tab on purpose: when a builder is lifted into its
own tab/widget class the only churn is repointing that one test at the new owner
(e.g. ``window.aoi_tab.get_aoi()``), never rewriting the frozen assertions.
"""

import re

import pytest
from PySide6.QtWidgets import QApplication, QTabWidget

from sentinelgui.core.processor import Sentinel2COGProcessor
from sentinelgui.ui.main_window import Sentinel2GUI


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    w = Sentinel2GUI()
    yield w
    w.close()


# -- structural facts (owned by the controller; stable across every extraction) --


def test_window_title_and_tabs(window):
    assert window.windowTitle() == "Sentinel-2 COG Processor - Multi-Index Analysis"

    tabs = window.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.count() == 4
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "Area of Interest",
        "Search Parameters",
        "Processing Options",
        "Output Settings",
    ]


def test_app_icon_loads(app):
    # The bundled resources/icon.png must resolve and produce a non-null QIcon so the
    # frozen app shows its own icon instead of Qt's default (needs a QApplication for QPixmap).
    from sentinelgui.app import _app_icon

    assert _app_icon().isNull() is False


def test_action_buttons_initial_state(window):
    assert window.search_btn.isEnabled() is True
    assert window.basemap_btn.isEnabled() is True
    assert window.process_btn.isEnabled() is False


def test_log_format(window):
    window.log("hello smoke")
    lines = window.log_panel.log_text.toPlainText().splitlines()
    assert re.fullmatch(r"\[\d{2}:\d{2}:\d{2}\] hello smoke", lines[-1])


def test_view_menu_toggles_theme(app, window):
    from sentinelgui.ui.theme.tokens import DARK, LIGHT

    assert [a.text() for a in window.menuBar().actions()] == ["View"]
    action = window.dark_mode_action
    assert action.isCheckable()

    # Drive the slot directly so the assertions don't depend on the persisted start mode.
    window.toggle_theme(True)
    assert DARK.surface in app.styleSheet()
    window.toggle_theme(False)
    assert LIGHT.surface in app.styleSheet()

    # The menu action is wired to the same slot: toggling it flips the applied theme.
    action.setChecked(False)  # normalize to a known baseline before asserting transitions
    action.setChecked(True)
    assert DARK.surface in app.styleSheet()
    action.setChecked(False)
    assert LIGHT.surface in app.styleSheet()


# -- AOI tab --


def test_default_aoi(window):
    assert window.aoi_tab.get_aoi() == {"bbox": [11.0, 46.0, 11.5, 46.5]}


# -- Search tab --


def test_search_defaults(window):
    assert window.search_tab.cloud_cover.value() == 20.0
    assert window.search_tab.get_search_params()["cloud_cover_max"] == 20.0


# -- Processing tab --


def test_index_checkboxes_and_select_clear(window):
    tab = window.processing_tab
    assert set(tab.index_checkboxes) == set(Sentinel2COGProcessor.ALGORITHMS)

    tab.select_all_indices()
    assert all(cb.isChecked() for cb in tab.index_checkboxes.values())
    assert set(tab.selected_algorithms()) == set(Sentinel2COGProcessor.ALGORITHMS)

    tab.clear_all_indices()
    assert not any(cb.isChecked() for cb in tab.index_checkboxes.values())
    assert tab.selected_algorithms() == []


# -- Output tab --


def test_output_defaults(window):
    tab = window.output_tab
    assert tab.output_dir().endswith("sentinel_output")
    assert tab.file_prefix() == "sentinel"
    assert tab.bit_depth() == 16
    assert tab.basemap_source() == "esri"
    assert tab.basemap_zoom() == 16
