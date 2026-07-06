"""QThread wrapping core.processor, translating its injected progress callback into a Signal."""

from PySide6.QtCore import QThread, Signal


class ProcessingWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str)
    scene_found = Signal(list)

    def __init__(self, processor, task_type, params):
        super().__init__()
        self.processor = processor
        self.task_type = task_type
        self.params = params

    def run(self):
        try:
            if self.task_type == "search":
                self.progress.emit("Searching for scenes...")
                scenes = self.processor.search_scenes()
                self.scene_found.emit(scenes)
                self.finished.emit(True, f"Found {len(scenes)} scenes")

            elif self.task_type == "process":
                summary = self.processor.process_scene(
                    scene_index=self.params['scene_index'],
                    bbox=self.params['bbox'],
                    bands_to_load=self.params['bands_to_load'],
                    output=self.params['output'],
                    algorithms=self.params.get('algorithms', []),
                    save_bands=self.params.get('save_bands', False),
                    rgb=self.params.get('rgb', False),
                    bit_depth=self.params.get('bit_depth', 16),
                    ref_band=self.params.get('ref_band'),
                    progress=self.progress.emit,
                )
                self.finished.emit(True, summary)

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.progress.emit(f"ERROR: {error_detail}")
            self.finished.emit(False, str(e))
