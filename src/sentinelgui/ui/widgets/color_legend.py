"""A small colorbar legend for the colormapped single-band views.

Samples a matplotlib colormap into a horizontal gradient with low/high end labels.
The gradient colors come from the colormap (they are data, not theme chrome); the
labels use the widget's themed palette, so nothing here hardcodes a UI color. The
results viewer shows it for colormapped single-band overlays/maps and hides it for
plain RGB passthrough.
"""

from __future__ import annotations

from matplotlib import colormaps
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

_STOPS = 32


class ColorLegend(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cmap_name: str | None = None
        self._low = "low"
        self._high = "high"
        self.setMinimumHeight(28)

    def set_colormap(self, cmap_name: str | None, low: str = "low", high: str = "high") -> None:
        """Show the legend for ``cmap_name``; ``None`` hides it."""
        self._cmap_name = cmap_name
        self._low = low
        self._high = high
        self.setVisible(cmap_name is not None)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802  (Qt override name)
        if self._cmap_name is None:
            return

        painter = QPainter(self)
        rect = self.rect()

        gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
        cmap = colormaps[self._cmap_name]
        for i in range(_STOPS):
            t = i / (_STOPS - 1)
            r, g, b, _ = cmap(t)
            gradient.setColorAt(t, QColor(int(r * 255), int(g * 255), int(b * 255)))
        painter.fillRect(rect, gradient)

        painter.setPen(self.palette().color(self.palette().ColorRole.WindowText))
        painter.drawText(rect.adjusted(4, 0, 0, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._low)
        painter.drawText(rect.adjusted(0, 0, -4, 0),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._high)
        painter.end()
