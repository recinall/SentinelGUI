"""Entry point: ``python -m sentinelgui`` launches the GUI.

This delegates to :func:`sentinelgui.ui.main_window.main`. As the refactor
progresses this will grow into the QApplication bootstrap + theme install.
"""

from sentinelgui.ui.main_window import main as _gui_main


def main() -> None:
    _gui_main()


if __name__ == "__main__":
    main()
