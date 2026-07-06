"""Qt-free basemap tile-download and georeferencing logic.

This module holds the pure imagery-fetching code extracted from the GUI
monolith (``sentinel_gui.py``). It downloads slippy-map tiles (ESRI / Google /
OSM), stitches them into a single image, optionally resamples to a reference
grid, and writes a georeferenced GeoTIFF via rasterio. It imports only
math/requests/PIL/numpy/rasterio — never Qt.

``BasemapDownloader`` exposes four public staticmethods:

- ``deg2num`` / ``num2deg`` — pure slippy-map tile math (lat/lon <-> tile x/y).
- ``download_tile`` — network fetch of a single tile as a ``PIL.Image``.
- ``download_basemap`` — orchestration: computes the tile grid, downloads and
  stitches tiles, optionally aligns to a reference grid, and optionally writes
  the result to a GeoTIFF.

Progress is reported through an injected ``progress`` callback (default no-op),
so the headless path stays silent while the ``workers/`` layer can forward the
same messages onto a Qt ``Signal``.
"""

import math
from collections.abc import Callable
from io import BytesIO

import numpy as np
import rasterio
import requests
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_bounds


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
    def download_tile(x, y, zoom, source='osm'):
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

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return Image.open(BytesIO(response.content))
        except Exception:
            return None

    @staticmethod
    def download_basemap(bbox, zoom, source='esri', output_path=None,
                         target_width=None, target_height=None, target_transform=None,
                         progress: Callable[[str], None] = lambda _: None):
        progress(f"Downloading basemap tiles at zoom level {zoom}...")
        progress(f"Source: {source.upper()}")

        min_lon, min_lat, max_lon, max_lat = bbox

        if target_width and target_height and target_transform:
            progress(f"Aligning to reference: {target_width}x{target_height} pixels")

            x_min, y_max = BasemapDownloader.deg2num(max_lat, min_lon, zoom)
            x_max, y_min = BasemapDownloader.deg2num(min_lat, max_lon, zoom)

            if x_min > x_max:
                x_min, x_max = x_max, x_min
            if y_min > y_max:
                y_min, y_max = y_max, y_min

            tile_width = 256
            tile_height = 256

            cols = x_max - x_min + 1
            rows = y_max - y_min + 1

            if cols <= 0 or rows <= 0:
                raise ValueError(f"Invalid tile grid: {cols}x{rows} tiles. Check bbox coordinates.")

            total_tiles = cols * rows

            temp_width = cols * tile_width
            temp_height = rows * tile_height

            temp_result = Image.new('RGB', (temp_width, temp_height))

            downloaded = 0
            failed = 0

            for y in range(y_min, y_max + 1):
                for x in range(x_min, x_max + 1):
                    tile = BasemapDownloader.download_tile(x, y, zoom, source)

                    if tile:
                        col = x - x_min
                        row = y - y_min
                        temp_result.paste(tile, (col * tile_width, row * tile_height))
                        downloaded += 1
                    else:
                        failed += 1

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

            tile_width = 256
            tile_height = 256

            cols = x_max - x_min + 1
            rows = y_max - y_min + 1

            if cols <= 0 or rows <= 0:
                raise ValueError(f"Invalid tile grid: {cols}x{rows} tiles. Check bbox coordinates.")

            total_tiles = cols * rows

            result_width = cols * tile_width
            result_height = rows * tile_height

            result = Image.new('RGB', (result_width, result_height))

            downloaded = 0
            failed = 0

            for y in range(y_min, y_max + 1):
                for x in range(x_min, x_max + 1):
                    tile = BasemapDownloader.download_tile(x, y, zoom, source)

                    if tile:
                        col = x - x_min
                        row = y - y_min
                        result.paste(tile, (col * tile_width, row * tile_height))
                        downloaded += 1
                    else:
                        failed += 1

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
