import sys
from pathlib import Path
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
                               QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox, QTextEdit,
                               QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
                               QProgressBar, QMessageBox, QSplitter, QHeaderView, QScrollArea)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
import json
from sentinelgui.core.models import ProcessingParams
from sentinelgui.core.processor import Sentinel2COGProcessor
from sentinelgui.workers.basemap import BasemapWorker
from sentinelgui.workers.processing import ProcessingWorker
from rasterio.crs import CRS


class Sentinel2GUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = None
        self.scenes = []
        self.processing_thread = None
        self.basemap_thread = None
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Sentinel-2 COG Processor - Multi-Index Analysis")
        self.setGeometry(100, 100, 1300, 850)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        splitter = QSplitter(Qt.Vertical)
        
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        
        tab_widget = QTabWidget()
        tab_widget.addTab(self.create_aoi_tab(), "Area of Interest")
        tab_widget.addTab(self.create_search_tab(), "Search Parameters")
        tab_widget.addTab(self.create_processing_tab(), "Processing Options")
        tab_widget.addTab(self.create_output_tab(), "Output Settings")
        
        top_layout.addWidget(tab_widget)
        
        btn_layout = QHBoxLayout()
        
        self.search_btn = QPushButton("🔍 Search Scenes")
        self.search_btn.clicked.connect(self.search_scenes)
        self.search_btn.setMinimumHeight(40)
        
        self.basemap_btn = QPushButton("🗺️ Download Basemap")
        self.basemap_btn.clicked.connect(self.download_basemap)
        self.basemap_btn.setMinimumHeight(40)
        self.basemap_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        
        self.process_btn = QPushButton("⚙️ Process Selected Scene")
        self.process_btn.clicked.connect(self.process_scene)
        self.process_btn.setEnabled(False)
        self.process_btn.setMinimumHeight(40)
        
        btn_layout.addWidget(self.search_btn)
        btn_layout.addWidget(self.basemap_btn)
        btn_layout.addWidget(self.process_btn)
        
        top_layout.addLayout(btn_layout)
        
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout()
        
        self.scene_table = QTableWidget()
        self.scene_table.setColumnCount(6)
        self.scene_table.setHorizontalHeaderLabels([
            "Index", "Date/Time", "Cloud Cover %", "MGRS Tile", "Scene ID", "Platform"
        ])
        self.scene_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.scene_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.scene_table.setSelectionMode(QTableWidget.SingleSelection)
        self.scene_table.itemSelectionChanged.connect(self.on_scene_selected)
        
        results_layout.addWidget(self.scene_table)
        results_group.setLayout(results_layout)
        
        log_group = QGroupBox("Processing Log")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        bottom_layout.addWidget(results_group)
        bottom_layout.addWidget(log_group)
        bottom_layout.addWidget(self.progress_bar)
        
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        
        self.log("Application started. Configure search parameters and click 'Search Scenes'.")
        
    def create_aoi_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
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
        
        return widget
    
    def create_search_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        date_group = QGroupBox("Date Range")
        date_layout = QHBoxLayout()
        
        start_layout = QVBoxLayout()
        start_layout.addWidget(QLabel("Start Date (YYYY-MM-DD):"))
        self.date_start = QLineEdit()
        self.date_start.setText((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))
        start_layout.addWidget(self.date_start)
        
        end_layout = QVBoxLayout()
        end_layout.addWidget(QLabel("End Date (YYYY-MM-DD):"))
        self.date_end = QLineEdit()
        self.date_end.setText(datetime.now().strftime("%Y-%m-%d"))
        end_layout.addWidget(self.date_end)
        
        date_layout.addLayout(start_layout)
        date_layout.addLayout(end_layout)
        date_group.setLayout(date_layout)
        
        cloud_group = QGroupBox("Cloud Cover Filter")
        cloud_layout = QHBoxLayout()
        
        cloud_layout.addWidget(QLabel("Maximum Cloud Cover (%):"))
        self.cloud_cover = QDoubleSpinBox()
        self.cloud_cover.setRange(0, 100)
        self.cloud_cover.setValue(20.0)
        self.cloud_cover.setSingleStep(5.0)
        
        cloud_layout.addWidget(self.cloud_cover)
        cloud_layout.addStretch()
        cloud_group.setLayout(cloud_layout)
        
        layout.addWidget(date_group)
        layout.addWidget(cloud_group)
        layout.addStretch()
        
        return widget
    
    def create_processing_tab(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        
        layout = QVBoxLayout(widget)
        
        indices_group = QGroupBox("Spectral Indices (Select Multiple)")
        indices_layout = QVBoxLayout()
        
        info_label = QLabel("Select one or more spectral indices to calculate:")
        info_label.setStyleSheet("color: #666; font-style: italic;")
        indices_layout.addWidget(info_label)
        
        self.index_checkboxes = {}
        
        index_descriptions = {
            'NDVI': 'Normalized Difference Vegetation Index - Vegetation health',
            'NDSI': 'Normalized Difference Snow Index - Snow/ice detection',
            'SI': 'Soil Index - Bare soil identification',
            'NDWI': 'Normalized Difference Water Index - Water bodies',
            'BI': 'Bareness Index - Soil exposure',
            'EVI': 'Enhanced Vegetation Index - Improved vegetation sensitivity',
            'SAVI': 'Soil Adjusted Vegetation Index - Reduces soil brightness',
            'NDRE': 'Normalized Difference Red Edge - Chlorophyll content',
            'MSI': 'Moisture Stress Index - Plant water stress',
            'GNDVI': 'Green NDVI - Photosynthetic activity',
            'IISV': 'Integrated Index for Soil and Vegetation - Combined analysis'
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
            
            desc_label = QLabel(index_descriptions.get(algo_key, ''))
            desc_label.setStyleSheet("color: #666; font-size: 10px; margin-left: 20px;")
            desc_label.setWordWrap(True)
            
            bands_label = QLabel(f"Required bands: {', '.join([b.upper() for b in algo_info['bands']])}")
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
        
        ref_info = QLabel("All bands will be resampled to match the resolution and grid of the reference band:")
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
        
        return scroll
    
    def select_all_indices(self):
        for cb in self.index_checkboxes.values():
            cb.setChecked(True)
        self.log("Selected all spectral indices")
    
    def clear_all_indices(self):
        for cb in self.index_checkboxes.values():
            cb.setChecked(False)
        self.log("Cleared all spectral indices")
    
    def create_output_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        output_group = QGroupBox("Output Directory")
        output_layout = QHBoxLayout()
        
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Select output directory...")
        self.output_path.setText(str(Path.home() / "sentinel_output"))
        
        output_btn = QPushButton("Browse...")
        output_btn.clicked.connect(self.browse_output)
        
        output_layout.addWidget(self.output_path)
        output_layout.addWidget(output_btn)
        output_group.setLayout(output_layout)
        
        prefix_group = QGroupBox("File Prefix")
        prefix_layout = QVBoxLayout()
        
        self.file_prefix = QLineEdit()
        self.file_prefix.setText("sentinel")
        self.file_prefix.setPlaceholderText("Prefix for output files...")
        
        prefix_info = QLabel("Output files will be named: prefix_ndvi.tif, prefix_ndwi.tif, etc.")
        prefix_info.setStyleSheet("color: #666; font-size: 10px;")
        
        prefix_layout.addWidget(self.file_prefix)
        prefix_layout.addWidget(prefix_info)
        prefix_group.setLayout(prefix_layout)
        
        depth_group = QGroupBox("Bit Depth")
        depth_layout = QHBoxLayout()
        
        self.bit_depth = QComboBox()
        self.bit_depth.addItem("8-bit (smallest files)", 8)
        self.bit_depth.addItem("16-bit (recommended)", 16)
        self.bit_depth.addItem("32-bit Float (highest precision)", 32)
        self.bit_depth.setCurrentIndex(1)
        
        depth_layout.addWidget(QLabel("Output Bit Depth:"))
        depth_layout.addWidget(self.bit_depth)
        depth_layout.addStretch()
        depth_group.setLayout(depth_layout)
        
        basemap_group = QGroupBox("Basemap Settings")
        basemap_layout = QVBoxLayout()
        
        basemap_info = QLabel("High-resolution reference imagery (non-radiometric)")
        basemap_info.setStyleSheet("color: #666; font-style: italic;")
        basemap_layout.addWidget(basemap_info)
        
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Imagery Source:"))
        self.basemap_source = QComboBox()
        self.basemap_source.addItem("ESRI World Imagery (High Quality)", "esri")
        self.basemap_source.addItem("Google Satellite", "google")
        self.basemap_source.addItem("OpenStreetMap (Low Quality)", "osm")
        source_layout.addWidget(self.basemap_source)
        source_layout.addStretch()
        
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("Zoom Level:"))
        self.basemap_zoom = QSpinBox()
        self.basemap_zoom.setRange(10, 18)
        self.basemap_zoom.setValue(16)
        self.basemap_zoom.setToolTip("Higher = better quality but slower download (10=lowest, 18=highest)")
        zoom_layout.addWidget(self.basemap_zoom)
        
        zoom_info = QLabel("Recommended: 14-16 for cities, 12-14 for rural areas")
        zoom_info.setStyleSheet("color: #999; font-size: 10px;")
        zoom_layout.addWidget(zoom_info)
        zoom_layout.addStretch()
        
        basemap_layout.addLayout(source_layout)
        basemap_layout.addLayout(zoom_layout)
        basemap_group.setLayout(basemap_layout)
        
        layout.addWidget(output_group)
        layout.addWidget(prefix_group)
        layout.addWidget(depth_group)
        layout.addWidget(basemap_group)
        layout.addStretch()
        
        return widget
    
    def browse_geojson(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select GeoJSON File", "", "GeoJSON Files (*.geojson *.json)"
        )
        if file_path:
            self.geojson_path.setText(file_path)
    
    def browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory"
        )
        if dir_path:
            self.output_path.setText(dir_path)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
    
    def get_aoi(self):
        if self.geojson_path.text():
            with open(self.geojson_path.text(), 'r') as f:
                return json.load(f)
        else:
            try:
                min_lon = float(self.min_lon.text().replace(',', '.'))
                min_lat = float(self.min_lat.text().replace(',', '.'))
                max_lon = float(self.max_lon.text().replace(',', '.'))
                max_lat = float(self.max_lat.text().replace(',', '.'))
                
                if not (-180 <= min_lon <= 180) or not (-180 <= max_lon <= 180):
                    raise ValueError("Longitude must be between -180 and 180")
                if not (-90 <= min_lat <= 90) or not (-90 <= max_lat <= 90):
                    raise ValueError("Latitude must be between -90 and 90")
                if min_lon >= max_lon:
                    raise ValueError("Min longitude must be less than max longitude")
                if min_lat >= max_lat:
                    raise ValueError("Min latitude must be less than max latitude")
                
                return {
                    'bbox': [min_lon, min_lat, max_lon, max_lat]
                }
            except ValueError as e:
                raise ValueError(f"Invalid coordinates: {str(e)}")
    
    def search_scenes(self):
        try:
            aoi = self.get_aoi()
            
            self.processor = Sentinel2COGProcessor(
                aoi=aoi,
                date_start=self.date_start.text(),
                date_end=self.date_end.text(),
                cloud_cover_max=self.cloud_cover.value()
            )
            
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.search_btn.setEnabled(False)
            
            self.processing_thread = ProcessingWorker(self.processor, "search", {})
            self.processing_thread.progress.connect(self.log)
            self.processing_thread.scene_found.connect(self.populate_scene_table)
            self.processing_thread.finished.connect(self.on_search_finished)
            self.processing_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Search failed: {str(e)}")
            self.log(f"Error: {str(e)}")
    
    def populate_scene_table(self, scenes):
        self.scenes = scenes
        self.scene_table.setRowCount(len(scenes))
        
        for idx, scene in enumerate(scenes):
            props = scene['properties']
            
            self.scene_table.setItem(idx, 0, QTableWidgetItem(str(idx)))
            self.scene_table.setItem(idx, 1, QTableWidgetItem(props.get('datetime', 'N/A')))
            self.scene_table.setItem(idx, 2, QTableWidgetItem(f"{props.get('eo:cloud_cover', 0):.1f}"))
            
            mgrs = f"{props.get('mgrs:utm_zone', '')}{props.get('mgrs:latitude_band', '')}{props.get('mgrs:grid_square', '')}"
            self.scene_table.setItem(idx, 3, QTableWidgetItem(mgrs))
            self.scene_table.setItem(idx, 4, QTableWidgetItem(props.get('sentinel:product_id', 'N/A')))
            self.scene_table.setItem(idx, 5, QTableWidgetItem(props.get('platform', 'N/A')))
        
        if scenes:
            self.scene_table.selectRow(0)
    
    def on_scene_selected(self):
        if self.scene_table.selectedItems():
            self.process_btn.setEnabled(True)
    
    def on_search_finished(self, success, message):
        self.progress_bar.setVisible(False)
        self.search_btn.setEnabled(True)
        self.log(message)
        
        if success and self.scenes:
            QMessageBox.information(self, "Success", message)
        elif not self.scenes:
            QMessageBox.warning(self, "No Results", "No scenes found matching your criteria.")
    
    def process_scene(self):
        try:
            if not self.scene_table.selectedItems():
                QMessageBox.warning(self, "Warning", "Please select a scene to process.")
                return
            
            scene_index = int(self.scene_table.selectedItems()[0].text())
            
            algorithms = []
            for algo_key, cb in self.index_checkboxes.items():
                if cb.isChecked():
                    algorithms.append(algo_key)
            
            bands_to_load = set()
            
            for algorithm in algorithms:
                required = Sentinel2COGProcessor.ALGORITHMS[algorithm]['bands']
                bands_to_load.update(required)
            
            for band_key, cb in self.band_checkboxes.items():
                if cb.isChecked():
                    bands_to_load.add(band_key)
            
            if self.rgb_cb.isChecked():
                bands_to_load.update(['b04', 'b03', 'b02'])
            
            if not bands_to_load and not algorithms:
                QMessageBox.warning(self, "Warning", 
                    "Please select at least one processing option:\n"
                    "- One or more spectral indices\n"
                    "- Individual bands\n"
                    "- RGB composite")
                return
            
            output_dir = Path(self.output_path.text())
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_base = output_dir / self.file_prefix.text()
            
            bbox = self.processor.get_bbox_from_aoi()
            
            params = ProcessingParams(
                scene_index=scene_index,
                bbox=bbox,
                bands_to_load=bands_to_load,
                output=str(output_base),
                algorithms=algorithms,
                save_bands=self.save_bands_cb.isChecked(),
                rgb=self.rgb_cb.isChecked(),
                bit_depth=self.bit_depth.currentData(),
                ref_band=self.ref_band_combo.currentData(),
            )
            
            self.log(f"Starting processing with {len(algorithms)} indices and {len(bands_to_load)} bands...")
            if algorithms:
                self.log(f"Indices to calculate: {', '.join(algorithms)}")
            
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.process_btn.setEnabled(False)
            self.search_btn.setEnabled(False)
            
            self.processing_thread = ProcessingWorker(self.processor, "process", params)
            self.processing_thread.progress.connect(self.log)
            self.processing_thread.finished.connect(self.on_process_finished)
            self.processing_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Processing failed: {str(e)}")
            self.log(f"Error: {str(e)}")
    
    def on_process_finished(self, success, message):
        self.progress_bar.setVisible(False)
        self.process_btn.setEnabled(True)
        self.search_btn.setEnabled(True)
        self.basemap_btn.setEnabled(True)
        self.log(message)
        
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(self, "Error", f"Processing failed:\n{message}")
    
    def download_basemap(self):
        try:
            aoi = self.get_aoi()
            
            if 'bbox' in aoi:
                bbox = aoi['bbox']
            else:
                from shapely.geometry import shape
                geom = shape(aoi if aoi['type'] != 'Feature' else aoi['geometry'])
                bbox = geom.bounds
            
            zoom = self.basemap_zoom.value()
            source = self.basemap_source.currentData()
            
            output_dir = Path(self.output_path.text())
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / f"{self.file_prefix.text()}_basemap_{source}_z{zoom}.tif"
            
            reference_profile = None
            profile_file = output_dir / f"{self.file_prefix.text()}_reference_profile.json"
            
            if profile_file.exists():
                try:
                    with open(profile_file, 'r') as f:
                        profile_data = json.load(f)
                    
                    from rasterio.transform import Affine
                    reference_profile = {
                        'width': profile_data['width'],
                        'height': profile_data['height'],
                        'transform': Affine(*profile_data['transform'][:6]),
                        'crs': CRS.from_string(profile_data['crs'])
                    }
                    
                    reply = QMessageBox.question(
                        self, 
                        "Download Basemap",
                        f"Found reference profile from previous Sentinel processing.\n"
                        f"Grid: {reference_profile['width']}x{reference_profile['height']} pixels\n\n"
                        f"Align basemap to this grid?\n"
                        f"(This ensures perfect overlay with Sentinel data)",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    
                    if reply != QMessageBox.Yes:
                        reference_profile = None
                
                except Exception as e:
                    self.log(f"Could not load reference profile: {e}")
                    reference_profile = None
            
            if not reference_profile:
                reply = QMessageBox.question(
                    self, 
                    "Download Basemap",
                    f"This will download high-resolution imagery from {source.upper()}\n"
                    f"at zoom level {zoom} for the selected area.\n\n"
                    f"Output: {output_path.name}\n\n"
                    f"Note: To align with Sentinel data, process Sentinel first.\n\n"
                    f"Continue?",
                    QMessageBox.Yes | QMessageBox.No
                )
            else:
                reply = QMessageBox.Yes
            
            if reply != QMessageBox.Yes:
                return
            
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.search_btn.setEnabled(False)
            self.process_btn.setEnabled(False)
            self.basemap_btn.setEnabled(False)
            
            self.basemap_thread = BasemapWorker(bbox, zoom, source, str(output_path), reference_profile)
            self.basemap_thread.progress.connect(self.log)
            self.basemap_thread.finished.connect(self.on_basemap_finished)
            self.basemap_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Basemap download failed: {str(e)}")
            self.log(f"Error: {str(e)}")
    
    def on_basemap_finished(self, success, message, output_path):
        self.progress_bar.setVisible(False)
        self.search_btn.setEnabled(True)
        self.process_btn.setEnabled(bool(self.scenes))
        self.basemap_btn.setEnabled(True)
        self.log(message)
        
        if success:
            QMessageBox.information(
                self, 
                "Success", 
                f"{message}\n\nSaved to:\n{output_path}"
            )
        else:
            QMessageBox.critical(self, "Error", f"Basemap download failed:\n{message}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = Sentinel2GUI()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()