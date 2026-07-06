"""QThread wrapping core.basemap, translating its injected progress callback into a Signal."""

from PySide6.QtCore import QThread, Signal

from sentinelgui.core.basemap import BasemapDownloader


class BasemapWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str, str)

    def __init__(self, bbox, zoom, source, output_path, reference_profile=None):
        super().__init__()
        self.bbox = bbox
        self.zoom = zoom
        self.source = source
        self.output_path = output_path
        self.reference_profile = reference_profile

    def run(self):
        try:
            if self.reference_profile:
                result, downloaded, failed, total = BasemapDownloader.download_basemap(
                    self.bbox,
                    self.zoom,
                    self.source,
                    self.output_path,
                    target_width=self.reference_profile['width'],
                    target_height=self.reference_profile['height'],
                    target_transform=self.reference_profile['transform'],
                    progress=self.progress.emit,
                )
            else:
                result, downloaded, failed, total = BasemapDownloader.download_basemap(
                    self.bbox,
                    self.zoom,
                    self.source,
                    self.output_path,
                    progress=self.progress.emit,
                )

            message = f"Downloaded {downloaded}/{total} tiles successfully"
            if failed > 0:
                message += f" ({failed} failed)"

            self.progress.emit(message)
            self.finished.emit(True, message, self.output_path)

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.progress.emit(f"ERROR: {error_detail}")
            self.finished.emit(False, str(e), "")
