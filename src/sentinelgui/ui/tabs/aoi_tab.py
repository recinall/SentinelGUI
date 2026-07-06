"""Area-of-Interest tab.

Owns the WGS84 bounding-box fields and the alternative GeoJSON-file picker, and
exposes the parsed AOI to the controller via :meth:`AoiTab.get_aoi`. Lifted verbatim
from the ``create_aoi_tab`` builder and the ``get_aoi``/``browse_geojson`` methods of
the old ``Sentinel2GUI`` monolith; behavior (defaults, validation, error strings) is
unchanged.
"""

import json

from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sentinelgui.core.geo import parse_coordinate


class AoiTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

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
        bbox_group.setLayout(bbox_layout)

        geojson_group = QGroupBox("GeoJSON File (Alternative)")
        geojson_layout = QHBoxLayout()

        self.geojson_path = QLineEdit()
        self.geojson_path.setPlaceholderText("Path to GeoJSON file...")

        geojson_btn = QPushButton("Browse...")
        geojson_btn.clicked.connect(self.browse_geojson)

        geojson_layout.addWidget(self.geojson_path)
        geojson_layout.addWidget(geojson_btn)
        geojson_group.setLayout(geojson_layout)

        layout.addWidget(bbox_group)
        layout.addWidget(geojson_group)
        layout.addStretch()

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
        else:
            try:
                min_lon = parse_coordinate(self.min_lon.text())
                min_lat = parse_coordinate(self.min_lat.text())
                max_lon = parse_coordinate(self.max_lon.text())
                max_lat = parse_coordinate(self.max_lat.text())

                if not (-180 <= min_lon <= 180) or not (-180 <= max_lon <= 180):
                    raise ValueError("Longitude must be between -180 and 180")
                if not (-90 <= min_lat <= 90) or not (-90 <= max_lat <= 90):
                    raise ValueError("Latitude must be between -90 and 90")
                if min_lon >= max_lon:
                    raise ValueError("Min longitude must be less than max longitude")
                if min_lat >= max_lat:
                    raise ValueError("Min latitude must be less than max latitude")

                return {"bbox": [min_lon, min_lat, max_lon, max_lat]}
            except ValueError as e:
                raise ValueError(f"Invalid coordinates: {str(e)}") from e
