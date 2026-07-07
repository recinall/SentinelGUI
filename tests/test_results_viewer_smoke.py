"""Offscreen smoke tests for the results-viewer window.

Builds a scene folder of tiny real GeoTIFFs in ``tmp_path`` and constructs the real
``ResultsViewer`` under the offscreen platform (session ``qapp`` fixture). No network.
"""

import numpy as np
import rasterio
from rasterio.transform import from_origin

from sentinelgui.ui.results_viewer import ResultsViewer

CRS = "EPSG:32632"
TRANSFORM = from_origin(654294, 5088566, 10, 10)
H, W = 6, 8


def _write(path, data):
    if data.ndim == 2:
        data = data[np.newaxis, :, :]
    count, height, width = data.shape
    with rasterio.open(path, "w", driver="GTiff", dtype=data.dtype, count=count,
                       height=height, width=width, crs=CRS, transform=TRANSFORM) as dst:
        dst.write(data)
    return path


def _select(combo, name):
    """Select a combo item by its display name (findData compares Path by identity)."""
    combo.setCurrentIndex(combo.findText(name))


def _make_scene(folder):
    _write(folder / "sentinel_rgb.tif", np.zeros((3, H, W), dtype=np.uint8))
    _write(folder / "sentinel_ndvi_color.tif", np.full((3, H, W), 128, dtype=np.uint8))
    _write(folder / "sentinel_ndvi.tif",
           np.linspace(0, 1, H * W, dtype=np.float32).reshape(H, W))
    _write(folder / "sentinel_band_b04.tif",
           np.linspace(0, 1, H * W, dtype=np.float32).reshape(H, W))
    return folder


def test_viewer_populates_combos_from_folder(qapp, tmp_path):
    _make_scene(tmp_path)
    viewer = ResultsViewer(tmp_path)

    # base/map combo lists every physical file (rgb + 2 singles); the _color
    # companion is excluded. overlay adds a "(none)" first entry to the 2 singles.
    assert viewer.base_combo.count() == 3
    assert viewer.overlay_combo.count() == 3
    assert viewer.overlay_combo.itemData(0) is None
    # the colorized companion is never offered
    assert viewer.base_combo.findText("sentinel_ndvi_color.tif") == -1
    assert viewer.overlay_combo.findText("sentinel_ndvi_color.tif") == -1
    # a base is displayed on load
    assert viewer._base_rgb is not None
    assert not viewer.view.base_item.pixmap().isNull()
    viewer.close()


def test_single_band_overlay_enables_threshold(qapp, tmp_path):
    # With _color companions excluded, every overlay option is a single-band raster
    # (raw index / band) carrying a mask, so threshold + opacity are always available.
    _make_scene(tmp_path)
    viewer = ResultsViewer(tmp_path)

    _select(viewer.overlay_combo, "sentinel_ndvi.tif")
    assert viewer.view.has_overlay()
    assert viewer.view.supports_threshold()              # single-band -> mask
    assert viewer.threshold_slider.isEnabled()
    assert viewer.opacity_slider.isEnabled()

    _select(viewer.overlay_combo, "sentinel_band_b04.tif")
    assert viewer.view.supports_threshold()
    assert viewer.threshold_slider.isEnabled()
    viewer.close()


def test_opacity_slider_drives_view(qapp, tmp_path):
    _make_scene(tmp_path)
    viewer = ResultsViewer(tmp_path)
    _select(viewer.overlay_combo, "sentinel_ndvi.tif")

    viewer.opacity_slider.setValue(30)
    assert abs(viewer.view.overlay_item.opacity() - 0.30) < 1e-6
    assert viewer.opacity_value.text() == "30%"
    viewer.close()


def test_single_map_mode_clears_overlay(qapp, tmp_path):
    _make_scene(tmp_path)
    viewer = ResultsViewer(tmp_path)
    _select(viewer.overlay_combo, "sentinel_ndvi.tif")
    assert viewer.view.has_overlay()

    viewer.single_mode_radio.setChecked(True)
    assert not viewer.view.has_overlay()
    assert not viewer.overlay_combo.isEnabled()
    viewer.close()


def test_export_writes_georeferenced_composite(qapp, tmp_path, monkeypatch):
    _make_scene(tmp_path)
    viewer = ResultsViewer(tmp_path)
    _select(viewer.overlay_combo, "sentinel_ndvi.tif")

    out = tmp_path / "exported.tif"
    monkeypatch.setattr(
        "sentinelgui.ui.results_viewer.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "GeoTIFF (*.tif)")),
    )
    viewer._on_save_composite()

    assert out.exists()
    with rasterio.open(out) as src:
        assert src.count == 3
        assert src.crs.to_string() == CRS
        assert src.transform == TRANSFORM
    viewer.close()


def test_empty_folder_disables_controls(qapp, tmp_path):
    viewer = ResultsViewer(tmp_path)  # no tifs
    assert viewer.base_combo.count() == 0
    assert not viewer.base_combo.isEnabled()
    assert viewer._base_rgb is None
    viewer.close()
