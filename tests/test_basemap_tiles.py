"""Characterization tests for BasemapDownloader's slippy-map tile math.

BasemapDownloader now lives in the Qt-free ``sentinelgui.core.basemap`` module,
so this import carries no Qt bindings dependency at all. deg2num/num2deg are pure
`math` functions and make no network calls. download_basemap's orchestration
(grid math + progress reporting) is covered below with ``download_tile``
monkeypatched so no real network call ever happens; the real network-hitting
``download_tile`` itself is intentionally NOT exercised here.
"""

import rasterio.transform
from PIL import Image

from sentinelgui.core.basemap import BasemapDownloader


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


# --- download_basemap: grid math + progress, with download_tile monkeypatched
# so no HTTP call ever happens. This bbox/zoom yields a known 2x2 tile grid. ---

_BBOX = (11.0, 46.0, 11.5, 46.5)  # (min_lon, min_lat, max_lon, max_lat)
_ZOOM = 8
_COLS, _ROWS = 2, 2
_TOTAL = _COLS * _ROWS


def test_download_basemap_grid_math_and_progress(monkeypatch):
    def fake_download_tile(x, y, zoom, source='osm'):
        return Image.new('RGB', (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)

    messages = []
    result, downloaded, failed, total_tiles = BasemapDownloader.download_basemap(
        _BBOX, _ZOOM, source='esri', progress=messages.append
    )

    assert downloaded == _TOTAL
    assert failed == 0
    assert total_tiles == _TOTAL
    assert result.size == (_COLS * 256, _ROWS * 256)

    assert messages[0] == f"Downloading basemap tiles at zoom level {_ZOOM}..."
    assert messages[1] == "Source: ESRI"
    assert not any(m.startswith("Aligning to reference:") for m in messages)


def test_download_basemap_aligned_progress(monkeypatch):
    def fake_download_tile(x, y, zoom, source='osm'):
        return Image.new('RGB', (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)

    min_lon, min_lat, max_lon, max_lat = _BBOX
    target_width, target_height = 100, 100
    target_transform = rasterio.transform.from_bounds(
        min_lon, min_lat, max_lon, max_lat, target_width, target_height
    )

    messages = []
    result, downloaded, failed, total_tiles = BasemapDownloader.download_basemap(
        _BBOX, _ZOOM, source='esri', output_path=None,
        target_width=target_width, target_height=target_height,
        target_transform=target_transform, progress=messages.append,
    )

    assert result.size == (target_width, target_height)
    assert downloaded == _TOTAL
    assert failed == 0
    assert total_tiles == _TOTAL
    assert (
        f"Aligning to reference: {target_width}x{target_height} pixels" in messages
    )


def test_download_basemap_counts_failed_tiles(monkeypatch):
    # x_min, y_min for this bbox/zoom is (135, 90); fail exactly one tile.
    failing_tile = (136, 91)

    def fake_download_tile(x, y, zoom, source='osm'):
        if (x, y) == failing_tile:
            return None
        return Image.new('RGB', (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)

    _, downloaded, failed, total_tiles = BasemapDownloader.download_basemap(
        _BBOX, _ZOOM, source='esri'
    )

    assert total_tiles == _TOTAL
    assert failed == 1
    assert downloaded == _TOTAL - 1
