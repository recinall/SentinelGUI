"""Characterization tests for the GUI-observable progress sequence produced by the
``SearchWorker`` (``sentinelgui.workers.search``) and ``ProcessingWorker``
(``sentinelgui.workers.processing``).

Both are ``QThread`` subclasses, but they are exercised here by calling ``.run()``
directly and SYNCHRONOUSLY (never ``.start()``), so nothing is offloaded to a real
worker thread and no Qt event loop is required. The offscreen platform is set
process-wide by ``tests/conftest.py``, which is what makes importing the workers
(a module-scope ``PySide6`` import) safe here.

The processor is fully faked (no network, no rasterio reads) via a plain class with
canned return values, so the search case exercises only ``SearchWorker.run()``
itself, while the process case drives ``Sentinel2COGProcessor.process_scene``.
The only real I/O boundary left for the RGB branch is an inline
``rasterio.open(path, 'w', **profile)`` write, which is monkeypatched to a
context-manager stub so nothing touches disk.

This is a snapshot of the *exact* ordered progress strings and the
finished/scene_found payloads, so refactors of the workers or ``process_scene``
can be checked against it without behavior drift.
"""

import numpy as np
import rasterio

from sentinelgui.core.models import ProcessingParams
from sentinelgui.core.processor import Sentinel2COGProcessor
from sentinelgui.workers.processing import ProcessingWorker
from sentinelgui.workers.search import SearchWorker


def _make_processor():
    """A real Sentinel2COGProcessor with its network/IO methods faked in-place."""
    band_urls = {"b04": "https://example.test/b04.tif", "b08": "https://example.test/b08.tif"}
    fake_profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "width": 4,
        "height": 3,
        "count": 1,
        "crs": "EPSG:4326",
        "transform": "IDENTITY",
    }

    processor = Sentinel2COGProcessor(
        {"bbox": [11.0, 46.0, 11.5, 46.5]}, "2024-06-01", "2024-06-30"
    )

    def fake_get_scene_assets(scene_index):
        assert scene_index == 0
        return band_urls

    def fake_load_band_window(cog_url, bbox, reference_profile=None):
        return np.zeros((3, 4), dtype=np.float32), fake_profile

    def fake_save_raster(data, profile, output_path, bit_depth=8, scale_range=None):
        pass

    def fake_calculate_index(algorithm, bands):
        return np.zeros((3, 4), dtype=np.float32)

    def fake_create_rgb_composite(bands):
        return np.zeros((3, 3, 4), dtype=np.float32)

    processor.get_scene_assets = fake_get_scene_assets
    processor.load_band_window = fake_load_band_window
    processor.save_raster = fake_save_raster
    processor.calculate_index = fake_calculate_index
    processor.create_rgb_composite = fake_create_rgb_composite

    return processor


class FakeProcessor:
    """Canned stand-in for Sentinel2COGProcessor: no network, no rasterio reads."""

    def __init__(self):
        self.band_urls = {"b04": "https://example.test/b04.tif", "b08": "https://example.test/b08.tif"}
        self.fake_profile = {
            "driver": "GTiff",
            "dtype": "float32",
            "width": 4,
            "height": 3,
            "count": 1,
            "crs": "EPSG:4326",
            "transform": "IDENTITY",
        }
        self.save_raster_calls = []

    # -- "search" task type --
    def search_scenes(self):
        return [{"id": "scene-0"}, {"id": "scene-1"}]

    # -- "process" task type --
    def get_scene_assets(self, scene_index):
        assert scene_index == 0
        return self.band_urls

    def load_band_window(self, cog_url, bbox, reference_profile=None):
        return np.zeros((3, 4), dtype=np.float32), self.fake_profile

    def save_raster(self, data, profile, output_path, bit_depth=8, scale_range=None):
        self.save_raster_calls.append((output_path, bit_depth, scale_range))

    def calculate_index(self, algorithm, bands):
        return np.zeros((3, 4), dtype=np.float32)

    def create_rgb_composite(self, bands):
        return np.zeros((3, 3, 4), dtype=np.float32)


class _FakeRasterioDataset:
    def write(self, data):
        pass


