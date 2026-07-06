"""Search-parameters tab.

Owns the date-range fields and the maximum-cloud-cover filter, and hands the
controller the exact keyword arguments the processor constructor expects via
:meth:`SearchTab.get_search_params`. Lifted verbatim from the ``create_search_tab``
builder of the old ``Sentinel2GUI`` monolith; defaults and behavior are unchanged.
"""

from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class SearchTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

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

    def get_search_params(self) -> dict:
        return {
            "date_start": self.date_start.text(),
            "date_end": self.date_end.text(),
            "cloud_cover_max": self.cloud_cover.value(),
        }
