"""Characterization tests for the remaining calculate_index() code paths, plus
create_rgb_composite() and normalize_to_reflectance().

test_indices.py already freezes NDVI, NDWI and EVI (the "generic" formula path) so
those are intentionally NOT repeated here. This file freezes:

- The generic path (formula -> nan_to_num(nan=0, posinf=1, neginf=-1) -> clip(-1,1))
  for the remaining generic indices: NDSI, SI, BI, SAVI, NDRE, GNDVI.
- The MSI special case: ``s / np.where(n != 0, n, np.nan)`` then
  ``nan_to_num(nan=0.0, posinf=10.0, neginf=0.0)`` with NO clip to [-1, 1] afterwards
  (surprising: MSI values above 1.0 are preserved, unlike every other index).
- The IISV special case: a weighted blend of NDVI/NDRE/NDWI/MSI (MSI clipped to
  [0, 2] and halved *inside* the IISV formula only) then clipped to [-1, 1].
- create_rgb_composite(): a 2/98 percentile stretch computed over the WHOLE
  stacked (3, H, W) cube -- not per band -- plus its degenerate p98==p2 branch and
  its missing-band ValueError.
- normalize_to_reflectance(): the uint16 / uint8 / float dtype branches.

No network calls are made anywhere in this file.
"""

import numpy as np

from sentinelgui.core.processor import Sentinel2COGProcessor

DUMMY_AOI = {"bbox": [11.0, 46.0, 11.5, 46.5]}
DATE_START = "2024-06-01"
DATE_END = "2024-06-30"


def make_processor() -> Sentinel2COGProcessor:
    return Sentinel2COGProcessor(DUMMY_AOI, DATE_START, DATE_END)


def _post_process(raw: np.ndarray) -> np.ndarray:
    """Replicates the generic-path post-processing applied by calculate_index."""
    out = np.nan_to_num(raw, nan=0.0, posinf=1.0, neginf=-1.0)
    return np.clip(out, -1.0, 1.0)


# --- generic-path indices not already covered by test_indices.py ---


def test_ndsi_matches_formula():
    nir = np.array([[0.2, 0.4], [0.1, 0.6]], dtype=np.float32)
    swir = np.array([[0.5, 0.1], [0.1, 0.3]], dtype=np.float32)

    expected = _post_process((swir - nir) / (swir + nir))

    processor = make_processor()
    result = processor.calculate_index("NDSI", {"b08": nir, "b11": swir})

    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_si_matches_formula():
    red = np.array([[0.1, 0.3], [0.2, 0.4]], dtype=np.float32)
    swir = np.array([[0.4, 0.2], [0.2, 0.1]], dtype=np.float32)

    expected = _post_process((swir - red) / (swir + red))

    processor = make_processor()
    result = processor.calculate_index("SI", {"b04": red, "b11": swir})

    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_bi_matches_formula():
    blue = np.array([[0.05, 0.1], [0.02, 0.2]], dtype=np.float32)
    red = np.array([[0.1, 0.2], [0.05, 0.3]], dtype=np.float32)
    nir = np.array([[0.4, 0.3], [0.5, 0.1]], dtype=np.float32)
    swir = np.array([[0.3, 0.2], [0.1, 0.05]], dtype=np.float32)

    expected = _post_process(((swir + red) - (nir + blue)) / ((swir + red) + (nir + blue)))

    processor = make_processor()
    result = processor.calculate_index(
        "BI", {"b02": blue, "b04": red, "b08": nir, "b11": swir}
    )

    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_savi_matches_formula():
    red = np.array([[0.1, 0.2], [0.3, 0.05]], dtype=np.float32)
    nir = np.array([[0.5, 0.4], [0.3, 0.6]], dtype=np.float32)

    expected = _post_process(1.5 * ((nir - red) / (nir + red + 0.5)))

    processor = make_processor()
    result = processor.calculate_index("SAVI", {"b04": red, "b08": nir})

    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_ndre_matches_formula():
    rededge = np.array([[0.2, 0.3], [0.1, 0.4]], dtype=np.float32)
    nir = np.array([[0.5, 0.4], [0.3, 0.6]], dtype=np.float32)

    expected = _post_process((nir - rededge) / (nir + rededge))

    processor = make_processor()
    result = processor.calculate_index("NDRE", {"b05": rededge, "b08": nir})

    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_gndvi_matches_formula():
    green = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    nir = np.array([[0.5, 0.4], [0.3, 0.6]], dtype=np.float32)

    expected = _post_process((nir - green) / (nir + green))

    processor = make_processor()
    result = processor.calculate_index("GNDVI", {"b03": green, "b08": nir})

    np.testing.assert_allclose(result, expected, rtol=1e-6)


