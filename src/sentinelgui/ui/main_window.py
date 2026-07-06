import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from rasterio.crs import CRS

from sentinelgui.core.models import ProcessingParams
from sentinelgui.core.processor import Sentinel2COGProcessor
from sentinelgui.ui import theme
from sentinelgui.ui.tabs.aoi_tab import AoiTab
from sentinelgui.ui.tabs.output_tab import OutputTab
from sentinelgui.ui.tabs.processing_tab import ProcessingTab
from sentinelgui.ui.tabs.search_tab import SearchTab
from sentinelgui.ui.widgets.log_panel import LogPanel
from sentinelgui.ui.widgets.scene_table import SceneTable
from sentinelgui.workers.basemap import BasemapWorker
from sentinelgui.workers.processing import ProcessingWorker
from sentinelgui.workers.search import SearchWorker


class Sentinel2GUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = None
        self.scenes = []
        self.search_thread = None
        self.processing_thread = None
        self.basemap_thread = None
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Sentinel-2 COG Processor - Multi-Index Analysis")
        self.setGeometry(100, 100, 1300, 850)

        self._create_menu_bar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        splitter = QSplitter(Qt.Vertical)
        
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        
        self.aoi_tab = AoiTab()
        self.search_tab = SearchTab()
        self.processing_tab = ProcessingTab()
        self.processing_tab.log_requested.connect(self.log)
        self.output_tab = OutputTab()

        tab_widget = QTabWidget()
        tab_widget.addTab(self.aoi_tab, "Area of Interest")
        tab_widget.addTab(self.search_tab, "Search Parameters")
        tab_widget.addTab(self.processing_tab, "Processing Options")
        tab_widget.addTab(self.output_tab, "Output Settings")
        
        top_layout.addWidget(tab_widget)
        
        btn_layout = QHBoxLayout()
        
        self.search_btn = QPushButton("🔍 Search Scenes")
        self.search_btn.clicked.connect(self.search_scenes)
        self.search_btn.setMinimumHeight(40)
        
        self.basemap_btn = QPushButton("🗺️ Download Basemap")
        self.basemap_btn.clicked.connect(self.download_basemap)
        self.basemap_btn.setMinimumHeight(40)
        self.basemap_btn.setObjectName("accent")
        
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

        self.scene_table = SceneTable()
        self.scene_table.itemSelectionChanged.connect(self.on_scene_selected)

        results_layout.addWidget(self.scene_table)
        results_group.setLayout(results_layout)

        self.log_panel = LogPanel()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)

        bottom_layout.addWidget(results_group)
        bottom_layout.addWidget(self.log_panel)
        bottom_layout.addWidget(self.progress_bar)
        
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        
        self.log("Application started. Configure search parameters and click 'Search Scenes'.")
        
    def _create_menu_bar(self):
        view_menu = self.menuBar().addMenu("View")
        self.dark_mode_action = view_menu.addAction("Dark Mode")
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(theme.current_mode() == "dark")
        self.dark_mode_action.toggled.connect(self.toggle_theme)

    def toggle_theme(self, checked):
        theme.load_theme(QApplication.instance(), "dark" if checked else "light")

    def log(self, message):
        self.log_panel.log(message)

    def search_scenes(self):
        try:
            aoi = self.aoi_tab.get_aoi()

            self.processor = Sentinel2COGProcessor(
                aoi=aoi,
                **self.search_tab.get_search_params(),
            )
            
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.search_btn.setEnabled(False)
            
            self.search_thread = SearchWorker(self.processor)
            self.search_thread.progress.connect(self.log)
            self.search_thread.scene_found.connect(self.populate_scene_table)
            self.search_thread.finished.connect(self.on_search_finished)
            self.search_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Search failed: {str(e)}")
            self.log(f"Error: {str(e)}")
    
    def populate_scene_table(self, scenes):
        self.scenes = scenes
        self.scene_table.populate(scenes)
    
    def on_scene_selected(self):
        if self.scene_table.has_selection():
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
            scene_index = self.scene_table.selected_index()
            if scene_index is None:
                QMessageBox.warning(self, "Warning", "Please select a scene to process.")
                return
            
            algorithms = self.processing_tab.selected_algorithms()

            bands_to_load = set()

            for algorithm in algorithms:
                required = Sentinel2COGProcessor.ALGORITHMS[algorithm]['bands']
                bands_to_load.update(required)

            bands_to_load.update(self.processing_tab.selected_bands())

            if self.processing_tab.rgb():
                bands_to_load.update(['b04', 'b03', 'b02'])
            
            if not bands_to_load and not algorithms:
                QMessageBox.warning(self, "Warning", 
                    "Please select at least one processing option:\n"
                    "- One or more spectral indices\n"
                    "- Individual bands\n"
                    "- RGB composite")
                return
            
            output_dir = Path(self.output_tab.output_dir())
            output_dir.mkdir(parents=True, exist_ok=True)

            output_base = output_dir / self.output_tab.file_prefix()

            bbox = self.processor.get_bbox_from_aoi()
            
            params = ProcessingParams(
                scene_index=scene_index,
                bbox=bbox,
                bands_to_load=bands_to_load,
                output=str(output_base),
                algorithms=algorithms,
                save_bands=self.processing_tab.save_bands(),
                rgb=self.processing_tab.rgb(),
                bit_depth=self.output_tab.bit_depth(),
                ref_band=self.processing_tab.ref_band(),
            )
            
            self.log(
                f"Starting processing with {len(algorithms)} indices "
                f"and {len(bands_to_load)} bands..."
            )
            if algorithms:
                self.log(f"Indices to calculate: {', '.join(algorithms)}")
            
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.process_btn.setEnabled(False)
            self.search_btn.setEnabled(False)
            
            self.processing_thread = ProcessingWorker(self.processor, params)
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
            aoi = self.aoi_tab.get_aoi()
            
            if 'bbox' in aoi:
                bbox = aoi['bbox']
            else:
                from shapely.geometry import shape
                geom = shape(aoi if aoi['type'] != 'Feature' else aoi['geometry'])
                bbox = geom.bounds
            
            zoom = self.output_tab.basemap_zoom()
            source = self.output_tab.basemap_source()

            output_dir = Path(self.output_tab.output_dir())
            output_dir.mkdir(parents=True, exist_ok=True)

            output_path = (
                output_dir / f"{self.output_tab.file_prefix()}_basemap_{source}_z{zoom}.tif"
            )

            reference_profile = None
            profile_file = output_dir / f"{self.output_tab.file_prefix()}_reference_profile.json"
            
            if profile_file.exists():
                try:
                    with open(profile_file) as f:
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
                        f"Grid: {reference_profile['width']}x{reference_profile['height']} "
                        f"pixels\n\n"
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
            
            self.basemap_thread = BasemapWorker(
                bbox, zoom, source, str(output_path), reference_profile
            )
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