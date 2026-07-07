"""Dedicated results-viewer window.

A top-level ``QMainWindow`` for looking at a scene's outputs without leaving the app:
either a single map (any produced GeoTIFF) or a base backdrop with a foreground
overlay whose transparency the user sets with a slider. All raster reading is done by
the Qt-free :mod:`sentinelgui.core.raster_io`; this module only wires the discovered
files to combos, drives the :class:`RasterView`, and exports a flattened composite.

The window is opened from the main window (``View -> Open Results...``) pointed at a
scene folder; it auto-discovers the known output files there and populates the combos.
Because the basemap, ``_rgb`` and the per-index rasters are resampled onto the same
reference grid, stacking base + overlay is a direct pixmap stack — no reprojection.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from sentinelgui.core.indices import index_colormap
from sentinelgui.core.raster_io import (
    apply_colormap,
    discover_rasters,
    index_name,
    load_display_rgb,
    load_normalized_band,
    save_composite_geotiff,
)
from sentinelgui.ui.widgets.color_legend import ColorLegend
from sentinelgui.ui.widgets.raster_view import RasterView

_DEFAULT_OPACITY = 60  # percent


def _colormap_for(path: Path) -> str:
    """Colormap for a single-band file: the index ramp for a raw index, else grayscale."""
    algo = index_name(path)
    return index_colormap(algo) if algo else "gray"


class ResultsViewer(QMainWindow):
    def __init__(self, start_folder, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Results Viewer")
        self.resize(900, 700)

        self._folder = Path(start_folder)
        self._singles: set[Path] = set()
        self._base_rgb = None
        self._overlay_rgb = None
        self._overlay_mask = None

        self._build_ui()
        self._load_folder(self._folder)

    # -- construction --

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        controls = QWidget()
        grid = QGridLayout(controls)

        self.folder_label = QLabel()
        self.folder_label.setProperty("role", "caption")
        change_btn = QPushButton("Change folder...")
        change_btn.clicked.connect(self._on_change_folder)
        grid.addWidget(self.folder_label, 0, 0, 1, 3)
        grid.addWidget(change_btn, 0, 3)

        self.overlay_mode_radio = QRadioButton("Base + Overlay")
        self.single_mode_radio = QRadioButton("Single map")
        self.overlay_mode_radio.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.overlay_mode_radio)
        mode_group.addButton(self.single_mode_radio)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.overlay_mode_radio)
        mode_row.addWidget(self.single_mode_radio)
        mode_row.addStretch()
        grid.addLayout(mode_row, 1, 0, 1, 4)

        self.base_combo = QComboBox()
        self.overlay_combo = QComboBox()
        grid.addWidget(QLabel("Base / Map:"), 2, 0)
        grid.addWidget(self.base_combo, 2, 1, 1, 3)
        grid.addWidget(QLabel("Overlay:"), 3, 0)
        grid.addWidget(self.overlay_combo, 3, 1, 1, 3)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(_DEFAULT_OPACITY)
        self.opacity_value = QLabel(f"{_DEFAULT_OPACITY}%")
        self.opacity_value.setProperty("role", "caption")
        grid.addWidget(QLabel("Opacity:"), 4, 0)
        grid.addWidget(self.opacity_slider, 4, 1, 1, 2)
        grid.addWidget(self.opacity_value, 4, 3)

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setValue(0)
        self.threshold_value = QLabel("off")
        self.threshold_value.setProperty("role", "caption")
        grid.addWidget(QLabel("Threshold:"), 5, 0)
        grid.addWidget(self.threshold_slider, 5, 1, 1, 2)
        grid.addWidget(self.threshold_value, 5, 3)

        action_row = QHBoxLayout()
        self.fit_btn = QPushButton("Fit")
        self.fit_btn.clicked.connect(lambda: self.view.fit())
        self.save_btn = QPushButton("Save composite...")
        self.save_btn.clicked.connect(self._on_save_composite)
        action_row.addWidget(self.fit_btn)
        action_row.addWidget(self.save_btn)
        action_row.addStretch()
        grid.addLayout(action_row, 6, 0, 1, 4)

        layout.addWidget(controls)

        self.view = RasterView()
        layout.addWidget(self.view, stretch=1)

        self.legend = ColorLegend()
        layout.addWidget(self.legend)

        self.setCentralWidget(central)

        # wire signals after the widgets exist; _refresh() is driven explicitly on load
        self.base_combo.currentIndexChanged.connect(self._refresh)
        self.overlay_combo.currentIndexChanged.connect(self._refresh)
        self.overlay_mode_radio.toggled.connect(self._refresh)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)

    # -- folder / discovery --

    def _load_folder(self, folder: Path) -> None:
        self._folder = Path(folder)
        self.folder_label.setText(str(self._folder))
        found = discover_rasters(self._folder)
        self._singles = set(found.singles)

        self.base_combo.blockSignals(True)
        self.overlay_combo.blockSignals(True)
        self.base_combo.clear()
        self.overlay_combo.clear()

        for path in [*found.base, *found.singles]:
            self.base_combo.addItem(path.name, path)

        self.overlay_combo.addItem("(none)", None)
        for path in found.singles:
            self.overlay_combo.addItem(path.name, path)

        self.base_combo.blockSignals(False)
        self.overlay_combo.blockSignals(False)

        has_files = self.base_combo.count() > 0
        for widget in (self.base_combo, self.overlay_combo, self.overlay_mode_radio,
                       self.single_mode_radio, self.fit_btn):
            widget.setEnabled(has_files)

        self._refresh()

    def _on_change_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select scene folder", str(self._folder))
        if chosen:
            self._load_folder(Path(chosen))

    # -- live updates --

    def _overlay_mode(self) -> bool:
        return self.overlay_mode_radio.isChecked()

    def _refresh(self, *_args) -> None:
        base_path = self.base_combo.currentData()
        overlay_path = self.overlay_combo.currentData()
        show_overlay = self._overlay_mode() and overlay_path is not None

        self._base_rgb = None
        self._overlay_rgb = None
        self._overlay_mask = None
        legend_cmap = None

        if base_path is not None:
            self._base_rgb = self._load_layer_rgb(base_path)
            self.view.set_base(self._base_rgb)
            if base_path in self._singles and not show_overlay:
                legend_cmap = _colormap_for(base_path)

        if show_overlay:
            rgb, mask = self._load_overlay(overlay_path)
            self._overlay_rgb, self._overlay_mask = rgb, mask
            self.view.set_overlay(rgb, mask)
            self.view.set_overlay_opacity(self.opacity_slider.value() / 100.0)
            self.view.set_overlay_threshold(self.threshold_slider.value() / 100.0)
            if overlay_path in self._singles:
                legend_cmap = _colormap_for(overlay_path)
        else:
            self.view.clear_overlay()

        # enable overlay controls only when an overlay with a mask is shown
        self.overlay_combo.setEnabled(self._overlay_mode() and self.base_combo.count() > 0)
        self.opacity_slider.setEnabled(show_overlay)
        can_threshold = show_overlay and self.view.supports_threshold()
        self.threshold_slider.setEnabled(can_threshold)
        if not can_threshold:
            self.threshold_value.setText("off")
        self.save_btn.setEnabled(show_overlay and base_path is not None)

        self.legend.set_colormap(legend_cmap, low="low", high="high")

    def _load_layer_rgb(self, path: Path):
        if path in self._singles:
            return load_display_rgb(path, colormap=_colormap_for(path))
        return load_display_rgb(path)

    def _load_overlay(self, path: Path):
        """Return ``(rgb, mask_or_none)`` for an overlay layer."""
        if path in self._singles:
            norm = load_normalized_band(path)
            return apply_colormap(norm, _colormap_for(path)), norm
        return load_display_rgb(path), None

    def _on_opacity_changed(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        self.view.set_overlay_opacity(value / 100.0)

    def _on_threshold_changed(self, value: int) -> None:
        self.threshold_value.setText("off" if value == 0 else f"{value}%")
        self.view.set_overlay_threshold(value / 100.0)

    # -- export --

    def _on_save_composite(self) -> None:
        if self._base_rgb is None or self._overlay_rgb is None:
            return
        base_path = self.base_combo.currentData()
        default = str(self._folder / "composite.tif")
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Save composite", default, "GeoTIFF (*.tif)")
        if not chosen:
            return

        opacity = self.opacity_slider.value() / 100.0
        height, width = self._overlay_rgb.shape[:2]
        alpha = np.full((height, width), int(opacity * 255), dtype=np.uint8)
        if self._overlay_mask is not None:
            threshold = self.threshold_slider.value() / 100.0
            alpha[self._overlay_mask < threshold] = 0
        rgba = np.dstack([self._overlay_rgb, alpha])

        save_composite_geotiff(self._base_rgb, rgba, chosen, base_path)
