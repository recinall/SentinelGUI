"""Offscreen smoke tests for the raster viewer widgets.

Run under the process-wide offscreen Qt platform (``tests/conftest.py``) using the
session ``qapp`` fixture. No files, no network — arrays are built in-process.
"""

import numpy as np
from PySide6.QtGui import QImage

from sentinelgui.ui.widgets.color_legend import ColorLegend
from sentinelgui.ui.widgets.raster_view import RasterView


def test_numpy_to_qimage_formats():
    rgb = np.zeros((4, 5, 3), dtype=np.uint8)
    img = RasterView.numpy_to_qimage(rgb)
    assert img.width() == 5 and img.height() == 4
    assert img.format() == QImage.Format.Format_RGB888

    rgba = np.zeros((4, 5, 4), dtype=np.uint8)
    assert RasterView.numpy_to_qimage(rgba).format() == QImage.Format.Format_RGBA8888


def test_view_stacks_base_and_overlay(qapp):
    view = RasterView()
    assert len(view.scene().items()) == 2  # base + overlay always present

    view.set_base(np.zeros((6, 8, 3), dtype=np.uint8))
    view.set_overlay(np.full((6, 8, 3), 255, dtype=np.uint8))

    assert not view.base_item.pixmap().isNull()
    assert not view.overlay_item.pixmap().isNull()
    assert view.has_overlay()


def test_opacity_slider_drives_overlay_opacity(qapp):
    view = RasterView()
    view.set_base(np.zeros((4, 4, 3), dtype=np.uint8))
    view.set_overlay(np.zeros((4, 4, 3), dtype=np.uint8))

    view.set_overlay_opacity(0.4)
    assert abs(view.overlay_item.opacity() - 0.4) < 1e-6
    view.set_overlay_opacity(2.0)  # clamped
    assert abs(view.overlay_item.opacity() - 1.0) < 1e-6


def test_threshold_hides_low_mask_pixels(qapp):
    view = RasterView()
    view.set_base(np.zeros((1, 2, 3), dtype=np.uint8))
    rgb = np.full((1, 2, 3), 255, dtype=np.uint8)
    mask = np.array([[0.0, 1.0]])  # left pixel low, right pixel high
    view.set_overlay(rgb, mask)
    assert view.supports_threshold()

    view.set_overlay_threshold(0.5)
    img = view.overlay_item.pixmap().toImage()
    assert img.pixelColor(0, 0).alpha() == 0     # below threshold -> transparent
    assert img.pixelColor(1, 0).alpha() == 255   # above threshold -> opaque


def test_overlay_without_mask_has_no_threshold(qapp):
    view = RasterView()
    view.set_overlay(np.zeros((2, 2, 3), dtype=np.uint8))
    assert not view.supports_threshold()
    view.clear_overlay()
    assert not view.has_overlay()
    assert view.overlay_item.pixmap().isNull()


def test_color_legend_visibility_follows_colormap(qapp):
    legend = ColorLegend()
    legend.show()
    legend.set_colormap("RdYlGn", low="-1", high="+1")
    assert legend._cmap_name == "RdYlGn"
    assert legend.isVisible()
    legend.set_colormap(None)
    assert not legend.isVisible()
    legend.close()
