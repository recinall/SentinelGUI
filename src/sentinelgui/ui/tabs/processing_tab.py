"""Processing-options tab.

Owns the spectral-index checkboxes, the additional-band checkboxes, the reference-band
selector and the extra output toggles (save-bands / RGB), all inside a scroll area.
Exposes the user's selection to the controller through small getters; the controller
still composes ``bands_to_load`` against the core ``ALGORITHMS`` registry, so this tab
stays ignorant of core. The Select/Clear-All buttons live here and report their action
through the :attr:`log_requested` signal (the controller connects it to its log panel),
preserving the exact log lines the monolith emitted.

Lifted verbatim from the ``create_processing_tab`` builder and the
``select_all_indices``/``clear_all_indices`` methods of the old ``Sentinel2GUI``.
Inline styles (``#666``/``#999``) ride along unchanged; removing them belongs to the
theme slice.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sentinelgui.core.processor import Sentinel2COGProcessor


class ProcessingTab(QScrollArea):
    log_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        widget = QWidget()
        self.setWidget(widget)
        self.setWidgetResizable(True)

        layout = QVBoxLayout(widget)

        indices_group = QGroupBox("Spectral Indices (Select Multiple)")
        indices_layout = QVBoxLayout()

        info_label = QLabel("Select one or more spectral indices to calculate:")
        info_label.setStyleSheet("color: #666; font-style: italic;")
        indices_layout.addWidget(info_label)

        self.index_checkboxes = {}

        index_descriptions = {
            "NDVI": "Normalized Difference Vegetation Index - Vegetation health",
            "NDSI": "Normalized Difference Snow Index - Snow/ice detection",
            "SI": "Soil Index - Bare soil identification",
            "NDWI": "Normalized Difference Water Index - Water bodies",
            "BI": "Bareness Index - Soil exposure",
            "EVI": "Enhanced Vegetation Index - Improved vegetation sensitivity",
            "SAVI": "Soil Adjusted Vegetation Index - Reduces soil brightness",
            "NDRE": "Normalized Difference Red Edge - Chlorophyll content",
            "MSI": "Moisture Stress Index - Plant water stress",
            "GNDVI": "Green NDVI - Photosynthetic activity",
            "IISV": "Integrated Index for Soil and Vegetation - Combined analysis",
        }

        grid_layout = QVBoxLayout()
        row_layout = None

        for idx, (algo_key, algo_info) in enumerate(Sentinel2COGProcessor.ALGORITHMS.items()):
            if idx % 2 == 0:
                row_layout = QHBoxLayout()
                grid_layout.addLayout(row_layout)

            cb_layout = QVBoxLayout()
            cb = QCheckBox(algo_key)
            cb.setStyleSheet("font-weight: bold;")

            desc_label = QLabel(index_descriptions.get(algo_key, ""))
            desc_label.setStyleSheet("color: #666; font-size: 10px; margin-left: 20px;")
            desc_label.setWordWrap(True)

            bands_label = QLabel(
                f"Required bands: {', '.join([b.upper() for b in algo_info['bands']])}"
            )
            bands_label.setStyleSheet("color: #999; font-size: 9px; margin-left: 20px;")

            cb_layout.addWidget(cb)
            cb_layout.addWidget(desc_label)
            cb_layout.addWidget(bands_label)
            cb_layout.addSpacing(5)

            self.index_checkboxes[algo_key] = cb
            row_layout.addLayout(cb_layout)

        if row_layout and row_layout.count() == 1:
            row_layout.addStretch()

        indices_layout.addLayout(grid_layout)

        select_btns = QHBoxLayout()
        select_all_btn = QPushButton("Select All Indices")
        select_all_btn.clicked.connect(self.select_all_indices)
        clear_all_btn = QPushButton("Clear All Indices")
        clear_all_btn.clicked.connect(self.clear_all_indices)

        select_btns.addWidget(select_all_btn)
        select_btns.addWidget(clear_all_btn)
        select_btns.addStretch()

        indices_layout.addLayout(select_btns)
        indices_group.setLayout(indices_layout)

        bands_group = QGroupBox("Additional Band Selection")
        bands_layout = QVBoxLayout()

        band_info = QLabel("Select individual bands to save (optional):")
        band_info.setStyleSheet("color: #666; font-style: italic;")
        bands_layout.addWidget(band_info)

        self.band_checkboxes = {}
        band_grid = QHBoxLayout()
        col_layout = QVBoxLayout()

        for idx, (band_key, band_name) in enumerate(Sentinel2COGProcessor.BAND_MAPPING.items()):
            cb = QCheckBox(f"{band_key.upper()} ({band_name})")
            self.band_checkboxes[band_key] = cb
            col_layout.addWidget(cb)

            if (idx + 1) % 4 == 0:
                band_grid.addLayout(col_layout)
                col_layout = QVBoxLayout()

        if col_layout.count() > 0:
            band_grid.addLayout(col_layout)

        bands_layout.addLayout(band_grid)
        bands_group.setLayout(bands_layout)

        ref_band_group = QGroupBox("Reference Band")
        ref_band_layout = QVBoxLayout()

        ref_info = QLabel(
            "All bands will be resampled to match the resolution and grid of the reference band:"
        )
        ref_info.setWordWrap(True)
        ref_band_layout.addWidget(ref_info)

        self.ref_band_combo = QComboBox()
        self.ref_band_combo.addItem("Auto (first loaded band)", None)
        for band_key, band_name in Sentinel2COGProcessor.BAND_MAPPING.items():
            self.ref_band_combo.addItem(f"{band_key.upper()} - {band_name}", band_key)

        ref_band_layout.addWidget(self.ref_band_combo)
        ref_band_group.setLayout(ref_band_layout)

        options_group = QGroupBox("Additional Options")
        options_layout = QVBoxLayout()

        self.save_bands_cb = QCheckBox("Save Individual Bands")
        self.save_bands_cb.setToolTip("Save each band as a separate GeoTIFF file")

        self.rgb_cb = QCheckBox("Create RGB Composite (B04, B03, B02)")
        self.rgb_cb.setToolTip("Generate a true color composite image")

        options_layout.addWidget(self.save_bands_cb)
        options_layout.addWidget(self.rgb_cb)
        options_group.setLayout(options_layout)

        layout.addWidget(indices_group)
        layout.addWidget(bands_group)
        layout.addWidget(ref_band_group)
        layout.addWidget(options_group)
        layout.addStretch()

    def select_all_indices(self):
        for cb in self.index_checkboxes.values():
            cb.setChecked(True)
        self.log_requested.emit("Selected all spectral indices")

    def clear_all_indices(self):
        for cb in self.index_checkboxes.values():
            cb.setChecked(False)
        self.log_requested.emit("Cleared all spectral indices")

    def selected_algorithms(self) -> list[str]:
        return [key for key, cb in self.index_checkboxes.items() if cb.isChecked()]

    def selected_bands(self) -> set[str]:
        return {key for key, cb in self.band_checkboxes.items() if cb.isChecked()}

    def ref_band(self) -> str | None:
        return self.ref_band_combo.currentData()

    def save_bands(self) -> bool:
        return self.save_bands_cb.isChecked()

    def rgb(self) -> bool:
        return self.rgb_cb.isChecked()
