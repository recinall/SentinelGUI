"""Application bootstrap: build the ``QApplication``, install the theme, show the window.

This is the single entry point for the GUI (``python -m sentinelgui`` and the
``sentinelgui`` console script both land here). Keeping the bootstrap out of
``ui/main_window`` lets the window class stay a pure controller and centralizes the
theme install (Fusion style + palette + generated stylesheet, restored from the
persisted choice) in one place.
"""

import sys

from PySide6.QtWidgets import QApplication

from sentinelgui.ui import theme
from sentinelgui.ui.main_window import Sentinel2GUI


def main() -> None:
    app = QApplication(sys.argv)
    theme.load_theme(app, theme.current_mode())

    window = Sentinel2GUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
