"""Headless tests for core.geo coordinate parsing (no Qt, no network, no I/O)."""

import math

import pytest

from sentinelgui.core.geo import parse_coordinate


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
