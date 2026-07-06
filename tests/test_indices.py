"""Characterization tests for Sentinel2COGProcessor.calculate_index.

These tests freeze the CURRENT, observable behavior of the index math (formula +
nan_to_num + clip post-processing) using small hand-built numpy arrays with known
values, so a future refactor cannot silently change semantics.

No network calls are made: search_scenes() is never invoked. calculate_index() is
pure numpy math and needs no display either.
"""

import numpy as np

from sentinelgui.core.indices import BAND_MAPPING, BAND_RESOLUTION
from sentinelgui.core.processor import Sentinel2COGProcessor

DUMMY_AOI = {"bbox": [11.0, 46.0, 11.5, 46.5]}
DATE_START = "2024-06-01"
DATE_END = "2024-06-30"


def make_processor() -> Sentinel2COGProcessor:
    return Sentinel2COGProcessor(DUMMY_AOI, DATE_START, DATE_END)


def test_ndvi_matches_formula():
    red = np.array([[0.1, 0.2], [0.3, 0.5]], dtype=np.float32)
    nir = np.array([[0.5, 0.4], [0.3, 0.7]], dtype=np.float32)

    expected = (nir - red) / (nir + red)
    expected = np.nan_to_num(expected, nan=0.0, posinf=1.0, neginf=-1.0)
    expected = np.clip(expected, -1.0, 1.0)

    processor = make_processor()
    result = processor.calculate_index("NDVI", {"b04": red, "b08": nir})

    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_ndvi_zero_denominator_becomes_zero_not_nan():
    # Pixel (0, 0) has nir + red == 0 -> 0/0 -> NaN before post-processing.
    red = np.array([[0.0, 0.2], [0.3, 0.5]], dtype=np.float32)
    nir = np.array([[0.0, 0.4], [0.3, 0.7]], dtype=np.float32)

    processor = make_processor()
    result = processor.calculate_index("NDVI", {"b04": red, "b08": nir})

    assert not np.isnan(result).any()
    assert result[0, 0] == 0.0


def test_ndwi_matches_formula():
    green = np.array([[0.1, 0.3], [0.05, 0.4]], dtype=np.float32)
    nir = np.array([[0.5, 0.2], [0.05, 0.1]], dtype=np.float32)

    expected = (green - nir) / (green + nir)
    expected = np.nan_to_num(expected, nan=0.0, posinf=1.0, neginf=-1.0)
    expected = np.clip(expected, -1.0, 1.0)

    processor = make_processor()
    result = processor.calculate_index("NDWI", {"b03": green, "b08": nir})

    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_evi_matches_formula():
    blue = np.array([[0.0, 0.05], [0.02, 0.1]], dtype=np.float32)
    red = np.array([[0.0, 0.1], [0.05, 0.2]], dtype=np.float32)
    nir = np.array([[1.0, 0.4], [0.3, 0.5]], dtype=np.float32)

    expected = 2.5 * ((nir - red) / (nir + 6 * red - 7.5 * blue + 1))
    expected = np.nan_to_num(expected, nan=0.0, posinf=1.0, neginf=-1.0)
    expected = np.clip(expected, -1.0, 1.0)

    processor = make_processor()
    result = processor.calculate_index("EVI", {"b02": blue, "b04": red, "b08": nir})

    np.testing.assert_allclose(result, expected, rtol=1e-6)


def test_evi_clips_values_above_one():
    # blue=0, red=0, nir=1 -> raw EVI = 2.5 * (1 - 0) / (1 + 0 - 0 + 1) = 1.25 > 1
    blue = np.array([[0.0]], dtype=np.float32)
    red = np.array([[0.0]], dtype=np.float32)
    nir = np.array([[1.0]], dtype=np.float32)

    raw_evi = 2.5 * ((nir - red) / (nir + 6 * red - 7.5 * blue + 1))
    assert raw_evi[0, 0] > 1.0  # sanity check the raw (pre-clip) formula really overshoots

    processor = make_processor()
    result = processor.calculate_index("EVI", {"b02": blue, "b04": red, "b08": nir})

    assert result[0, 0] == 1.0


def test_calculate_index_raises_for_unknown_algorithm():
    processor = make_processor()
    try:
        processor.calculate_index("NOT_A_REAL_INDEX", {})
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for unsupported algorithm")


def test_calculate_index_raises_for_missing_band():
    processor = make_processor()
    red = np.array([[0.1]], dtype=np.float32)
    try:
        # NDVI requires b04 and b08; only b04 is supplied.
        processor.calculate_index("NDVI", {"b04": red})
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for missing required band")


def test_band_resolution_keys_mirror_band_mapping():
    # The resolution map must cover exactly the same band keys as BAND_MAPPING,
    # including the narrow-NIR "b08a" key, so the Auto reference selection can look
    # up every loadable band.
    assert set(BAND_RESOLUTION) == set(BAND_MAPPING)


def test_band_resolution_tiers_match_sentinel2_native_gsd():
    tier_10m = {"b02", "b03", "b04", "b08"}
    tier_20m = {"b05", "b06", "b07", "b08a", "b11", "b12"}
    tier_60m = {"b01", "b09"}

    assert {b for b, m in BAND_RESOLUTION.items() if m == 10} == tier_10m
    assert {b for b, m in BAND_RESOLUTION.items() if m == 20} == tier_20m
    assert {b for b, m in BAND_RESOLUTION.items() if m == 60} == tier_60m
