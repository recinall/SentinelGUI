"""QThread wrapping core.processor.search_scenes, translating its progress into Signals."""

from PySide6.QtCore import QThread, Signal


class SearchWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str)
    scene_found = Signal(list)

    def __init__(self, processor):
        super().__init__()
        self.processor = processor

    def run(self):
        try:
            self.progress.emit("Searching for scenes...")
            scenes = self.processor.search_scenes()
            self.scene_found.emit(scenes)
            self.finished.emit(True, f"Found {len(scenes)} scenes")

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.progress.emit(f"ERROR: {error_detail}")
            self.finished.emit(False, str(e))
