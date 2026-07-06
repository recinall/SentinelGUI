"""Headless tests for core.geo coordinate parsing (no Qt, no network, no I/O)."""

import math

import pytest

from sentinelgui.core.geo import bbox_from_center, parse_coordinate


def test_parses_plain_decimal():
    assert parse_coordinate("10.5") == 10.5


def test_parses_integer():
    assert parse_coordinate("46") == 46.0


def test_parses_negative_decimal():
    assert parse_coordinate("-10.5") == -10.5


def test_comma_decimal_separator():
    assert parse_coordinate("10,5") == 10.5


def test_surrounding_whitespace_ignored():
    assert parse_coordinate("  11.0  ") == 11.0


def test_parses_full_dms_with_quote():
    # 10°59'24.90" = 10 + 59/60 + 24.90/3600
    expected = 10 + 59 / 60 + 24.90 / 3600
    assert parse_coordinate("10°59'24.90\"") == pytest.approx(expected)


def test_parses_dms_without_seconds_quote():
    expected = 10 + 59 / 60 + 24.90 / 3600
    assert parse_coordinate("10°59'24.90") == pytest.approx(expected)


def test_parses_degrees_only_dms():
    assert parse_coordinate("45°") == 45.0


def test_parses_degrees_minutes_dms():
    assert parse_coordinate("45°30'") == pytest.approx(45.5)


def test_hemisphere_suffix_south_negates():
    assert parse_coordinate("46°30'S") == pytest.approx(-46.5)


def test_hemisphere_suffix_west_negates_decimal():
    assert parse_coordinate("11.5W") == pytest.approx(-11.5)


def test_hemisphere_prefix_north_positive():
    assert parse_coordinate("N46°30'") == pytest.approx(46.5)


def test_hemisphere_is_case_insensitive():
    assert parse_coordinate("11.5w") == pytest.approx(-11.5)


def test_dms_matches_equivalent_decimal():
    dms = parse_coordinate("11°30'00\"")
    assert dms == pytest.approx(11.5)


@pytest.mark.parametrize("bad", ["", "   ", "abc", "N", "10 20 30", "°"])
def test_unparseable_raises_value_error(bad):
    with pytest.raises(ValueError):
        parse_coordinate(bad)


def test_none_raises_value_error():
    with pytest.raises(ValueError):
        parse_coordinate(None)


def test_result_is_finite_float():
    value = parse_coordinate("10°59'24.90\"")
    assert isinstance(value, float)
    assert math.isfinite(value)


# -- bbox_from_center --


def test_bbox_at_equator_known_values():
    # width 222.64 km -> ±1° lon at the equator; height 221.148 km -> ±1° lat.
    bbox = bbox_from_center(0.0, 0.0, 222.64, 221.148)
    min_lon, min_lat, max_lon, max_lat = bbox
    assert min_lon == pytest.approx(-1.0)
    assert max_lon == pytest.approx(1.0)
    assert min_lat == pytest.approx(-1.0)
    assert max_lat == pytest.approx(1.0)


def test_bbox_is_symmetric_around_center():
    lat, lon = 46.0, 11.0
    min_lon, min_lat, max_lon, max_lat = bbox_from_center(lat, lon, 10.0, 10.0)
    assert (min_lon + max_lon) / 2 == pytest.approx(lon)
    assert (min_lat + max_lat) / 2 == pytest.approx(lat)


def test_bbox_longitude_span_widens_with_latitude():
    # Same width in km spans more degrees of longitude nearer the pole.
    span_low = bbox_from_center(0.0, 11.0, 100.0, 10.0)
    span_high = bbox_from_center(60.0, 11.0, 100.0, 10.0)
    width_low = span_low[2] - span_low[0]
    width_high = span_high[2] - span_high[0]
    assert width_high > width_low


def test_bbox_latitude_span_is_latitude_independent():
    low = bbox_from_center(0.0, 11.0, 10.0, 100.0)
    high = bbox_from_center(60.0, 11.0, 10.0, 100.0)
    assert (low[3] - low[1]) == pytest.approx(high[3] - high[1])


@pytest.mark.parametrize(
    "lat,lon,w,h",
    [
        (91.0, 0.0, 10.0, 10.0),
        (0.0, 181.0, 10.0, 10.0),
        (0.0, 0.0, 0.0, 10.0),
        (0.0, 0.0, 10.0, -5.0),
    ],
)
def test_bbox_invalid_inputs_raise(lat, lon, w, h):
    with pytest.raises(ValueError):
        bbox_from_center(lat, lon, w, h)
