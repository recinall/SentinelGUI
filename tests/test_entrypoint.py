"""Freezes the GUI-vs-CLI dispatch in ``sentinelgui.__main__``.

Zero arguments launch the GUI; any argument routes to the headless CLI. Both
``app.main`` and ``cli.main`` are replaced with recorders, so nothing actually
starts a Qt event loop or parses real arguments — only the dispatch branch is
exercised.
"""

import sys

import sentinelgui.__main__ as entry


def _install_recorders(monkeypatch):
    called = []
    monkeypatch.setattr("sentinelgui.app.main", lambda: called.append("gui"))
    monkeypatch.setattr("sentinelgui.cli.main", lambda: called.append("cli"))
    return called


def test_no_args_launches_gui(monkeypatch):
    called = _install_recorders(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["sentinelgui"])
    entry.main()
    assert called == ["gui"]


def test_any_arg_routes_to_cli(monkeypatch):
    called = _install_recorders(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["sentinelgui", "search", "--help"])
    entry.main()
    assert called == ["cli"]
