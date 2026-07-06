"""Characterization tests for BasemapDownloader's slippy-map tile math.

Importing sentinel_gui (to reach BasemapDownloader) pulls in PySide6 at module
scope; tests/conftest.py sets QT_QPA_PLATFORM=offscreen before this import happens
so no real display is required. deg2num/num2deg are pure `math` functions and make
no network calls; download_tile/download_basemap (which do hit the network) are
intentionally NOT exercised here.
"""

from sentinelgui.sentinel_gui import BasemapDownloader


def test_deg2num_known_value_zoom_zero():
    # At zoom 0 the whole world is a single 1x1 tile grid.
    assert BasemapDownloader.deg2num(0, 0, 0) == (0, 0)


def test_deg2num_known_value_zoom_one():
    # zoom 1 -> 2x2 grid; (0, 0) sits exactly on the boundary of all four
    # quadrants and falls into tile (1, 1) per the current int() truncation.
    assert BasemapDownloader.deg2num(0, 0, 1) == (1, 1)


def test_deg2num_known_value_zoom_two():
    assert BasemapDownloader.deg2num(45, -90, 2) == (1, 1)


def test_deg2num_known_value_zoom_five():
    assert BasemapDownloader.deg2num(46.2, 11.2, 5) == (16, 11)


def _tile_bounds(x, y, zoom):
    """Return (lat_min, lat_max, lon_min, lon_max) for a tile, handling that
    num2deg gives the NW (top-left) corner and latitude decreases as y grows."""
    lat_top, lon_left = BasemapDownloader.num2deg(x, y, zoom)
    lat_bottom, lon_right = BasemapDownloader.num2deg(x + 1, y + 1, zoom)
    return lat_bottom, lat_top, lon_left, lon_right


def test_deg2num_num2deg_roundtrip_containment():
    samples = [
        (46.2, 11.2, 5),   # roughly northern Italy
        (0.0, 0.0, 3),     # equator / prime meridian
        (-33.9, 151.2, 8), # Sydney, southern hemisphere
        (51.5, -0.1, 10),  # London
        (80.0, 179.0, 6),  # high latitude (within Web Mercator's ~85.05 limit), near-antimeridian
    ]

    for lat, lon, zoom in samples:
        x, y = BasemapDownloader.deg2num(lat, lon, zoom)
        lat_min, lat_max, lon_min, lon_max = _tile_bounds(x, y, zoom)

        assert lat_min <= lat <= lat_max, (lat, lon, zoom, lat_min, lat_max)
        assert lon_min <= lon <= lon_max, (lat, lon, zoom, lon_min, lon_max)


def test_num2deg_matches_expected_nw_corner_zoom_zero():
    # The single zoom-0 tile spans the whole world; its NW corner is
    # (~85.05 N, -180 E) per the Web Mercator projection used here.
    lat, lon = BasemapDownloader.num2deg(0, 0, 0)
    assert lon == -180.0
    assert 85.0 < lat < 85.1
