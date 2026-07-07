"""Headless tests for core.paths output-folder helpers (no Qt, no network, no I/O)."""

import pytest

from sentinelgui.core.paths import sanitize_folder_name, scene_datetime_folder


def test_sanitize_keeps_plain_name():
    assert sanitize_folder_name("Vigneto Trento") == "Vigneto-Trento"


def test_sanitize_collapses_whitespace_runs():
    assert sanitize_folder_name("  north   field \t vineyard ") == "north-field-vineyard"


def test_sanitize_strips_illegal_chars():
    assert sanitize_folder_name('a/b:c*d?"e<f>g|h\\i') == "abcdefghi"


def test_sanitize_strips_path_separators_so_result_is_single_component():
    assert "/" not in sanitize_folder_name("some/nested/path")
    assert "\\" not in sanitize_folder_name("some\\win\\path")


def test_sanitize_trims_leading_trailing_dots_and_hyphens():
    assert sanitize_folder_name("...my-place...") == "my-place"


def test_sanitize_keeps_unicode_letters():
    assert sanitize_folder_name("Caña Brava") == "Caña-Brava"


def test_sanitize_empty_returns_empty():
    assert sanitize_folder_name("") == ""
    assert sanitize_folder_name("   ") == ""


def test_sanitize_all_illegal_returns_empty():
    assert sanitize_folder_name('/\\:*?"<>|') == ""


def test_sanitize_reserved_device_name_returns_empty():
    assert sanitize_folder_name("CON") == ""
    assert sanitize_folder_name("lpt1") == ""


def test_sanitize_caps_length():
    result = sanitize_folder_name("x" * 500)
    assert 0 < len(result) <= 100


def test_datetime_folder_with_fractional_seconds_and_z():
    assert scene_datetime_folder("2024-08-30T10:18:16.322000Z") == "2024-08-30_101816"


def test_datetime_folder_without_fractional_seconds():
    assert scene_datetime_folder("2024-06-15T10:23:45Z") == "2024-06-15_102345"


def test_datetime_folder_without_trailing_z():
    assert scene_datetime_folder("2024-06-15T10:23:45") == "2024-06-15_102345"


def test_datetime_folder_empty_raises():
    with pytest.raises(ValueError):
        scene_datetime_folder("")


def test_datetime_folder_unparseable_raises():
    with pytest.raises(ValueError):
        scene_datetime_folder("not-a-date")