# --- MSI special case ---


def test_msi_normal_ratio_value():
    nir = np.array([[0.4]], dtype=np.float32)
    swir = np.array([[0.2]], dtype=np.float32)

    processor = make_processor()
    result = processor.calculate_index("MSI", {"b08": nir, "b11": swir})

    np.testing.assert_allclose(result, [[0.5]], rtol=1e-6)


def test_msi_zero_denominator_becomes_zero_not_nan():
    nir = np.array([[0.0, 0.4]], dtype=np.float32)
    swir = np.array([[0.3, 0.2]], dtype=np.float32)

    processor = make_processor()
    result = processor.calculate_index("MSI", {"b08": nir, "b11": swir})

    assert not np.isnan(result).any()
    assert result[0, 0] == 0.0


def test_msi_is_not_clipped_to_unit_range():
    # nir << swir -> ratio well above 1.0; MSI has no [-1, 1] clip, unlike every
    # other index, so this must survive intact (well above 1.0).
    nir = np.array([[0.1]], dtype=np.float32)
    swir = np.array([[0.9]], dtype=np.float32)

    processor = make_processor()
    result = processor.calculate_index("MSI", {"b08": nir, "b11": swir})

    expected = 0.9 / 0.1
    assert expected > 1.0  # sanity: the raw ratio really does exceed 1.0
    np.testing.assert_allclose(result, [[expected]], rtol=1e-6)


# --- IISV special case ---


def test_iisv_matches_hand_rolled_blend():
    green = np.array([[0.1, 0.2]], dtype=np.float32)
    red = np.array([[0.1, 0.15]], dtype=np.float32)
    rededge = np.array([[0.2, 0.25]], dtype=np.float32)
    nir = np.array([[0.5, 0.4]], dtype=np.float32)
    swir = np.array([[0.2, 0.3]], dtype=np.float32)

    bands = {"b03": green, "b04": red, "b05": rededge, "b08": nir, "b11": swir}

    processor = make_processor()

    ndvi = processor.calculate_index("NDVI", bands)
    ndre = processor.calculate_index("NDRE", bands)
    ndwi = processor.calculate_index("NDWI", bands)
    msi = processor.calculate_index("MSI", bands)

    msi_normalized = np.clip(msi, 0, 2) / 2
    expected = 0.4 * ndvi + 0.3 * ndre + 0.2 * ndwi + 0.1 * (1 - msi_normalized)
    expected = np.clip(expected, -1.0, 1.0)

    result = processor.calculate_index("IISV", bands)

    np.testing.assert_allclose(result, expected, rtol=1e-6)


# --- error paths shared by every algorithm ---


def test_calculate_index_raises_for_missing_band_generic_path():
    processor = make_processor()
    try:
        # SAVI requires b04 and b08; only b04 is supplied.
        processor.calculate_index("SAVI", {"b04": np.array([[0.1]], dtype=np.float32)})
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for missing required band")


# --- create_rgb_composite ---


def test_create_rgb_composite_stretch_uses_whole_cube_percentiles():
    red = np.array([[0.1, 0.9], [0.2, 0.8]], dtype=np.float32)
    green = np.array([[0.0, 1.0], [0.3, 0.7]], dtype=np.float32)
    blue = np.array([[0.4, 0.5], [0.1, 0.6]], dtype=np.float32)

    bands = {"b04": red, "b03": green, "b02": blue}

    rgb = np.stack([red, green, blue], axis=0)
    p2, p98 = np.percentile(rgb, (2, 98))
    expected = np.clip((rgb - p2) / (p98 - p2), 0, 1)

    processor = make_processor()
    result = processor.create_rgb_composite(bands)

    assert result.shape == (3, 2, 2)
    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_create_rgb_composite_degenerate_equal_input_returns_unstretched():
    # p98 == p2 when every pixel across all three bands is identical, hitting the
    # `else: rgb_stretched = rgb` branch (no stretch applied at all).
    red = np.full((2, 2), 0.5, dtype=np.float32)
    green = np.full((2, 2), 0.5, dtype=np.float32)
    blue = np.full((2, 2), 0.5, dtype=np.float32)

    bands = {"b04": red, "b03": green, "b02": blue}

    processor = make_processor()
    result = processor.create_rgb_composite(bands)

    expected = np.stack([red, green, blue], axis=0)
    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_create_rgb_composite_raises_for_missing_band():
    red = np.zeros((2, 2), dtype=np.float32)
    green = np.zeros((2, 2), dtype=np.float32)

    processor = make_processor()
    try:
        # Default rgb_bands = ['b04', 'b03', 'b02']; b02 is missing here.
        processor.create_rgb_composite({"b04": red, "b03": green})
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for missing RGB band")


