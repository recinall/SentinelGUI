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


def test_open_results_action_constructs_viewer(window):
    from sentinelgui.ui.results_viewer import ResultsViewer

    # No scene selected -> falls back to the per-project dir (may not exist); must not raise.
    window.open_results()
    assert isinstance(window.results_viewer, ResultsViewer)
    window.results_viewer.close()


# -- AOI tab --


def test_default_aoi(window):
    # A small ~0.2 deg box centered on 11.25/46.25, sized to sit inside a single
    # Sentinel-2 tile (avoids the multi-tile straddle that caused Bug 3).
    assert window.aoi_tab.get_aoi() == {"bbox": [11.15, 46.15, 11.35, 46.35]}


def test_aoi_accepts_dms_in_bbox_field(window):
    # 10°30'00" == 10.5; the other three stay decimal.
    window.aoi_tab.min_lon.setText("10°30'00\"")
    aoi = window.aoi_tab.get_aoi()
    assert aoi["bbox"] == [10.5, 46.15, 11.35, 46.35]


def test_aoi_defaults_to_bbox_mode(window):
    assert window.aoi_tab.bbox_radio.isChecked()
    assert not window.aoi_tab.center_radio.isChecked()


def test_switching_to_center_mirrors_default_bbox(window):
    tab = window.aoi_tab
    tab.center_radio.setChecked(True)
    assert float(tab.center_lat.text()) == pytest.approx(46.25)
    assert float(tab.center_lon.text()) == pytest.approx(11.25)
    assert float(tab.width_km.text()) > 0
    assert float(tab.height_km.text()) > 0
    # Round-trips through the UI back to the original AOI.
    min_lon, min_lat, max_lon, max_lat = tab.get_aoi()["bbox"]
    assert [min_lon, min_lat, max_lon, max_lat] == pytest.approx(
        [11.15, 46.15, 11.35, 46.35]
    )


def test_switching_to_bbox_mirrors_center_window(window):
    tab = window.aoi_tab
    tab.center_radio.setChecked(True)
    tab.center_lat.setText("0")
    tab.center_lon.setText("0")
    tab.width_km.setText("222.64")
    tab.height_km.setText("221.148")
    tab.bbox_radio.setChecked(True)
    assert float(tab.min_lon.text()) == pytest.approx(-1.0)
    assert float(tab.max_lon.text()) == pytest.approx(1.0)
    assert float(tab.min_lat.text()) == pytest.approx(-1.0)
    assert float(tab.max_lat.text()) == pytest.approx(1.0)


def test_toggle_with_unparseable_active_input_does_not_crash(window):
    tab = window.aoi_tab
    before = (
        tab.center_lat.text(),
        tab.center_lon.text(),
        tab.width_km.text(),
        tab.height_km.text(),
    )
    tab.min_lon.setText("abc")
    tab.center_radio.setChecked(True)  # must not raise
    after = (
        tab.center_lat.text(),
        tab.center_lon.text(),
        tab.width_km.text(),
        tab.height_km.text(),
    )
    assert after == before


def test_aoi_center_window_mode_computes_bbox(window):
    tab = window.aoi_tab
    tab.center_radio.setChecked(True)
    tab.center_lat.setText("0")
    tab.center_lon.setText("0")
    tab.width_km.setText("222.64")
    tab.height_km.setText("221.148")
    min_lon, min_lat, max_lon, max_lat = tab.get_aoi()["bbox"]
    assert min_lon == pytest.approx(-1.0)
    assert max_lon == pytest.approx(1.0)
    assert min_lat == pytest.approx(-1.0)
    assert max_lat == pytest.approx(1.0)


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


def test_save_bands_auto_checks_only_necessary_bands(window):
    # Ticking "Save Individual Bands" must auto-check the NECESSARY bands (those required
    # by the selected indices + the RGB triple when the composite is on) -- not all 12 --
    # so bands_to_load is non-empty (Bug 2 stays fixed) without saving every band.
    tab = window.processing_tab
    assert tab.selected_bands() == set()

    tab.index_checkboxes["NDVI"].setChecked(True)
    tab.rgb_cb.setChecked(True)
    tab.save_bands_cb.setChecked(True)

    ndvi_bands = set(Sentinel2COGProcessor.ALGORITHMS["NDVI"]["bands"])
    expected = ndvi_bands | {"b04", "b03", "b02"}
    assert tab.selected_bands() == expected
    assert tab.selected_bands() != set(Sentinel2COGProcessor.BAND_MAPPING)

    # Live resync: adding an index while save-bands is on extends the checked set.
    tab.index_checkboxes["NDWI"].setChecked(True)
    ndwi_bands = set(Sentinel2COGProcessor.ALGORITHMS["NDWI"]["bands"])
    assert tab.selected_bands() == expected | ndwi_bands

    tab.save_bands_cb.setChecked(False)
    assert not any(cb.isChecked() for cb in tab.band_checkboxes.values())
    assert tab.selected_bands() == set()


def test_save_bands_untoggle_preserves_manual_picks(window):
    # Untoggling save-bands clears only the auto-added bands, leaving a band the user
    # ticked by hand (and that no index/RGB needs) still selected.
    tab = window.processing_tab
    tab.index_checkboxes["NDVI"].setChecked(True)

    manual = next(b for b in tab.band_checkboxes if b not in tab._necessary_bands())
    tab.band_checkboxes[manual].setChecked(True)

    tab.save_bands_cb.setChecked(True)
    assert manual in tab.selected_bands()

    tab.save_bands_cb.setChecked(False)
    assert tab.selected_bands() == {manual}


def test_clear_all_bands_button_wipes_every_checkbox(window):
    # The Clear-All-Bands escape hatch unchecks every band, auto or manual.
    tab = window.processing_tab
    tab.index_checkboxes["NDVI"].setChecked(True)
    tab.save_bands_cb.setChecked(True)
    assert tab.selected_bands()

    tab.clear_all_bands()
    assert not any(cb.isChecked() for cb in tab.band_checkboxes.values())
    assert tab.selected_bands() == set()


def test_save_color_checkbox_defaults_off_and_toggles(window):
    # The colorized _color companion is opt-in (physical-data-only): the checkbox
    # starts unchecked and simply mirrors into save_color(), with no side effects.
    tab = window.processing_tab
    assert tab.save_color() is False

    tab.save_color_cb.setChecked(True)
    assert tab.save_color() is True

    tab.save_color_cb.setChecked(False)
    assert tab.save_color() is False


# -- Output tab --


def test_output_defaults(window):
    tab = window.output_tab
    assert tab.output_dir().endswith("sentinel_output")
    assert tab.file_prefix() == "sentinel"
    assert tab.bit_depth() == 16
    assert tab.basemap_source() == "esri"
    assert tab.basemap_zoom() == 16
