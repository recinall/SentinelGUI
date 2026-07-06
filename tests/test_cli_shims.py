"""Characterization tests for the two standalone argparse shims BEFORE they are
folded into the unified ``sentinelgui.cli``.

These freeze the observable command-line contract — argparse validation exits
(``SystemExit(2)`` with a usage message on stderr), the early-exit error paths
(``SystemExit(1)`` with a specific stderr line), and the positional-argument order
handed to the core functions — so the port into ``cli.py`` can be proven equivalent.

No network and no disk I/O: ``sentinel.main`` runs against a fake processor class
(monkeypatched in place of ``Sentinel2COGProcessor``) whose ``search_scenes`` just
sets ``self.scenes``; ``create_overlay.main`` has its ``create_overlay`` call
monkeypatched to a recorder, so the success path never reads or writes an image.

This module is transient: once ``cli.py`` owns the CLI (and the shims are retired),
the frozen contract lives in ``test_cli.py`` and this file is removed.
"""

import sys

import pytest

import sentinelgui.create_overlay as create_overlay_shim
import sentinelgui.sentinel as sentinel_shim

# ---------------------------------------------------------------------------
# sentinel.py shim
# ---------------------------------------------------------------------------


class _FakeProcessor:
    """Stand-in for Sentinel2COGProcessor: no network, canned scene results.

    ``ALGORITHMS`` must exist as a class attribute because ``sentinel.main`` reads
    ``Sentinel2COGProcessor.ALGORITHMS.keys()`` at argparse-setup time to build the
    ``--algorithm`` choices.
    """

    ALGORITHMS = {"NDVI": {"bands": ["b04", "b08"]}}

    #: scenes that ``search_scenes`` will publish; overridden per test.
    scenes_to_publish: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.scenes = []

    def search_scenes(self):
        self.scenes = list(type(self).scenes_to_publish)
        return self.scenes

    def get_scene_assets(self, scene_index=0):
        return {}

    def get_bbox_from_aoi(self):
        return (11.0, 46.0, 11.5, 46.5)


def _run_sentinel(monkeypatch, argv, scenes):
    _FakeProcessor.scenes_to_publish = scenes
    monkeypatch.setattr(sentinel_shim, "Sentinel2COGProcessor", _FakeProcessor)
    monkeypatch.setattr(sys, "argv", ["sentinel", *argv])
    with pytest.raises(SystemExit) as exc:
        sentinel_shim.main()
    return exc.value.code


def test_sentinel_requires_an_aoi(monkeypatch, capsys):
    # Neither --bbox nor --geojson: the required mutually-exclusive group errors.
    code = _run_sentinel(
        monkeypatch,
        ["--date-start", "2024-06-01", "--date-end", "2024-06-30", "--output", "/tmp/out"],
        scenes=[],
    )
    assert code == 2
    assert "one of the arguments --bbox --geojson is required" in capsys.readouterr().err


def test_sentinel_requires_date_start(monkeypatch, capsys):
    code = _run_sentinel(
        monkeypatch,
        [
            "--bbox", "11.0", "46.0", "11.5", "46.5",
            "--date-end", "2024-06-30", "--output", "/tmp/out",
        ],
        scenes=[],
    )
    assert code == 2
    assert "--date-start" in capsys.readouterr().err


def test_sentinel_rejects_unknown_algorithm(monkeypatch, capsys):
    code = _run_sentinel(
        monkeypatch,
        [
            "--bbox", "11.0", "46.0", "11.5", "46.5",
            "--date-start", "2024-06-01", "--date-end", "2024-06-30",
            "--output", "/tmp/out", "--algorithm", "NOPE",
        ],
        scenes=[],
    )
    assert code == 2
    assert "invalid choice: 'NOPE'" in capsys.readouterr().err


def test_sentinel_no_scenes_found_exits_1(monkeypatch, capsys):
    code = _run_sentinel(
        monkeypatch,
        [
            "--bbox", "11.0", "46.0", "11.5", "46.5",
            "--date-start", "2024-06-01", "--date-end", "2024-06-30",
            "--output", "/tmp/out", "--algorithm", "NDVI",
        ],
        scenes=[],
    )
    assert code == 1
    out, err = capsys.readouterr()
    assert out == "Searching for Sentinel-2 scenes...\n"
    assert err == "No scenes found matching criteria\n"


