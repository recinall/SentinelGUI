"""Processing-log panel.

A ``QGroupBox`` titled "Processing Log" wrapping a read-only ``QTextEdit`` and owning
the timestamped :meth:`log` append. Lifted verbatim from the inline log group and the
``log`` method of the old ``Sentinel2GUI``; the controller's ``log`` now delegates here
and worker ``progress`` signals connect to it unchanged.
"""

from datetime import datetime

from PySide6.QtWidgets import QGroupBox, QTextEdit, QVBoxLayout


class LogPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Processing Log", parent)

        layout = QVBoxLayout(self)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)

        layout.addWidget(self.log_text)

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
