"""Entry point: ``python -m sentinelgui`` launches the GUI.

For now this delegates to the (still monolithic) GUI module. As the refactor
progresses this will grow into the QApplication bootstrap + theme install.
"""

from sentinelgui.sentinel_gui import main as _gui_main


def main() -> None:
    _gui_main()


if __name__ == "__main__":
    main()
