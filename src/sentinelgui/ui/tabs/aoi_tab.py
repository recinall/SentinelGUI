"""Area-of-Interest tab.

Owns the WGS84 bounding-box fields, the center+window-in-km alternative, and the
GeoJSON-file picker, and exposes the parsed AOI to the controller via
:meth:`AoiTab.get_aoi`. The bbox path was lifted verbatim from the old
``Sentinel2GUI`` monolith; its defaults, validation, and error strings are
unchanged. Coordinate parsing and the km→degrees math live in the Qt-free
``core.geo`` module.
"""

import json

from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from sentinelgui.core.geo import bbox_from_center, parse_coordinate


class AoiTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        # -- Mode selector --
        mode_layout = QHBoxLayout()
        self.bbox_radio = QRadioButton("Bounding Box")
        self.bbox_radio.setChecked(True)
        self.center_radio = QRadioButton("Center + Window")
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.bbox_radio)
        mode_group.addButton(self.center_radio)
        mode_layout.addWidget(self.bbox_radio)
        mode_layout.addWidget(self.center_radio)
        mode_layout.addStretch()

        # -- Bounding-box inputs --
        bbox_group = QGroupBox("Bounding Box (WGS84)")
        bbox_layout = QVBoxLayout()

        coords_layout = QVBoxLayout()

        min_lon_layout = QHBoxLayout()
        min_lon_layout.addWidget(QLabel("Min Longitude:"))
        self.min_lon = QLineEdit()
        self.min_lon.setText("11.0")
        self.min_lon.setPlaceholderText("-180.000000 to 180.000000")
        min_lon_layout.addWidget(self.min_lon)

        min_lat_layout = QHBoxLayout()
        min_lat_layout.addWidget(QLabel("Min Latitude:"))
        self.min_lat = QLineEdit()
        self.min_lat.setText("46.0")
        self.min_lat.setPlaceholderText("-90.000000 to 90.000000")
        min_lat_layout.addWidget(self.min_lat)

        max_lon_layout = QHBoxLayout()
        max_lon_layout.addWidget(QLabel("Max Longitude:"))
        self.max_lon = QLineEdit()
        self.max_lon.setText("11.5")
        self.max_lon.setPlaceholderText("-180.000000 to 180.000000")
        max_lon_layout.addWidget(self.max_lon)

        max_lat_layout = QHBoxLayout()
        max_lat_layout.addWidget(QLabel("Max Latitude:"))
        self.max_lat = QLineEdit()
        self.max_lat.setText("46.5")
        self.max_lat.setPlaceholderText("-90.000000 to 90.000000")
        max_lat_layout.addWidget(self.max_lat)

        coords_layout.addLayout(min_lon_layout)
        coords_layout.addLayout(min_lat_layout)
        coords_layout.addLayout(max_lon_layout)
        coords_layout.addLayout(max_lat_layout)

        bbox_layout.addLayout(coords_layout)
        self.bbox_group = bbox_group
        bbox_group.setLayout(bbox_layout)

        # -- Center + window inputs --
        center_group = QGroupBox("Center + Window")
        center_layout = QVBoxLayout()

        center_lat_layout = QHBoxLayout()
        center_lat_layout.addWidget(QLabel("Center Latitude:"))
        self.center_lat = QLineEdit()
        self.center_lat.setText("46.25")
        self.center_lat.setPlaceholderText("decimal or DMS (e.g. 46°15'00\")")
        center_lat_layout.addWidget(self.center_lat)

        center_lon_layout = QHBoxLayout()
        center_lon_layout.addWidget(QLabel("Center Longitude:"))
        self.center_lon = QLineEdit()
        self.center_lon.setText("11.25")
        self.center_lon.setPlaceholderText("decimal or DMS (e.g. 11°15'00\")")
        center_lon_layout.addWidget(self.center_lon)

        width_km_layout = QHBoxLayout()
        width_km_layout.addWidget(QLabel("Width (km):"))
        self.width_km = QLineEdit()
        self.width_km.setText("10")
        self.width_km.setPlaceholderText("window width in km")
        width_km_layout.addWidget(self.width_km)

        height_km_layout = QHBoxLayout()
        height_km_layout.addWidget(QLabel("Height (km):"))
        self.height_km = QLineEdit()
        self.height_km.setText("10")
        self.height_km.setPlaceholderText("window height in km")
        height_km_layout.addWidget(self.height_km)

        center_layout.addLayout(center_lat_layout)
        center_layout.addLayout(center_lon_layout)
        center_layout.addLayout(width_km_layout)
        center_layout.addLayout(height_km_layout)

        self.center_group = center_group
        center_group.setLayout(center_layout)
        center_group.setEnabled(False)

        # -- GeoJSON alternative --
        geojson_group = QGroupBox("GeoJSON File (Alternative)")
        geojson_layout = QHBoxLayout()

        self.geojson_path = QLineEdit()
        self.geojson_path.setPlaceholderText("Path to GeoJSON file...")

        geojson_btn = QPushButton("Browse...")
        geojson_btn.clicked.connect(self.browse_geojson)

        geojson_layout.addWidget(self.geojson_path)
        geojson_layout.addWidget(geojson_btn)
        geojson_group.setLayout(geojson_layout)

        self.bbox_radio.toggled.connect(self._on_mode_changed)

        layout.addLayout(mode_layout)
        layout.addWidget(bbox_group)
        layout.addWidget(center_group)
        layout.addWidget(geojson_group)
        layout.addStretch()

    def _on_mode_changed(self, bbox_selected):
        self.bbox_group.setEnabled(bbox_selected)
        self.center_group.setEnabled(not bbox_selected)

    def browse_geojson(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select GeoJSON File", "", "GeoJSON Files (*.geojson *.json)"
        )
        if file_path:
            self.geojson_path.setText(file_path)

    def get_aoi(self):
        if self.geojson_path.text():
            with open(self.geojson_path.text()) as f:
                return json.load(f)
        if self.center_radio.isChecked():
            return self._get_center_aoi()
        return self._get_bbox_aoi()

    def _get_bbox_aoi(self):
        try:
            min_lon = parse_coordinate(self.min_lon.text())
            min_lat = parse_coordinate(self.min_lat.text())
            max_lon = parse_coordinate(self.max_lon.text())
            max_lat = parse_coordinate(self.max_lat.text())
            return self._build_bbox(min_lon, min_lat, max_lon, max_lat)
        except ValueError as e:
            raise ValueError(f"Invalid coordinates: {str(e)}") from e

    def _get_center_aoi(self):
        try:
            lat = parse_coordinate(self.center_lat.text())
            lon = parse_coordinate(self.center_lon.text())
            width_km = float(self.width_km.text().replace(",", "."))
            height_km = float(self.height_km.text().replace(",", "."))
            min_lon, min_lat, max_lon, max_lat = bbox_from_center(
                lat, lon, width_km, height_km
            )
            return self._build_bbox(min_lon, min_lat, max_lon, max_lat)
        except ValueError as e:
            raise ValueError(f"Invalid coordinates: {str(e)}") from e

    def _build_bbox(self, min_lon, min_lat, max_lon, max_lat):
        if not (-180 <= min_lon <= 180) or not (-180 <= max_lon <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        if not (-90 <= min_lat <= 90) or not (-90 <= max_lat <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if min_lon >= max_lon:
            raise ValueError("Min longitude must be less than max longitude")
        if min_lat >= max_lat:
            raise ValueError("Min latitude must be less than max latitude")

        return {"bbox": [min_lon, min_lat, max_lon, max_lat]}