# --- normalize_to_reflectance ---


def test_normalize_to_reflectance_uint16_uint8_and_float_branches():
    processor = make_processor()

    raw_uint16 = np.array([[0, 10000, 20000]], dtype=np.float32)
    result_uint16 = processor.normalize_to_reflectance(raw_uint16, "uint16")
    np.testing.assert_allclose(result_uint16, raw_uint16 / 10000.0, rtol=1e-6)

    raw_uint8 = np.array([[0, 128, 255]], dtype=np.float32)
    result_uint8 = processor.normalize_to_reflectance(raw_uint8, "uint8")
    np.testing.assert_allclose(result_uint8, raw_uint8 / 255.0, rtol=1e-6)

    raw_float = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
    result_float = processor.normalize_to_reflectance(raw_float, "float32")
    np.testing.assert_allclose(result_float, raw_float, rtol=1e-6)
    assert result_float is raw_float  # float branch is a passthrough, not a copy


# --- colorize_index (viewer-friendly companion) ---


def test_colorize_index_shape_dtype_and_direction():
    # A left->right ramp from -1 to +1; RdYlGn maps low->red, high->green, so the
    # +1 end must be greener (higher G, lower R) than the -1 end. This proves the
    # colorized companion is an ordinary 8-bit RGB cube, correctly oriented.
    processor = make_processor()
    ramp = np.tile(np.linspace(-1.0, 1.0, 5, dtype=np.float32), (3, 1))  # (3, 5)

    rgb = processor.colorize_index(ramp, "NDVI")

    assert rgb.shape == (3, 3, 5)  # (bands, H, W)
    assert rgb.dtype == np.uint8

    low = rgb[:, 0, 0]   # NDVI = -1  -> red end
    high = rgb[:, 0, -1]  # NDVI = +1 -> green end
    assert high[1] > low[1]  # greener
    assert low[0] > high[0]  # redder at the low end


def test_colorize_index_colormap_choice_differs_by_algorithm():
    # Gradient (vegetation) indices use RdYlGn; the others use RdYlBu_r. The two
    # colormaps disagree at the extremes, so the same value colorizes differently.
    processor = make_processor()
    data = np.full((2, 2), 0.9, dtype=np.float32)

    veg = processor.colorize_index(data, "NDVI")
    other = processor.colorize_index(data, "NDSI")

    assert not np.array_equal(veg, other)


# --- save_raster tiling policy ---


def test_save_raster_strips_small_rasters_and_tiles_large(tmp_path):
    import rasterio

    processor = make_processor()
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "width": 148,
        "height": 114,
        "count": 1,
        "crs": "EPSG:32632",
        "transform": rasterio.transform.from_origin(654294, 5088566, 10, 10),
    }

    small = np.zeros((114, 148), dtype=np.float32)
    small_path = tmp_path / "small.tif"
    processor.save_raster(small, profile, str(small_path), bit_depth=16, scale_range=(-1, 1))
    with rasterio.open(small_path) as s:
        # A tile larger than the raster makes GIMP mis-render it; small stays stripped,
        # so each block spans the full width (strip layout) rather than a 256-px tile.
        assert s.block_shapes[0][1] == s.width
        assert s.profile.get("tiled", False) is False

    big = np.zeros((300, 300), dtype=np.float32)
    big_profile = {**profile, "width": 300, "height": 300}
    big_path = tmp_path / "big.tif"
    processor.save_raster(big, big_profile, str(big_path), bit_depth=16, scale_range=(-1, 1))
    with rasterio.open(big_path) as s:
        assert s.block_shapes[0] == (256, 256)