def test_sentinel_no_processing_specified_exits_1(monkeypatch, capsys):
    # A scene is found, but no --algorithm/--bands/--rgb -> nothing to do.
    code = _run_sentinel(
        monkeypatch,
        [
            "--bbox", "11.0", "46.0", "11.5", "46.5",
            "--date-start", "2024-06-01", "--date-end", "2024-06-30",
            "--output", "/tmp/out",
        ],
        scenes=[{"id": "scene-0"}],
    )
    assert code == 1
    err = capsys.readouterr().err
    assert err.strip().endswith("No processing specified. Use --algorithm, --bands, or --rgb")


# ---------------------------------------------------------------------------
# create_overlay.py shim
# ---------------------------------------------------------------------------


def _run_overlay(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["create_overlay", *argv])
    with pytest.raises(SystemExit) as exc:
        create_overlay_shim.main()
    return exc.value.code


_OVERLAY_MIN = ["--index", "idx.tif", "--output", "out.tif"]


def test_overlay_opacity_out_of_range(monkeypatch, capsys):
    code = _run_overlay(monkeypatch, [*_OVERLAY_MIN, "--opacity", "1.5"])
    assert code == 2
    assert "--opacity must be between 0.0 and 1.0" in capsys.readouterr().err


def test_overlay_threshold_out_of_range(monkeypatch, capsys):
    code = _run_overlay(monkeypatch, [*_OVERLAY_MIN, "--threshold", "150"])
    assert code == 2
    assert "--threshold must be between 0.0 and 100.0" in capsys.readouterr().err


def test_overlay_level_out_of_range(monkeypatch, capsys):
    code = _run_overlay(
        monkeypatch,
        [
            *_OVERLAY_MIN, "--mode", "gradient",
            "--levels", "0", "200", "--colors", "#000000", "#ffffff",
        ],
    )
    assert code == 2
    assert "--levels values must be between 0.0 and 100.0" in capsys.readouterr().err


def test_overlay_class_mode_level_color_mismatch(monkeypatch, capsys):
    # class mode needs len(levels) == len(colors) + 1; here 2 == 2 is wrong.
    code = _run_overlay(
        monkeypatch,
        [
            *_OVERLAY_MIN, "--mode", "class",
            "--levels", "0", "100", "--colors", "#000000", "#ffffff",
        ],
    )
    assert code == 2
    assert "For 'class' mode, number of levels" in capsys.readouterr().err


def test_overlay_gradient_mode_level_color_mismatch(monkeypatch, capsys):
    code = _run_overlay(
        monkeypatch,
        [
            *_OVERLAY_MIN, "--mode", "gradient",
            "--levels", "0", "50", "100", "--colors", "#000000", "#ffffff",
        ],
    )
    assert code == 2
    assert "For 'gradient' mode, number of levels" in capsys.readouterr().err


def test_overlay_gradient_needs_two_levels(monkeypatch, capsys):
    code = _run_overlay(
        monkeypatch,
        [*_OVERLAY_MIN, "--mode", "gradient", "--levels", "0", "--colors", "#000000"],
    )
    assert code == 2
    assert "you need at least 2 levels/colors" in capsys.readouterr().err


def test_overlay_invalid_hex_color(monkeypatch, capsys):
    code = _run_overlay(
        monkeypatch,
        [
            *_OVERLAY_MIN, "--mode", "gradient",
            "--levels", "0", "100", "--colors", "notacolor", "#ffffff",
        ],
    )
    assert code == 2
    assert "Invalid hex color in --colors" in capsys.readouterr().err


def test_overlay_success_path_calls_core_with_positional_order(monkeypatch):
    """The shim's success path forwards args to ``create_overlay`` positionally in a
    fixed order: (rgb, index, output, levels, colors, opacity, threshold, mode)."""
    recorded = {}

    def fake_create_overlay(*args):
        recorded["args"] = args

    monkeypatch.setattr(create_overlay_shim, "create_overlay", fake_create_overlay)
    monkeypatch.setattr(sys, "argv", ["create_overlay", *_OVERLAY_MIN])

    create_overlay_shim.main()  # no SystemExit on the success path

    assert recorded["args"] == (
        None,  # --rgb (not provided)
        "idx.tif",
        "out.tif",
        [0.0, 25.0, 50.0, 75.0, 100.0],  # default levels
        ["#0000FF", "#FF0000", "#FFFF00", "#00FF00", "#007200"],  # default colors
        0.7,  # default opacity
        10.0,  # default threshold
        "gradient",  # default mode
    )
