"""Entry point: ``python -m sentinelgui`` launches the GUI.

This delegates to :func:`sentinelgui.app.main`, which builds the ``QApplication``,
installs the theme, and shows the main window.
"""

from sentinelgui.app import main as _gui_main


def main() -> None:
    _gui_main()


if __name__ == "__main__":
    main()
