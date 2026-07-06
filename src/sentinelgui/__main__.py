"""Entry point: dispatch between the GUI and the headless CLI.

``python -m sentinelgui`` with no arguments launches the GUI (via
:func:`sentinelgui.app.main`). Any argument routes to the headless CLI
(:func:`sentinelgui.cli.main`), so ``python -m sentinelgui --help`` and the
``search`` / ``process`` / ``overlay`` / ``basemap`` subcommands run headless.

The heavy, branch-specific imports (Qt for the GUI, rasterio for the CLI) are
deferred into each branch so neither path pays for the other's dependencies —
in particular the CLI never imports Qt.
"""

import sys


def main() -> None:
    if len(sys.argv) > 1:
        from sentinelgui.cli import main as cli_main

        cli_main()
    else:
        from sentinelgui.app import main as gui_main

        gui_main()


if __name__ == "__main__":
    main()
