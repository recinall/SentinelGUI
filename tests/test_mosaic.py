"""Headless tests for multi-tile mosaicking in ``process_scene`` (no Qt/network/IO).

Bug 3: when the AOI straddles a Sentinel-2 tile boundary, a single scene covers only
part of it and the output is a nodata strip. ``process_scene`` now gathers the
same-acquisition sibling tiles that intersect the AOI and fill-merges them onto the
reference grid; when no tiles can complete the coverage it warns instead.

The processor is real but its network/IO seams (``get_scene_assets`` /
``load_band_window`` / ``save_raster``) are faked, and ``self.scenes`` is populated
with synthetic STAC features whose GeoJSON footprints split the AOI, so the tile
selection + merge run entirely in-process.
"""

import numpy as np
from shapely.geometry import box, mapping

from sentinelgui.core.models import ProcessingParams
from sentinelgui.core.processor import Sentinel2COGProcessor

# AOI = unit square; south tile covers the bottom 60%, north tile the top 60%.
AOI = (0.0, 0.0, 1.0, 1.0)
FAKE_PROFILE = {
    "driver": "GTiff", "dtype": "float32", "width": 2, "height": 4,
    "count": 1, "crs": "EPSG:4326", "transform": "IDENTITY",
}

# 4-row arrays, row 0 = north (top), row 3 = south (bottom).
SOUTH_ARR = np.array([[0, 0], [0, 0], [1, 1], [1, 1]], dtype=np.float32)  # valid bottom
NORTH_ARR = np.array([[1, 1], [1, 1], [0, 0], [0, 0]], dtype=np.float32)  # valid top


def _scene(datetime_str, geom_box, tile):
    zone, band, square = tile[:2], tile[2], tile[3:]
    return {
        "geometry": mapping(box(*geom_box)),
        "properties": {
            "datetime": datetime_str,
            "mgrs:utm_zone": zone,
            "mgrs:latitude_band": band,
            "mgrs:grid_square": square,
        },
        "assets": {},
    }


def _processor(scenes, arr_by_url):
    proc = Sentinel2COGProcessor({"bbox": list(AOI)}, "2024-08-01", "2024-08-31")
    proc.scenes = scenes

    proc.get_scene_assets = lambda idx: {"b04": f"url-{idx}"}
    proc.load_band_window = lambda url, bbox, reference_profile=None: (
        arr_by_url[url], FAKE_PROFILE
    )

    saved = {}

    def fake_save(data, profile, output_path, bit_depth=8, scale_range=None):
        saved[output_path] = np.array(data)

    proc.save_raster = fake_save
    return proc, saved


def _run(proc):
    msgs = []
    proc.process_scene(
        ProcessingParams(
            scene_index=0, bbox=AOI, bands_to_load={"b04"}, output="/tmp/out",
            algorithms=[], save_bands=True, rgb=False, bit_depth=16, ref_band="b04",
        ),
        progress=msgs.append,
    )
    return msgs


def test_two_tiles_are_mosaicked_into_a_full_frame():
    scenes = [
        _scene("2024-08-30T10:18:16Z", (0.0, 0.0, 1.0, 0.6), "32TPR"),  # south, selected
        _scene("2024-08-30T10:18:01Z", (0.0, 0.4, 1.0, 1.0), "32TPS"),  # north sibling
    ]
    proc, saved = _processor(scenes, {"url-0": SOUTH_ARR, "url-1": NORTH_ARR})

    msgs = _run(proc)

    # Both tiles were selected and merged; full coverage => no warning.
    assert any(m.startswith("Mosaicking 2 tiles:") and "32TPR" in m and "32TPS" in m
               for m in msgs)
    assert "  Mosaicked 2 tiles for b04" in msgs
    assert not any(m.startswith("Warning: available imagery") for m in msgs)

    merged = saved["/tmp/out_band_b04.tif"]
    assert not np.any(merged == 0)  # the strip is gone — every pixel is filled


def test_partial_coverage_warns_and_leaves_a_strip():
    # Only the south tile is available; it covers ~60% of the AOI.
    scenes = [_scene("2024-08-30T10:18:16Z", (0.0, 0.0, 1.0, 0.6), "32TPR")]
    proc, saved = _processor(scenes, {"url-0": SOUTH_ARR})

    msgs = _run(proc)

    assert any(m.startswith("Warning: available imagery covers only 60% of the AOI")
               for m in msgs)
    # Single tile => no mosaic lines.
    assert not any(m.startswith("Mosaicking") for m in msgs)
    assert not any("Mosaicked" in m for m in msgs)

    merged = saved["/tmp/out_band_b04.tif"]
    assert np.any(merged == 0)  # north half is still nodata


def test_sibling_that_adds_no_coverage_is_skipped():
    # A same-day sibling whose footprint is fully inside the selected tile's AOI
    # coverage must NOT be pulled in (no redundant downloads).
    scenes = [
        _scene("2024-08-30T10:18:16Z", (0.0, 0.0, 1.0, 1.0), "32TPS"),  # covers all
        _scene("2024-08-30T10:18:01Z", (0.2, 0.2, 0.4, 0.4), "32TPR"),  # inside -> redundant
    ]
    proc, saved = _processor(scenes, {"url-0": np.ones((4, 2), dtype=np.float32)})

    msgs = _run(proc)

    # Only one tile used: no mosaic line, no warning (100% covered by the first).
    assert not any(m.startswith("Mosaicking") for m in msgs)
    assert not any(m.startswith("Warning: available imagery") for m in msgs)
