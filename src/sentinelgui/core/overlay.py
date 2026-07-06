"""Qt-free colorized-overlay generation logic.

This module holds the pure overlay-rendering code extracted from the standalone
``create_overlay.py`` CLI. It colorizes a grayscale spectral-index raster with a
matplotlib colormap (``class`` bins or a continuous ``gradient``) and, when an
RGB base image is supplied, alpha-composites the colorized index on top of it.
It imports only ``sys``/``numpy``/``PIL``/``matplotlib`` — never Qt.

Progress is reported through an injected ``progress`` callback (default no-op),
so the headless/CLI path stays silent while the ``workers/`` layer can forward
the same messages onto a Qt ``Signal``. The default no-op keeps the CLI's
stdout/stderr byte-identical.

Error handling deliberately keeps the original CLI vocabulary: fatal input
problems print to ``stderr`` and call ``sys.exit(1)`` rather than raising.
"""

import sys
from collections.abc import Callable

import matplotlib.colors
import numpy as np
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap
from PIL import Image

__all__ = ["create_overlay", "hex_to_rgba"]


def hex_to_rgba(hex_color):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (*rgb, 255)
    elif len(hex_color) == 8:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4, 6))
    else:
        raise ValueError(f"Invalid hex color format: {hex_color}")


def create_overlay(rgb_path, index_path, output_path, levels_pct, colors, opacity,
                   threshold_pct, mode,
                   progress: Callable[[str], None] = lambda _: None):
    """Colorize an index raster and (optionally) composite it over an RGB base.

    The 8-digit ``#RRGGBBAA`` form accepted by :func:`hex_to_rgba` takes its
    alpha byte verbatim, whereas the 6-digit ``#RRGGBB`` form forces alpha to
    255; this asymmetry is preserved intentionally.
    """

    base_image = None
    if rgb_path:
        try:
            base_image = Image.open(rgb_path).convert('RGBA')
        except OSError as e:
            print(f"Error opening RGB file: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        index_image = Image.open(index_path)
    except OSError as e:
        print(f"Error opening index file: {e}", file=sys.stderr)
        sys.exit(1)

    if base_image and base_image.size != index_image.size:
        index_image = index_image.resize(base_image.size, Image.Resampling.NEAREST)

    index_data = np.array(index_image)

    if index_data.ndim == 3:
        print("Warning: Index image appears to be RGB. Converting to grayscale.", file=sys.stderr)
        index_image = index_image.convert('L')
        index_data = np.array(index_image)

    if index_data.size == 0:
        print("Error: Index image is empty.", file=sys.stderr)
        sys.exit(1)

    progress("Loaded index image")

    try:
        levels_val = np.percentile(index_data, levels_pct)
        threshold_val = np.percentile(index_data, threshold_pct)
    except Exception as e:
        print(f"Error calculating percentiles: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(levels_val, np.ndarray):
        levels_val = np.array([levels_val])

    if np.any(np.isnan(levels_val)):
        print("Error: Percentile calculation resulted in NaN. Check index image.", file=sys.stderr)
        sys.exit(1)

    progress("Computed percentile levels")

    if mode == 'class':
        for i in range(1, len(levels_val)):
            if levels_val[i] <= levels_val[i-1]:
                dtype = levels_val.dtype if levels_val.dtype.kind == 'f' else np.float32
                levels_val[i] = levels_val[i-1] + np.finfo(dtype).eps

        if levels_val.size > 0 and levels_val[-1] <= levels_val[0]:
            dtype = levels_val.dtype if levels_val.dtype.kind == 'f' else np.float32
            levels_val[-1] = levels_val[0] + np.finfo(dtype).eps

        cmap = ListedColormap(colors)
        norm = BoundaryNorm(levels_val, cmap.N)

    elif mode == 'gradient':
        vmin = levels_val[0]
        vmax = levels_val[-1]

        if vmin >= vmax:
            cmap = ListedColormap([colors[0]])
            norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax + np.finfo(np.float32).eps)
        else:
            norm_levels = (levels_val - vmin) / (vmax - vmin)
            cmap_list = list(zip(norm_levels, colors, strict=False))
            cmap = LinearSegmentedColormap.from_list("custom_gradient", cmap_list)
            norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)

    rgba_data = cmap(norm(index_data))

    rgba_data_uint8 = (rgba_data * 255).astype(np.uint8)

    if base_image:
        try:
            threshold_val = np.percentile(index_data, threshold_pct)
        except Exception as e:
            print(f"Error calculating threshold percentile: {e}", file=sys.stderr)
            sys.exit(1)

        alpha_channel = np.full(index_data.shape, int(opacity * 255), dtype=np.uint8)

        mask = index_data < threshold_val
        alpha_channel[mask] = 0

        rgba_data_uint8[:, :, 3] = alpha_channel

        overlay_image = Image.fromarray(rgba_data_uint8, 'RGBA')

        final_image = Image.alpha_composite(base_image, overlay_image)
        final_image = final_image.convert('RGB')
    else:
        final_image = Image.fromarray(rgba_data_uint8, 'RGBA')

    progress("Built overlay image")
    progress(f"Saving overlay to {output_path}")

    try:
        final_image.save(output_path)
    except OSError as e:
        print(f"Error saving output file: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, ValueError) as e:
        print(
            f"Error saving as TIFF. Ensure output file has .tif extension. Error: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
