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

from sentinelgui.core.basemap import BasemapDownloader, TransientTileError


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
    def fake_download_tile(x, y, zoom, source='osm', session=None):
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
    def fake_download_tile(x, y, zoom, source='osm', session=None):
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

    def fake_download_tile(x, y, zoom, source='osm', session=None):
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


# --- retry / backoff / throttle / sweep, all driven through a faked download_tile
# with an injected sleep + a zero-jitter rng so no real time or network is used. ---


class _ZeroRng:
    """An rng whose ``uniform`` always returns 0, so backoff delays are exact."""

    def uniform(self, a, b):
        return 0.0


def test_download_basemap_retries_transient_then_succeeds(monkeypatch):
    # One tile raises a transient error on its first attempt, then succeeds; the
    # in-loop retry must fill the hole (no failure) and back off exactly once.
    target = (136, 91)
    calls = {}

    def fake_download_tile(x, y, zoom, source='osm', session=None):
        calls[(x, y)] = calls.get((x, y), 0) + 1
        if (x, y) == target and calls[(x, y)] == 1:
            raise TransientTileError("simulated transient")
        return Image.new('RGB', (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)

    sleeps = []
    _, downloaded, failed, total_tiles = BasemapDownloader.download_basemap(
        _BBOX, _ZOOM, source='esri',
        backoff_base=0.5, sleep=sleeps.append, rng=_ZeroRng(),
    )

    assert failed == 0
    assert downloaded == _TOTAL
    assert total_tiles == _TOTAL
    assert calls[target] == 2  # failed once, retried once, then succeeded
    # equal-jitter backoff with zero jitter => backoff_base / 2; throttle default 0.
    assert sleeps == [0.25]


def test_download_basemap_honors_retry_after(monkeypatch):
    # A 429-style transient carrying Retry-After must sleep for exactly that value.
    target = (135, 90)
    calls = {}

    def fake_download_tile(x, y, zoom, source='osm', session=None):
        calls[(x, y)] = calls.get((x, y), 0) + 1
        if (x, y) == target and calls[(x, y)] == 1:
            raise TransientTileError("HTTP 429", retry_after=7.0)
        return Image.new('RGB', (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)

    sleeps = []
    _, _downloaded, failed, _total = BasemapDownloader.download_basemap(
        _BBOX, _ZOOM, source='esri', sleep=sleeps.append, rng=_ZeroRng(),
    )

    assert failed == 0
    assert sleeps == [7.0]  # Retry-After overrides the computed backoff


def test_download_basemap_does_not_retry_permanent_miss(monkeypatch):
    # A tile that returns None (permanent 404) is never retried and stays failed.
    target = (136, 91)
    calls = {}

    def fake_download_tile(x, y, zoom, source='osm', session=None):
        calls[(x, y)] = calls.get((x, y), 0) + 1
        if (x, y) == target:
            return None
        return Image.new('RGB', (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)

    sleeps = []
    _, downloaded, failed, _total = BasemapDownloader.download_basemap(
        _BBOX, _ZOOM, source='esri', sweep=False,
        sleep=sleeps.append, rng=_ZeroRng(),
    )

    assert failed == 1
    assert downloaded == _TOTAL - 1
    assert calls[target] == 1  # returned None once, never retried
    assert sleeps == []        # no backoff (permanent), no throttle


def test_download_basemap_sweep_recovers_failed_tile(monkeypatch):
    # A tile fails every attempt of the main pass (1 + retries), then recovers on
    # the final sweep; the sweep must paste it and emit its progress line.
    target = (136, 91)
    calls = {}

    def fake_download_tile(x, y, zoom, source='osm', session=None):
        calls[(x, y)] = calls.get((x, y), 0) + 1
        if (x, y) == target and calls[(x, y)] <= 4:  # retries=3 -> 4 main attempts
            raise TransientTileError("still down")
        return Image.new('RGB', (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)

    messages = []
    _, downloaded, failed, _total = BasemapDownloader.download_basemap(
        _BBOX, _ZOOM, source='esri', retries=3,
        sleep=lambda _d: None, rng=_ZeroRng(), progress=messages.append,
    )

    assert failed == 0
    assert downloaded == _TOTAL
    assert calls[target] == 5  # 4 failing main attempts + 1 succeeding sweep attempt
    assert "Retrying 1 failed tiles..." in messages


def test_download_basemap_throttles_between_requests(monkeypatch):
    # A positive throttle sleeps once after every tile; no backoff when all succeed.
    def fake_download_tile(x, y, zoom, source='osm', session=None):
        return Image.new('RGB', (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)

    sleeps = []
    BasemapDownloader.download_basemap(
        _BBOX, _ZOOM, source='esri',
        throttle=0.05, sleep=sleeps.append, rng=_ZeroRng(),
    )

    assert sleeps == [0.05] * _TOTAL


def test_download_basemap_default_throttle_is_zero(monkeypatch):
    # With the default throttle=0 the happy path never sleeps (speed unchanged).
    def fake_download_tile(x, y, zoom, source='osm', session=None):
        return Image.new('RGB', (256, 256))

    monkeypatch.setattr(BasemapDownloader, "download_tile", fake_download_tile)

    sleeps = []
    BasemapDownloader.download_basemap(
        _BBOX, _ZOOM, source='esri', sleep=sleeps.append,
    )

    assert sleeps == []
