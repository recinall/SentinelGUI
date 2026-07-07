"""Headless tests for :mod:`sentinelgui.core.raster_io` and ``index_colormap``.

Tiny synthetic GeoTIFFs are written to ``tmp_path`` with rasterio (the
``test_processor_indices.py`` idiom); no network, no display.
"""

import numpy as np
import rasterio
from rasterio.transform import from_origin

from sentinelgui.core.indices import index_colormap
from sentinelgui.core.raster_io import (
    SceneRasters,
    apply_colormap,
    composite_over,
    discover_rasters,
    index_name,
    load_display_rgb,
    load_normalized_band,
    save_composite_geotiff,
)

CRS = "EPSG:32632"
TRANSFORM = from_origin(654294, 5088566, 10, 10)


def _write(path, data, *, nodata=None):
    """Write ``data`` (2D single-band or (bands, H, W)) as a GeoTIFF and return the path."""
    if data.ndim == 2:
        data = data[np.newaxis, :, :]
    count, height, width = data.shape
    profile = {
        "driver": "GTiff", "dtype": data.dtype, "count": count,
        "height": height, "width": width, "crs": CRS, "transform": TRANSFORM,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
    return path


def _touch(path):
    path.write_bytes(b"")
    return path


# --- index_colormap ---


def test_index_colormap_vegetation_vs_other():
    assert index_colormap("NDVI") == "RdYlGn"
    assert index_colormap("GNDVI") == "RdYlGn"
    assert index_colormap("NDSI") == "RdYlBu_r"
    assert index_colormap("SI") == "RdYlBu_r"
    assert index_colormap("") == "RdYlBu_r"  # unknown falls back


# --- load_display_rgb ---


def test_load_display_rgb_passes_three_band_uint8_through(tmp_path):
    rgb = np.random.default_rng(0).integers(0, 256, size=(3, 8, 10), dtype=np.uint8)
    path = _write(tmp_path / "x_rgb.tif", rgb)

    out = load_display_rgb(path)

    assert out.shape == (8, 10, 3)
    assert out.dtype == np.uint8
    np.testing.assert_array_equal(out, np.transpose(rgb, (1, 2, 0)))


def test_load_display_rgb_colormaps_a_single_band(tmp_path):
    band = np.linspace(0, 1, 12, dtype=np.float32).reshape(3, 4)
    path = _write(tmp_path / "x_ndvi.tif", band)

    out = load_display_rgb(path, colormap="gray")

    assert out.shape == (3, 4, 3)
    assert out.dtype == np.uint8
    # grayscale ramp: the max-value pixel is brighter than the min-value pixel
    assert out[-1, -1, 0] > out[0, 0, 0]


# --- load_normalized_band ---


def test_load_normalized_band_is_in_unit_range_and_stretches(tmp_path):
    band = np.arange(100, dtype=np.float32).reshape(10, 10)
    path = _write(tmp_path / "x_band_b04.tif", band)

    norm = load_normalized_band(path, percentiles=(0, 100))

    assert norm.dtype == np.float64
    assert norm.min() == 0.0 and norm.max() == 1.0
    # monotonic: last (largest) pixel maps to 1, first to 0
    assert norm[0, 0] == 0.0 and norm[-1, -1] == 1.0


def test_load_normalized_band_maps_nodata_to_zero(tmp_path):
    band = np.full((4, 4), 5.0, dtype=np.float32)
    band[0, 0] = -999.0
    path = _write(tmp_path / "x_ndre.tif", band, nodata=-999.0)

    norm = load_normalized_band(path)

    assert norm[0, 0] == 0.0  # nodata pixel forced transparent
    # valid pixels are all equal -> degenerate stretch -> 0, but never NaN
    assert not np.isnan(norm).any()


# --- apply_colormap ---


def test_apply_colormap_shape_and_dtype():
    norm = np.linspace(0, 1, 20).reshape(4, 5)
    out = apply_colormap(norm, "RdYlGn")
    assert out.shape == (4, 5, 3)
    assert out.dtype == np.uint8


# --- index_name ---


def test_index_name_parses_raw_index_and_ignores_others():
    assert index_name("/out/sentinel_ndvi.tif") == "NDVI"
    assert index_name("/out/sentinel_ndsi.tif") == "NDSI"
    assert index_name("/out/sentinel_ndvi_color.tif") is None
    assert index_name("/out/sentinel_band_b04.tif") is None
    assert index_name("/out/sentinel_rgb.tif") is None


# --- discover_rasters ---


def test_discover_rasters_groups_by_known_names(tmp_path):
    _touch(tmp_path / "sentinel_rgb.tif")
    _touch(tmp_path / "sentinel_basemap_esri_z16.tif")
    _touch(tmp_path / "sentinel_ndvi_color.tif")
    _touch(tmp_path / "sentinel_ndsi_color.tif")
    _touch(tmp_path / "sentinel_ndvi.tif")  # raw index
    _touch(tmp_path / "sentinel_band_b04.tif")
    _touch(tmp_path / "sentinel_reference_profile.json")  # ignored (not .tif)
    _touch(tmp_path / "unrelated.tif")  # unknown -> ignored

    found = discover_rasters(tmp_path)

    assert {p.name for p in found.base} == {
        "sentinel_rgb.tif", "sentinel_basemap_esri_z16.tif"}
    assert {p.name for p in found.overlays} == {
        "sentinel_ndvi_color.tif", "sentinel_ndsi_color.tif"}
    assert {p.name for p in found.singles} == {
        "sentinel_ndvi.tif", "sentinel_band_b04.tif"}


def test_discover_rasters_missing_folder_is_empty(tmp_path):
    found = discover_rasters(tmp_path / "does_not_exist")
    assert found == SceneRasters()


# --- composite_over / save_composite_geotiff ---


def test_composite_over_alpha_blends():
    base = np.zeros((1, 1, 3), dtype=np.uint8)
    over = np.array([[[200, 100, 50, 255]]], dtype=np.uint8)  # fully opaque red-ish
    np.testing.assert_array_equal(composite_over(base, over), [[[200, 100, 50]]])

    over_half = np.array([[[200, 0, 0, 128]]], dtype=np.uint8)  # ~50% over black
    out = composite_over(np.full((1, 1, 3), 0, np.uint8), over_half)
    assert 90 <= out[0, 0, 0] <= 110  # 200 * 128/255 ~= 100

    over_clear = np.array([[[255, 255, 255, 0]]], dtype=np.uint8)  # transparent
    base2 = np.array([[[10, 20, 30]]], dtype=np.uint8)
    np.testing.assert_array_equal(composite_over(base2, over_clear), base2)


def test_save_composite_geotiff_copies_georeferencing(tmp_path):
    base_path = _write(tmp_path / "sentinel_rgb.tif",
                       np.zeros((3, 5, 7), dtype=np.uint8))
    base_rgb = np.zeros((5, 7, 3), dtype=np.uint8)
    overlay_rgba = np.zeros((5, 7, 4), dtype=np.uint8)
    overlay_rgba[..., :3] = 255
    overlay_rgba[..., 3] = 255  # fully opaque white overlay

    out = save_composite_geotiff(base_rgb, overlay_rgba, tmp_path / "composite", base_path)

    assert out.endswith(".tif")
    with rasterio.open(out) as src:
        assert src.count == 3
        assert src.dtypes[0] == "uint8"
        assert src.width == 7 and src.height == 5
        assert src.crs.to_string() == CRS
        assert src.transform == TRANSFORM
        assert src.profile.get("tiled", False) is False
        # opaque white overlay wins over black base
        assert int(src.read(1).max()) == 255
