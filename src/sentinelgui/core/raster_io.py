"""Qt-free raster reading helpers for the results viewer.

Reads the GeoTIFFs produced by :mod:`sentinelgui.core.processor` and
:mod:`sentinelgui.core.basemap` into display-ready numpy arrays, and discovers the
known output files inside a scene folder. There is deliberately **no PySide6 import
here**: the numpy -> ``QImage`` conversion (the only Qt-touching part of the viewer)
lives in ``ui/widgets/raster_view.py``. rasterio, numpy and matplotlib are already
core dependencies (see ``processor.py``), so this module adds none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps

from sentinelgui.core.indices import ALGORITHMS


def load_normalized_band(path, *, percentiles: tuple[float, float] = (2, 98)) -> np.ndarray:
    """Read band 1 of ``path`` and percentile-stretch it to ``float64`` in ``[0, 1]``.

    Uses the low/high ``percentiles`` of the valid pixels (the same 2/98 idea as
    ``processor.create_rgb_composite``). Pixels equal to the raster's ``nodata`` value
    (if set) are excluded from the stretch and mapped to ``0.0`` — so they read as
    "below any threshold" and become transparent in the overlay. The returned array
    doubles as the threshold mask source for the viewer.
    """
    path = Path(path)
    with rasterio.open(path) as src:
        band = src.read(1).astype('float64')
        nodata = src.nodata

    valid = band != nodata if nodata is not None else np.ones(band.shape, dtype=bool)

    if valid.any():
        lo, hi = np.percentile(band[valid], percentiles)
    else:
        lo, hi = float(band.min()), float(band.max())

    norm = np.clip((band - lo) / (hi - lo), 0.0, 1.0) if hi > lo else np.zeros_like(band)
    norm[~valid] = 0.0
    return norm


def apply_colormap(norm2d: np.ndarray, cmap_name: str) -> np.ndarray:
    """Map a ``[0, 1]`` single-band array through a matplotlib colormap to ``(H, W, 3)`` uint8."""
    norm2d = np.asarray(norm2d, dtype='float64')
    rgba = colormaps[cmap_name](norm2d)
    return (rgba[..., :3] * 255).astype('uint8')


def load_display_rgb(path, *, colormap: str | None = None,
                     percentiles: tuple[float, float] = (2, 98)) -> np.ndarray:
    """Read ``path`` into a display-ready ``(H, W, 3)`` uint8 RGB array.

    A 3+ band raster with no forced ``colormap`` (``_rgb.tif``, ``_basemap_*.tif``,
    ``_color.tif``) is read as its first three bands and passed through when already
    uint8 (percentile-scaled otherwise). A single-band raster — or any raster with a
    forced ``colormap`` — is normalized via :func:`load_normalized_band` and colormapped
    (default ``"gray"``).
    """
    path = Path(path)
    with rasterio.open(path) as src:
        multiband = src.count >= 3 and colormap is None
        if multiband:
            rgb = np.transpose(src.read([1, 2, 3]), (1, 2, 0))

    if multiband:
        if rgb.dtype == np.uint8:
            return np.ascontiguousarray(rgb)
        rgb = rgb.astype('float64')
        lo, hi = np.percentile(rgb, percentiles)
        scaled = np.clip((rgb - lo) / (hi - lo), 0.0, 1.0) if hi > lo else np.zeros_like(rgb)
        return (scaled * 255).astype('uint8')

    norm = load_normalized_band(path, percentiles=percentiles)
    return apply_colormap(norm, colormap or 'gray')


def composite_over(base_rgb: np.ndarray, overlay_rgba: np.ndarray) -> np.ndarray:
    """Alpha-composite ``overlay_rgba`` (H, W, 4) over ``base_rgb`` (H, W, 3) -> (H, W, 3) uint8."""
    base = base_rgb.astype('float64')
    over = overlay_rgba.astype('float64')
    alpha = over[..., 3:4] / 255.0
    out = over[..., :3] * alpha + base * (1.0 - alpha)
    return np.clip(out, 0, 255).astype('uint8')


def save_composite_geotiff(base_rgb: np.ndarray, overlay_rgba: np.ndarray,
                           out_path, base_tif_path) -> str:
    """Composite the overlay over the base and write a georeferenced 8-bit RGB GeoTIFF.

    The CRS and transform are copied from ``base_tif_path`` (the base and overlay are
    already pixel-aligned on the scene's reference grid), so the flattened composite
    stays georeferenced — unlike ``core.overlay.create_overlay``, which writes via PIL
    and drops georeferencing. Written stripped and LZW-compressed, matching the RGB
    output written by ``processor.process_scene``. Returns the final path.
    """
    composite = composite_over(base_rgb, overlay_rgba)

    with rasterio.open(base_tif_path) as src:
        profile = src.profile.copy()

    profile.update({
        'driver': 'GTiff',
        'dtype': 'uint8',
        'count': 3,
        'height': composite.shape[0],
        'width': composite.shape[1],
        'photometric': 'RGB',
        'compress': 'lzw',
        'interleave': 'band',
        'tiled': False,
    })

    out_path = str(out_path)
    if not out_path.lower().endswith(('.tif', '.tiff')):
        out_path = out_path + '.tif'
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(out_path, 'w', **profile) as dst:
        dst.write(np.transpose(composite, (2, 0, 1)))

    return out_path


@dataclass
class SceneRasters:
    """Known output GeoTIFFs in a scene folder, grouped by how the viewer uses them.

    - ``base``: display-ready RGB backdrops (``_rgb.tif``, ``_basemap_*.tif``).
    - ``overlays``: display-ready RGB overlays (``_color.tif``).
    - ``singles``: single-band rasters (raw ``_{algo}.tif`` indices, ``_band_*.tif``) —
      shown colormapped, and usable as a threshold-able overlay.
    """

    base: list[Path] = field(default_factory=list)
    overlays: list[Path] = field(default_factory=list)
    singles: list[Path] = field(default_factory=list)


def _algo_suffixes() -> set[str]:
    return {a.lower() for a in ALGORITHMS}


def index_name(path) -> str | None:
    """Return the ``ALGORITHMS`` key a raw index file encodes, else ``None``.

    ``sentinel_ndvi.tif`` -> ``"NDVI"``; ``_color`` companions, ``_band_*`` and unknown
    names return ``None`` (a band or unknown single map is shown grayscale).
    """
    stem = Path(path).stem.lower()
    if stem.endswith('_color'):
        return None
    for algo in ALGORITHMS:
        if stem.endswith('_' + algo.lower()):
            return algo
    return None


def discover_rasters(folder) -> SceneRasters:
    """Scan ``folder`` for the known output ``.tif`` files and group them.

    Pure path logic (no raster reads). Non-``.tif`` files and the
    ``_reference_profile.json`` sidecar are ignored, as are unrecognized ``.tif`` names.
    """
    folder = Path(folder)
    result = SceneRasters()
    if not folder.is_dir():
        return result

    algos = _algo_suffixes()
    for path in sorted(folder.glob('*.tif')):
        stem = path.stem.lower()
        if stem.endswith('_color'):
            result.overlays.append(path)
        elif stem.endswith('_rgb') or '_basemap_' in stem:
            result.base.append(path)
        elif '_band_' in stem or any(stem.endswith('_' + algo) for algo in algos):
            result.singles.append(path)

    return result
