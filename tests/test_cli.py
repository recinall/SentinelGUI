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

import sentinelgui.cli as cli


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
    def write(self, data):
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
