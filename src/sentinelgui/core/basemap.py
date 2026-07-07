"""Qt-free basemap tile-download and georeferencing logic.

This module holds the pure imagery-fetching code extracted from the GUI
monolith (``sentinel_gui.py``). It downloads slippy-map tiles (ESRI / Google /
OSM), stitches them into a single image, optionally resamples to a reference
grid, and writes a georeferenced GeoTIFF via rasterio. It imports only
math/random/time/requests/PIL/numpy/rasterio — never Qt.

``BasemapDownloader`` exposes these public staticmethods:

- ``deg2num`` / ``num2deg`` — pure slippy-map tile math (lat/lon <-> tile x/y).
- ``download_tile`` — network fetch of a single tile as a ``PIL.Image``. It now
  distinguishes *transient* failures (timeout / connection reset / HTTP 429 / 5xx),
  which it raises as :class:`TransientTileError` so the caller can retry, from a
  *permanent* miss (404 and other 4xx), which it returns as ``None`` — a tile the
  server genuinely does not have, so retrying would only waste requests.
- ``download_basemap`` — orchestration: computes the tile grid, downloads and
  stitches tiles (with per-tile retry + exponential backoff, connection keep-alive
  via a shared ``requests.Session``, an optional inter-request throttle, and a final
  sweep that re-fetches still-failed tiles), optionally aligns to a reference grid,
  and optionally writes the result to a GeoTIFF.

The retry loop lives *above* ``download_tile`` (in ``_download_tile_with_retry``),
so tests can drive it by faking ``download_tile`` alone. The ``sleep`` and ``rng``
callables are injectable (defaulting to ``time.sleep`` / a module RNG) so the
backoff/throttle logic is unit-testable with no real time and no network.

Progress is reported through an injected ``progress`` callback (default no-op),
so the headless path stays silent while the ``workers/`` layer can forward the
same messages onto a Qt ``Signal``.
"""

import math
import random
import time
from collections.abc import Callable
from io import BytesIO

import numpy as np
import rasterio
import requests
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_bounds

_DEFAULT_RNG = random.Random()


class TransientTileError(Exception):
    """A retryable tile-download failure (timeout, reset, HTTP 429, or 5xx).

    ``retry_after`` carries the parsed ``Retry-After`` delay in seconds when the
    server supplied one (typically on a 429), else ``None`` so the caller falls
    back to exponential backoff.
    """

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after


def _parse_retry_after(value):
    """Parse a ``Retry-After`` header to a non-negative float of seconds, else None.

    Only the numeric ``delta-seconds`` form is honored; the HTTP-date form is
    ignored (the caller then falls back to exponential backoff).
    """
    if not value:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


