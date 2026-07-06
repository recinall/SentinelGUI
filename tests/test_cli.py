"""Characterization tests for the unified ``sentinelgui.cli`` entry point.

These pin the argparse dispatch, the exit codes, and (for ``process``) the exact
stdout narration, so the CLI behaves like the retired standalone shims did. No
network and no disk I/O: the processor is faked in place of
``sentinelgui.cli.Sentinel2COGProcessor`` and the lone ``rasterio.open`` write in
the RGB branch is monkeypatched to a context-manager stub.
"""

import numpy as np
import pytest
import rasterio
from PIL import Image

import sentinelgui.cli as cli
import sentinelgui.core.basemap as core_basemap
from sentinelgui.core.basemap import BasemapDownloader


class _FakeProcessor:
    """No-network stand-in for Sentinel2COGProcessor used by the ``search``/``process`` paths.

    ``ALGORITHMS`` must exist as a class attribute because ``build_parser`` reads
    ``Sentinel2COGProcessor.ALGORITHMS.keys()`` to build the ``--algorithm`` choices.
    """

    ALGORITHMS = {"NDVI": {"bands": ["b04", "b08"]}}

    #: scenes that ``search_scenes`` will publish; overridden per test.
    scenes_to_publish: list = []

    def __init__(self, aoi, date_start, date_end, cloud_cover_max=20.0):
        self.aoi = aoi
        self.date_start = date_start
        self.date_end = date_end
        self.cloud_cover_max = cloud_cover_max
        self.scenes = []

    def search_scenes(self):
        self.scenes = list(type(self).scenes_to_publish)
        return self.scenes

    def get_scene_assets(self, scene_index=0):
        return {b: f"https://example.test/{b}.tif" for b in ("b02", "b03", "b04", "b08")}

    def get_bbox_from_aoi(self):
        return (11.0, 46.0, 11.5, 46.5)

    def load_band_window(self, cog_url, bbox, reference_profile=None):
        return np.zeros((3, 4), dtype=np.float32), {"driver": "GTiff", "count": 1}

    def save_raster(self, data, profile, output_path, bit_depth=16, scale_range=None):
        pass

    def calculate_index(self, algorithm, bands):
        return np.zeros((3, 4), dtype=np.float32)

    def create_rgb_composite(self, bands):
        return np.zeros((3, 3, 4), dtype=np.float32)


class _FakeRasterioDataset:
    def write(self, *args, **kwargs):
        pass


class _FakeRasterioOpen:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return _FakeRasterioDataset()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def _run_cli(monkeypatch, argv, scenes):
    _FakeProcessor.scenes_to_publish = scenes
    monkeypatch.setattr(cli, "Sentinel2COGProcessor", _FakeProcessor)
    return cli.main(argv)


_AOI = ["--bbox", "11.0", "46.0", "11.5", "46.5"]
_DATES = ["--date-start", "2024-06-01", "--date-end", "2024-06-30"]


# ---------------------------------------------------------------------------
# top-level dispatch
# ---------------------------------------------------------------------------


