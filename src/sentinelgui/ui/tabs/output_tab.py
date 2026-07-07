"""Output-settings tab.

Owns the output directory, an optional project/location name, the file prefix, the
bit-depth selector, and the basemap source/zoom controls. Exposes them to the
controller through small getters (``output_dir``, ``project_name``, ``file_prefix``,
``bit_depth``, ``basemap_source``, ``basemap_zoom``);
the underlying widgets are stored under role-suffixed attribute names so they don't
shadow the getters. Lifted from the ``create_output_tab`` builder and the
``browse_output`` method of the old ``Sentinel2GUI``; defaults and ranges are unchanged.
The helper labels carry no inline literals — they are tagged ``role="hint"``/``"caption"``
so the theme's QSS (see :mod:`sentinelgui.ui.theme`) supplies their color and size.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class OutputTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        output_group = QGroupBox("Output Directory")
        output_layout = QHBoxLayout()

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output directory...")
        self.output_path_edit.setText(str(Path.home() / "sentinel_output"))

        output_btn = QPushButton("Browse...")
        output_btn.clicked.connect(self.browse_output)

        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(output_btn)
        output_group.setLayout(output_layout)

        project_group = QGroupBox("Project / location")
        project_layout = QVBoxLayout()

        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText("e.g. Vigneto-Trento (optional)")

        project_info = QLabel(
            "Groups outputs under a per-project, per-acquisition subfolder. "
            "Leave empty to use the scene's MGRS tile."
        )
        project_info.setProperty("role", "caption")

        project_layout.addWidget(self.project_name_edit)
        project_layout.addWidget(project_info)
        project_group.setLayout(project_layout)

        prefix_group = QGroupBox("File Prefix")
        prefix_layout = QVBoxLayout()

        self.file_prefix_edit = QLineEdit()
        self.file_prefix_edit.setText("sentinel")
        self.file_prefix_edit.setPlaceholderText("Prefix for output files...")

        prefix_info = QLabel("Output files will be named: prefix_ndvi.tif, prefix_ndwi.tif, etc.")
        prefix_info.setProperty("role", "caption")

        prefix_layout.addWidget(self.file_prefix_edit)
        prefix_layout.addWidget(prefix_info)
        prefix_group.setLayout(prefix_layout)

        depth_group = QGroupBox("Bit Depth")
        depth_layout = QHBoxLayout()

        self.bit_depth_combo = QComboBox()
        self.bit_depth_combo.addItem("8-bit (smallest files)", 8)
        self.bit_depth_combo.addItem("16-bit (recommended)", 16)
        self.bit_depth_combo.addItem("32-bit Float (highest precision)", 32)
        self.bit_depth_combo.setCurrentIndex(1)

        depth_layout.addWidget(QLabel("Output Bit Depth:"))
        depth_layout.addWidget(self.bit_depth_combo)
        depth_layout.addStretch()
        depth_group.setLayout(depth_layout)

        basemap_group = QGroupBox("Basemap Settings")
        basemap_layout = QVBoxLayout()

        basemap_info = QLabel("High-resolution reference imagery (non-radiometric)")
        basemap_info.setProperty("role", "hint")
        basemap_layout.addWidget(basemap_info)

        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Imagery Source:"))
        self.basemap_source_combo = QComboBox()
        self.basemap_source_combo.addItem("ESRI World Imagery (High Quality)", "esri")
        self.basemap_source_combo.addItem("Google Satellite", "google")
        self.basemap_source_combo.addItem("OpenStreetMap (Low Quality)", "osm")
        source_layout.addWidget(self.basemap_source_combo)
        source_layout.addStretch()

        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("Zoom Level:"))
        self.basemap_zoom_spin = QSpinBox()
        self.basemap_zoom_spin.setRange(10, 18)
        self.basemap_zoom_spin.setValue(16)
        self.basemap_zoom_spin.setToolTip(
            "Higher = better quality but slower download (10=lowest, 18=highest)"
        )
        zoom_layout.addWidget(self.basemap_zoom_spin)

        zoom_info = QLabel("Recommended: 14-16 for cities, 12-14 for rural areas")
        zoom_info.setProperty("role", "caption")
        zoom_layout.addWidget(zoom_info)
        zoom_layout.addStretch()

        basemap_layout.addLayout(source_layout)
        basemap_layout.addLayout(zoom_layout)
        basemap_group.setLayout(basemap_layout)

        layout.addWidget(output_group)
        layout.addWidget(project_group)
        layout.addWidget(prefix_group)
        layout.addWidget(depth_group)
        layout.addWidget(basemap_group)
        layout.addStretch()

    def browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.output_path_edit.setText(dir_path)

    def output_dir(self) -> str:
        return self.output_path_edit.text()

    def project_name(self) -> str:
        return self.project_name_edit.text()

    def file_prefix(self) -> str:
        return self.file_prefix_edit.text()

    def bit_depth(self) -> int:
        return self.bit_depth_combo.currentData()

    def basemap_source(self) -> str:
        return self.basemap_source_combo.currentData()

    def basemap_zoom(self) -> int:
        return self.basemap_zoom_spin.value()