class BasemapDownloader:

    @staticmethod
    def deg2num(lat_deg, lon_deg, zoom):
        lat_rad = math.radians(lat_deg)
        n = 2.0 ** zoom
        xtile = int((lon_deg + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return (xtile, ytile)

    @staticmethod
    def num2deg(xtile, ytile, zoom):
        n = 2.0 ** zoom
        lon_deg = xtile / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
        lat_deg = math.degrees(lat_rad)
        return (lat_deg, lon_deg)

    @staticmethod
    def download_tile(x, y, zoom, source='osm', session=None):
        headers = {
            'User-Agent': 'Sentinel2Processor/1.0'
        }

        if source == 'osm':
            url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
        elif source == 'esri':
            url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{y}/{x}"
        elif source == 'google':
            url = f"https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={zoom}"
        else:
            raise ValueError(f"Unknown source: {source}")

        getter = session.get if session is not None else requests.get

        try:
            response = getter(url, headers=headers, timeout=10)
        except requests.RequestException as e:
            raise TransientTileError(f"request failed: {e}") from e

        status = response.status_code
        if status == 429 or status >= 500:
            retry_after = _parse_retry_after(response.headers.get('Retry-After'))
            raise TransientTileError(f"HTTP {status}", retry_after=retry_after)
        if status >= 400:
            # 404 and other 4xx: the server genuinely has no such tile — not retryable.
            return None

        try:
            return Image.open(BytesIO(response.content))
        except Exception as e:
            raise TransientTileError(f"decode failed: {e}") from e

    @staticmethod
    def _download_tile_with_retry(x, y, zoom, source, *, session=None,
                                  retries=3, backoff_base=0.5, backoff_cap=30.0,
                                  sleep=time.sleep, rng=None):
        """Fetch one tile, retrying transient failures with backoff; else give up.

        Returns the tile ``Image`` on success, or ``None`` when the tile is a
        permanent miss (``download_tile`` returned ``None``) or all ``retries``
        transient attempts were exhausted. Backoff uses "equal jitter"
        (``d/2 + uniform(0, d/2)``) so retries spread out and don't stampede; a
        server-supplied ``Retry-After`` overrides the computed delay.
        """
        rng = rng if rng is not None else _DEFAULT_RNG
        attempt = 0
        while True:
            try:
                return BasemapDownloader.download_tile(x, y, zoom, source, session=session)
            except TransientTileError as e:
                if attempt >= retries:
                    return None
                if e.retry_after is not None:
                    delay = e.retry_after
                else:
                    ceiling = min(backoff_cap, backoff_base * (2 ** attempt))
                    delay = ceiling / 2 + rng.uniform(0, ceiling / 2)
                sleep(delay)
                attempt += 1

    @staticmethod
    def _download_grid(image, x_min, x_max, y_min, y_max, zoom, source,
                       tile_width, tile_height, *, session,
                       retries, backoff_base, backoff_cap, throttle, sweep,
                       sleep, rng, progress):
        """Download every tile in the grid into ``image``; return (downloaded, failed).

        Shared by both ``download_basemap`` branches. Each tile goes through
        ``_download_tile_with_retry``; a positive ``throttle`` sleeps between
        requests to stay gentle on the service. Tiles still missing after the main
        pass get one ``sweep`` with a longer backoff (the server may have recovered)
        — the ``"Retrying N failed tiles..."`` progress line fires only when there
        are failures, so the all-success path stays silent.
        """

        def fetch(x, y, base):
            return BasemapDownloader._download_tile_with_retry(
                x, y, zoom, source, session=session,
                retries=retries, backoff_base=base, backoff_cap=backoff_cap,
                sleep=sleep, rng=rng,
            )

        def paste(x, y, tile):
            image.paste(tile, ((x - x_min) * tile_width, (y - y_min) * tile_height))

        downloaded = 0
        failed_coords = []

        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                tile = fetch(x, y, backoff_base)
                if tile:
                    paste(x, y, tile)
                    downloaded += 1
                else:
                    failed_coords.append((x, y))
                if throttle > 0:
                    sleep(throttle)

        if sweep and failed_coords:
            progress(f"Retrying {len(failed_coords)} failed tiles...")
            still_failed = []
            for x, y in failed_coords:
                tile = fetch(x, y, backoff_base * 4)
                if tile:
                    paste(x, y, tile)
                    downloaded += 1
                else:
                    still_failed.append((x, y))
                if throttle > 0:
                    sleep(throttle)
            failed_coords = still_failed

        return downloaded, len(failed_coords)

    @staticmethod
    def download_basemap(bbox, zoom, source='esri', output_path=None,
                         target_width=None, target_height=None, target_transform=None,
                         progress: Callable[[str], None] = lambda _: None,
                         *, retries=3, backoff_base=0.5, backoff_cap=30.0,
                         throttle=0.0, sweep=True, sleep=time.sleep, rng=None):
        progress(f"Downloading basemap tiles at zoom level {zoom}...")
        progress(f"Source: {source.upper()}")

        min_lon, min_lat, max_lon, max_lat = bbox

        tile_width = 256
        tile_height = 256

        if target_width and target_height and target_transform:
            progress(f"Aligning to reference: {target_width}x{target_height} pixels")

            x_min, y_max = BasemapDownloader.deg2num(max_lat, min_lon, zoom)
            x_max, y_min = BasemapDownloader.deg2num(min_lat, max_lon, zoom)

            if x_min > x_max:
                x_min, x_max = x_max, x_min
            if y_min > y_max:
                y_min, y_max = y_max, y_min

            cols = x_max - x_min + 1
            rows = y_max - y_min + 1

            if cols <= 0 or rows <= 0:
                raise ValueError(f"Invalid tile grid: {cols}x{rows} tiles. Check bbox coordinates.")

            total_tiles = cols * rows

            temp_result = Image.new('RGB', (cols * tile_width, rows * tile_height))

            with requests.Session() as session:
                downloaded, failed = BasemapDownloader._download_grid(
                    temp_result, x_min, x_max, y_min, y_max, zoom, source,
                    tile_width, tile_height, session=session,
                    retries=retries, backoff_base=backoff_base, backoff_cap=backoff_cap,
                    throttle=throttle, sweep=sweep, sleep=sleep, rng=rng, progress=progress,
                )

            result = temp_result.resize((target_width, target_height), Image.Resampling.LANCZOS)

            if output_path:
                img_array = np.array(result)

                with rasterio.open(
                    output_path,
                    'w',
                    driver='GTiff',
                    height=target_height,
                    width=target_width,
                    count=3,
                    dtype=np.uint8,
                    crs=CRS.from_epsg(4326),
                    transform=target_transform,
                    compress='jpeg',
                    photometric='RGB'
                ) as dst:
                    for i in range(3):
                        dst.write(img_array[:, :, i], i + 1)

            return result, downloaded, failed, total_tiles

        else:
            x_min, y_max = BasemapDownloader.deg2num(max_lat, min_lon, zoom)
            x_max, y_min = BasemapDownloader.deg2num(min_lat, max_lon, zoom)

            if x_min > x_max:
                x_min, x_max = x_max, x_min
            if y_min > y_max:
                y_min, y_max = y_max, y_min

            cols = x_max - x_min + 1
            rows = y_max - y_min + 1

            if cols <= 0 or rows <= 0:
                raise ValueError(f"Invalid tile grid: {cols}x{rows} tiles. Check bbox coordinates.")

            total_tiles = cols * rows

            result_width = cols * tile_width
            result_height = rows * tile_height

            result = Image.new('RGB', (result_width, result_height))

            with requests.Session() as session:
                downloaded, failed = BasemapDownloader._download_grid(
                    result, x_min, x_max, y_min, y_max, zoom, source,
                    tile_width, tile_height, session=session,
                    retries=retries, backoff_base=backoff_base, backoff_cap=backoff_cap,
                    throttle=throttle, sweep=sweep, sleep=sleep, rng=rng, progress=progress,
                )

            if output_path:
                top_left_lat, top_left_lon = BasemapDownloader.num2deg(x_min, y_min, zoom)
                bottom_right_lat, bottom_right_lon = BasemapDownloader.num2deg(
                    x_max + 1, y_max + 1, zoom
                )

                transform = from_bounds(
                    top_left_lon, bottom_right_lat,
                    bottom_right_lon, top_left_lat,
                    result_width, result_height
                )

                img_array = np.array(result)

                with rasterio.open(
                    output_path,
                    'w',
                    driver='GTiff',
                    height=result_height,
                    width=result_width,
                    count=3,
                    dtype=np.uint8,
                    crs=CRS.from_epsg(4326),
                    transform=transform,
                    compress='jpeg',
                    photometric='RGB'
                ) as dst:
                    for i in range(3):
                        dst.write(img_array[:, :, i], i + 1)

            return result, downloaded, failed, total_tiles
