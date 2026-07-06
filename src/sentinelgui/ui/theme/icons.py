"""Render the theme's ``currentColor`` SVG icons into recolored ``QIcon`` pixmaps.

The SVGs in ``sentinelgui/resources/icons`` are stroke-based and use
``stroke="currentColor"`` so one asset serves both themes. Qt does not resolve CSS
``currentColor`` for button icons, so :func:`render_icon` substitutes the requested color
into the SVG text and rasterizes it. Callers pass a token color (e.g. a palette's
``on_surface`` / ``on_primary``) and re-render on theme change so icons track the theme.
"""

from importlib.resources import files

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ICONS = files("sentinelgui").joinpath("resources", "icons")


def render_icon(name: str, color: str, size: int = 40) -> QIcon:
    """Return a ``QIcon`` for ``resources/icons/<name>.svg`` tinted with ``color``."""
    svg = _ICONS.joinpath(f"{name}.svg").read_text(encoding="utf-8")
    svg = svg.replace("currentColor", color)

    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)