class _FakeRasterioOpen:
    """Context-manager stand-in for rasterio.open(path, 'w', **profile)."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return _FakeRasterioDataset()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def _run_thread(worker):
    progress_msgs = []
    finished_calls = []
    scene_found_calls = []

    worker.progress.connect(progress_msgs.append)
    worker.finished.connect(lambda ok, msg: finished_calls.append((ok, msg)))
    # scene_found only exists on the search worker; the process worker never emits it.
    if hasattr(worker, "scene_found"):
        worker.scene_found.connect(scene_found_calls.append)

    worker.run()

    return progress_msgs, finished_calls, scene_found_calls


def test_process_task_emits_exact_progress_sequence(monkeypatch):
    monkeypatch.setattr(rasterio, "open", _FakeRasterioOpen)

    processor = _make_processor()

    msgs = []
    summary = processor.process_scene(
        ProcessingParams(
            scene_index=0,
            bbox=(11.0, 46.0, 11.5, 46.5),
            bands_to_load={"b04", "b08"},
            output="/tmp/out",
            algorithms=["NDVI"],
            save_bands=True,
            rgb=True,
            bit_depth=16,
            ref_band="b04",
        ),
        progress=msgs.append,
    )

    assert msgs == [
        "Processing scene 0...",
        "[1/4] Loading b04...",
        "  Using b04 as reference (4x3 pixels)",
        "  Saved: /tmp/out_band_b04.tif",
        "[2/4] Loading b08...",
        "  Saved: /tmp/out_band_b08.tif",
        "[3/4] Calculating NDVI...",
        "  Saved: /tmp/out_ndvi.tif",
        "  Saved: /tmp/out_ndvi_color.tif",
        "[4/4] Creating RGB composite...",
        "  Saved: /tmp/out_rgb.tif",
    ]

    assert summary == "Processing complete! Generated 1 indices, 2 bands, 1 RGB composite"


def test_process_task_reference_profile_only_reported_once():
    # The "Using <band> as reference" message only fires on the FIRST band loaded
    # (whichever establishes reference_profile); the second band load must not
    # repeat it, which the exact-sequence assertion above already proves, but this
    # test isolates that single fact for clarity/robustness against reordering.
    processor = _make_processor()

    msgs = []
    summary = processor.process_scene(
        ProcessingParams(
            scene_index=0,
            bbox=(11.0, 46.0, 11.5, 46.5),
            bands_to_load={"b04", "b08"},
            output="/tmp/out",
            algorithms=[],
            save_bands=False,
            rgb=False,
            bit_depth=16,
            ref_band="b04",
        ),
        progress=msgs.append,
    )

    reference_msgs = [m for m in msgs if m.startswith("  Using")]
    assert reference_msgs == ["  Using b04 as reference (4x3 pixels)"]
    assert summary == "Processing complete! Generated 0 indices"


def test_process_task_via_worker_emits_exact_progress_sequence(monkeypatch):
    """Freezes the ``ProcessingWorker`` contract: it forwards its ``ProcessingParams``
    straight to ``process_scene`` and re-emits progress/finished unchanged.

    Drives ``ProcessingWorker.run()`` (not ``process_scene`` directly) with a fully
    populated ``ProcessingParams``, so the real worker object is exercised. This must
    keep producing the exact same progress sequence and finished payload as the
    direct-call test (``test_process_task_emits_exact_progress_sequence``) for the
    same effective arguments.
    """
    monkeypatch.setattr(rasterio, "open", _FakeRasterioOpen)

    processor = _make_processor()

    params = ProcessingParams(
        scene_index=0,
        bbox=(11.0, 46.0, 11.5, 46.5),
        bands_to_load={"b04", "b08"},
        output="/tmp/out",
        algorithms=["NDVI"],
        save_bands=True,
        rgb=True,
        bit_depth=16,
        ref_band="b04",
    )

    progress_msgs, finished_calls, scene_found_calls = _run_thread(
        ProcessingWorker(processor, params)
    )

    assert progress_msgs == [
        "Processing scene 0...",
        "[1/4] Loading b04...",
        "  Using b04 as reference (4x3 pixels)",
        "  Saved: /tmp/out_band_b04.tif",
        "[2/4] Loading b08...",
        "  Saved: /tmp/out_band_b08.tif",
        "[3/4] Calculating NDVI...",
        "  Saved: /tmp/out_ndvi.tif",
        "  Saved: /tmp/out_ndvi_color.tif",
        "[4/4] Creating RGB composite...",
        "  Saved: /tmp/out_rgb.tif",
    ]

    assert finished_calls == [
        (True, "Processing complete! Generated 1 indices, 2 bands, 1 RGB composite")
    ]
    assert scene_found_calls == []


def test_process_task_via_worker_uses_dataclass_defaults(monkeypatch):
    """Freezes the omitted-field defaults driven through ``ProcessingWorker``, which
    now come from the ``ProcessingParams`` dataclass.

    Only the required fields (``scene_index``, ``bbox``, ``bands_to_load``, ``output``)
    are supplied; ``algorithms``, ``save_bands``, ``rgb``, ``bit_depth``, and
    ``ref_band`` are omitted entirely so the ``ProcessingParams`` defaults
    (``[]``, ``False``, ``False``, ``16``, ``None``) are exercised, exactly as the
    worker's ``.get(...)`` fallbacks did before.
    """
    monkeypatch.setattr(rasterio, "open", _FakeRasterioOpen)

    processor = _make_processor()

    params = ProcessingParams(
        scene_index=0,
        bbox=(11.0, 46.0, 11.5, 46.5),
        bands_to_load={"b04", "b08"},
        output="/tmp/out",
    )

    progress_msgs, finished_calls, scene_found_calls = _run_thread(
        ProcessingWorker(processor, params)
    )

    assert progress_msgs == [
        "Processing scene 0...",
        "[1/2] Loading b04...",
        "  Using b04 as reference (4x3 pixels)",
        "[2/2] Loading b08...",
    ]
    assert not any(m.startswith("[") and "Calculating" in m for m in progress_msgs)
    assert not any("Creating RGB composite" in m for m in progress_msgs)
    assert not any(m.startswith("  Saved:") for m in progress_msgs)

    assert finished_calls == [(True, "Processing complete! Generated 0 indices")]
    assert scene_found_calls == []


def test_search_task_emits_expected_sequence_and_payloads():
    processor = FakeProcessor()

    progress_msgs, finished_calls, scene_found_calls = _run_thread(SearchWorker(processor))

    assert progress_msgs == ["Searching for scenes..."]
    assert finished_calls == [(True, "Found 2 scenes")]
    assert scene_found_calls == [[{"id": "scene-0"}, {"id": "scene-1"}]]