def test_no_subcommand_errors(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Sentinel2COGProcessor", _FakeProcessor)
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_unknown_subcommand_errors(monkeypatch):
    monkeypatch.setattr(cli, "Sentinel2COGProcessor", _FakeProcessor)
    with pytest.raises(SystemExit) as exc:
        cli.main(["frobnicate"])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_requires_an_aoi(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, ["search", *_DATES], scenes=[])
    assert exc.value.code == 2
    assert "one of the arguments --bbox --geojson is required" in capsys.readouterr().err


def test_search_no_scenes_found_exits_1(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, ["search", *_AOI, *_DATES], scenes=[])
    assert exc.value.code == 1
    out, err = capsys.readouterr()
    assert out == "Searching for Sentinel-2 scenes...\n"
    assert err == "No scenes found matching criteria\n"


def test_search_scenes_found_succeeds(monkeypatch, capsys):
    _run_cli(monkeypatch, ["search", *_AOI, *_DATES], scenes=[{"id": "scene-0"}])
    out, err = capsys.readouterr()
    assert out == "Searching for Sentinel-2 scenes...\n"
    assert err == ""


# ---------------------------------------------------------------------------
# process
# ---------------------------------------------------------------------------


def test_process_requires_output(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, ["process", *_AOI, *_DATES, "--algorithm", "NDVI"], scenes=[])
    assert exc.value.code == 2
    assert "--output" in capsys.readouterr().err


def test_process_rejects_unknown_algorithm(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_cli(
            monkeypatch,
            ["process", *_AOI, *_DATES, "--output", "/tmp/out", "--algorithm", "NOPE"],
            scenes=[],
        )
    assert exc.value.code == 2
    assert "invalid choice: 'NOPE'" in capsys.readouterr().err


def test_process_no_scenes_found_exits_1(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_cli(
            monkeypatch,
            ["process", *_AOI, *_DATES, "--output", "/tmp/out", "--algorithm", "NDVI"],
            scenes=[],
        )
    assert exc.value.code == 1
    out, err = capsys.readouterr()
    assert out == "Searching for Sentinel-2 scenes...\n"
    assert err == "No scenes found matching criteria\n"


def test_process_no_processing_specified_exits_1(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _run_cli(
            monkeypatch,
            ["process", *_AOI, *_DATES, "--output", "/tmp/out"],
            scenes=[{"id": "scene-0"}],
        )
    assert exc.value.code == 1
    out, err = capsys.readouterr()
    assert out == "Searching for Sentinel-2 scenes...\n\nProcessing scene 0...\n"
    assert err.strip().endswith("No processing specified. Use --algorithm, --bands, or --rgb")


def test_process_full_run_emits_exact_narration(monkeypatch, capsys):
    monkeypatch.setattr(rasterio, "open", _FakeRasterioOpen)
    _run_cli(
        monkeypatch,
        [
            "process", *_AOI, *_DATES, "--output", "/tmp/out",
            "--algorithm", "NDVI", "--rgb", "--save-bands",
        ],
        scenes=[{"id": "scene-0"}],
    )
    out, err = capsys.readouterr()
    assert out == (
        "Searching for Sentinel-2 scenes...\n"
        "\nProcessing scene 0...\n"
        "\nLoading bands: b02, b03, b04, b08\n"
        "Loading b02... ✓ ((3, 4)) [REFERENCE]\n"
        "Loading b03... ✓ ((3, 4)) [resampled to reference]\n"
        "Loading b04... ✓ ((3, 4)) [resampled to reference]\n"
        "Loading b08... ✓ ((3, 4)) [resampled to reference]\n"
        "\nCalculating NDVI...\n"
        "\nCreating RGB composite...\n"
        "Saved: /tmp/out_rgb.tif\n"
        "\nProcessing complete!\n"
    )
    assert err == ""


# ---------------------------------------------------------------------------
# overlay
# ---------------------------------------------------------------------------


_OVERLAY_MIN = ["overlay", "--index", "idx.tif", "--output", "out.tif"]


def test_overlay_opacity_out_of_range(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([*_OVERLAY_MIN, "--opacity", "1.5"])
    assert exc.value.code == 2
    assert "--opacity must be between 0.0 and 1.0" in capsys.readouterr().err


def test_overlay_threshold_out_of_range(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([*_OVERLAY_MIN, "--threshold", "150"])
    assert exc.value.code == 2
    assert "--threshold must be between 0.0 and 100.0" in capsys.readouterr().err


def test_overlay_level_out_of_range(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([
            *_OVERLAY_MIN, "--mode", "gradient",
            "--levels", "0", "200", "--colors", "#000000", "#ffffff",
        ])
    assert exc.value.code == 2
    assert "--levels values must be between 0.0 and 100.0" in capsys.readouterr().err


def test_overlay_class_mode_level_color_mismatch(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([
            *_OVERLAY_MIN, "--mode", "class",
            "--levels", "0", "100", "--colors", "#000000", "#ffffff",
        ])
    assert exc.value.code == 2
    assert "For 'class' mode, number of levels" in capsys.readouterr().err


def test_overlay_gradient_mode_level_color_mismatch(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([
            *_OVERLAY_MIN, "--mode", "gradient",
            "--levels", "0", "50", "100", "--colors", "#000000", "#ffffff",
        ])
    assert exc.value.code == 2
    assert "For 'gradient' mode, number of levels" in capsys.readouterr().err


def test_overlay_gradient_needs_two_levels(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([*_OVERLAY_MIN, "--mode", "gradient", "--levels", "0", "--colors", "#000000"])
    assert exc.value.code == 2
    assert "you need at least 2 levels/colors" in capsys.readouterr().err


def test_overlay_invalid_hex_color(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([
            *_OVERLAY_MIN, "--mode", "gradient",
            "--levels", "0", "100", "--colors", "notacolor", "#ffffff",
        ])
    assert exc.value.code == 2
    assert "Invalid hex color in --colors" in capsys.readouterr().err


def test_overlay_success_path_calls_core_with_positional_order(monkeypatch):
    """The overlay success path forwards args positionally in a fixed order:
    (rgb, index, output, levels, colors, opacity, threshold, mode)."""
    recorded = {}

    def fake_create_overlay(*args):
        recorded["args"] = args

    monkeypatch.setattr(cli, "create_overlay", fake_create_overlay)
    cli.main(_OVERLAY_MIN)  # no SystemExit on the success path

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


# ---------------------------------------------------------------------------
# basemap
# ---------------------------------------------------------------------------


_BASEMAP_BBOX = ["--bbox", "11.0", "46.0", "11.5", "46.5"]  # zoom 8 -> a 2x2 grid


def _patch_basemap(monkeypatch, failing_tile=None):
    """Fake the tile HTTP and the rasterio write so basemap runs offline, no disk."""

    def fake_download_tile(x, y, zoom, source="osm"):
        if failing_tile is not None and (x, y) == failing_tile:
            return None
        return Image.new("RGB", (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)
    monkeypatch.setattr(core_basemap.rasterio, "open", _FakeRasterioOpen)


def test_basemap_requires_output(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["basemap", *_BASEMAP_BBOX, "--zoom", "8"])
    assert exc.value.code == 2
    assert "--output" in capsys.readouterr().err


def test_basemap_requires_zoom(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["basemap", *_BASEMAP_BBOX, "--output", "/tmp/base.tif"])
    assert exc.value.code == 2
    assert "--zoom" in capsys.readouterr().err


def test_basemap_rejects_unknown_source(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([
            "basemap", *_BASEMAP_BBOX, "--zoom", "8", "--output", "/tmp/b.tif", "--source", "bing",
        ])
    assert exc.value.code == 2
    assert "invalid choice: 'bing'" in capsys.readouterr().err


def test_basemap_success_emits_progress_and_summary(monkeypatch, capsys):
    _patch_basemap(monkeypatch)
    cli.main(["basemap", *_BASEMAP_BBOX, "--zoom", "8", "--output", "/tmp/base.tif"])
    out = capsys.readouterr().out
    assert out == (
        "Downloading basemap tiles at zoom level 8...\n"
        "Source: ESRI\n"
        "Downloaded 4/4 tiles successfully\n"
    )


def test_basemap_reports_failed_tiles(monkeypatch, capsys):
    # For this bbox/zoom the grid starts at (135, 90); fail exactly one tile.
    _patch_basemap(monkeypatch, failing_tile=(136, 91))
    cli.main([
        "basemap", *_BASEMAP_BBOX, "--zoom", "8",
        "--output", "/tmp/base.tif", "--source", "google",
    ])
    out = capsys.readouterr().out
    assert out.startswith("Downloading basemap tiles at zoom level 8...\nSource: GOOGLE\n")
    assert out.endswith("Downloaded 3/4 tiles successfully (1 failed)\n")
