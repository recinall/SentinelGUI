"""Application bootstrap: build the ``QApplication``, install the theme, show the window.

This is the single entry point for the GUI (``python -m sentinelgui`` and the
``sentinelgui`` console script both land here). Keeping the bootstrap out of
``ui/main_window`` lets the window class stay a pure controller and centralizes the
theme install (Fusion style + palette + generated stylesheet, restored from the
persisted choice) in one place.
"""

import sys
from importlib.resources import files

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from sentinelgui.ui import theme
from sentinelgui.ui.main_window import Sentinel2GUI


def _app_icon() -> QIcon:
    """Load the bundled application icon (``resources/icon.png``) as a ``QIcon``.

    Read the bytes through ``importlib.resources`` rather than a filesystem path so
    the icon resolves both from the source tree and from a frozen/zipped bundle
    (mirrors :mod:`sentinelgui.ui.theme.icons`).
    """
    data = files("sentinelgui").joinpath("resources", "icon.png").read_bytes()
    pixmap = QPixmap()
    pixmap.loadFromData(data)
    return QIcon(pixmap)


def main() -> None:
    app = QApplication(sys.argv)
    app.setWindowIcon(_app_icon())
    theme.load_theme(app, theme.current_mode())

    window = Sentinel2GUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
