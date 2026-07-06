"""Search-results scene table.

A ``QTableWidget`` preconfigured with the six STAC columns and row-selection modes,
plus a :meth:`populate` method that fills it from the scene dicts and a
:meth:`selected_index`/:meth:`has_selection` pair the controller uses to drive the
Process button. Lifted verbatim from the inline table setup and the
``populate_scene_table`` body of the old ``Sentinel2GUI``; the controller keeps
``self.scenes`` and connects ``itemSelectionChanged`` itself.
"""

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem


class SceneTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(
            ["Index", "Date/Time", "Cloud Cover %", "MGRS Tile", "Scene ID", "Platform"]
        )
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)

    def populate(self, scenes):
        self.setRowCount(len(scenes))

        for idx, scene in enumerate(scenes):
            props = scene["properties"]

            self.setItem(idx, 0, QTableWidgetItem(str(idx)))
            self.setItem(idx, 1, QTableWidgetItem(props.get("datetime", "N/A")))
            self.setItem(idx, 2, QTableWidgetItem(f"{props.get('eo:cloud_cover', 0):.1f}"))

            mgrs = (
                f"{props.get('mgrs:utm_zone', '')}"
                f"{props.get('mgrs:latitude_band', '')}"
                f"{props.get('mgrs:grid_square', '')}"
            )
            self.setItem(idx, 3, QTableWidgetItem(mgrs))
            self.setItem(idx, 4, QTableWidgetItem(props.get("sentinel:product_id", "N/A")))
            self.setItem(idx, 5, QTableWidgetItem(props.get("platform", "N/A")))

        if scenes:
            self.selectRow(0)

    def has_selection(self) -> bool:
        return bool(self.selectedItems())

    def selected_index(self) -> int | None:
        items = self.selectedItems()
        return int(items[0].text()) if items else None
