"""Unified headless command-line interface for SentinelGUI.

Qt-free by construction: this module drives the ``core/`` layer directly and never
imports the Qt workers. It exposes the subcommands behind
``python -m sentinelgui <subcommand>``; the GUI stays the zero-argument default
(the GUI-vs-CLI dispatch lives in :mod:`sentinelgui.__main__`).

The ``process`` subcommand is a verbatim port of the former standalone
``sentinel.py`` argparse entry point (same prints, the same ``✓``/``[REFERENCE]``
band-load narration, the same ``sys.exit`` paths), so its stdout/stderr/exit-code
behavior is unchanged. ``search`` is the search-only prefix of that same flow.
"""

import argparse
import json
import sys

import numpy as np
import rasterio

from sentinelgui.core.basemap import BasemapDownloader
from sentinelgui.core.overlay import create_overlay, hex_to_rgba
from sentinelgui.core.processor import Sentinel2COGProcessor

__all__ = ["build_parser", "main"]


def _resolve_aoi(args: argparse.Namespace) -> dict:
    """Build the AOI dict from ``--bbox`` or ``--geojson`` (mirrors the old shim)."""
    if args.bbox:
        return {"bbox": args.bbox}
    with open(args.geojson) as f:
        return json.load(f)


def _add_search_arguments(parser: argparse.ArgumentParser) -> None:
    """AOI + date-range + cloud-cover options shared by ``search`` and ``process``."""
    aoi_group = parser.add_mutually_exclusive_group(required=True)
    aoi_group.add_argument(
        "--bbox", type=float, nargs=4, metavar=("MINX", "MINY", "MAXX", "MAXY"),
        help="Bounding box in WGS84 (lon_min lat_min lon_max lat_max)",
    )
    aoi_group.add_argument("--geojson", type=str, help="Path to GeoJSON file with AOI geometry")

    parser.add_argument("--date-start", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--date-end", type=str, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--cloud-cover", type=float, default=20.0,
        help="Maximum cloud cover percentage (default: 20)",
    )


def _cmd_search(args: argparse.Namespace) -> None:
    """List the Sentinel-2 scenes matching the AOI / date-range without processing."""
    aoi = _resolve_aoi(args)

    processor = Sentinel2COGProcessor(
        aoi=aoi,
        date_start=args.date_start,
        date_end=args.date_end,
        cloud_cover_max=args.cloud_cover,
    )

    print("Searching for Sentinel-2 scenes...")
    processor.search_scenes()

    if not processor.scenes:
        print("No scenes found matching criteria", file=sys.stderr)
        sys.exit(1)


def _cmd_process(args: argparse.Namespace) -> None:
    """Search, then process a single scene (verbatim port of the old ``sentinel.py``)."""
    aoi = _resolve_aoi(args)

    processor = Sentinel2COGProcessor(
        aoi=aoi,
        date_start=args.date_start,
        date_end=args.date_end,
        cloud_cover_max=args.cloud_cover,
    )

    print("Searching for Sentinel-2 scenes...")
    processor.search_scenes()

    if not processor.scenes:
        print("No scenes found matching criteria", file=sys.stderr)
        sys.exit(1)

    print(f"\nProcessing scene {args.scene_index}...")
    band_urls = processor.get_scene_assets(args.scene_index)

    bbox = processor.get_bbox_from_aoi()

    bands_to_load = set()

    if args.algorithm:
        required = Sentinel2COGProcessor.ALGORITHMS[args.algorithm]["bands"]
        bands_to_load.update(required)

    if args.bands:
        bands_to_load.update(args.bands)

    if args.rgb:
        bands_to_load.update(["b04", "b03", "b02"])

    if not bands_to_load:
        print("No processing specified. Use --algorithm, --bands, or --rgb", file=sys.stderr)
        sys.exit(1)

    print(f"\nLoading bands: {', '.join(sorted(bands_to_load))}")

    loaded_bands = {}
    reference_profile = None

    for band in sorted(bands_to_load):
        if band not in band_urls:
            print(f"Warning: Band {band} not available in scene", file=sys.stderr)
            continue

        print(f"Loading {band}...", end=" ")

        data, band_profile = processor.load_band_window(
            band_urls[band],
            bbox,
            reference_profile=reference_profile,
        )

        loaded_bands[band] = data

        if reference_profile is None:
            reference_profile = band_profile
            print(f"✓ ({data.shape}) [REFERENCE]")
        else:
            print(f"✓ ({data.shape}) [resampled to reference]")

        if args.save_bands:
            output_path = f"{args.output}_band_{band}.tif"
            processor.save_raster(data, reference_profile, output_path, bit_depth=args.bit_depth)

    if args.algorithm:
        print(f"\nCalculating {args.algorithm}...")
        index_data = processor.calculate_index(args.algorithm, loaded_bands)

        output_path = f"{args.output}_{args.algorithm.lower()}.tif"
        processor.save_raster(
            index_data, reference_profile, output_path,
            bit_depth=args.bit_depth, scale_range=(-1, 1),
        )

        if args.visualize:
            processor.visualize_index(
                index_data, args.algorithm,
                mode=args.visualize,
                class_breaks=args.class_breaks,
            )

    if args.rgb:
        print("\nCreating RGB composite...")
        rgb_data = processor.create_rgb_composite(loaded_bands)

        rgb_profile = reference_profile.copy()
        rgb_profile.update({"count": 3})

        output_path = f"{args.output}_rgb.tif"

        rgb_8bit = (rgb_data * 255).astype(np.uint8)

        rgb_profile.update({
            "dtype": rasterio.uint8,
            "count": 3,
            "photometric": "RGB",
        })

        with rasterio.open(output_path, "w", **rgb_profile) as dst:
            dst.write(rgb_8bit)

        print(f"Saved: {output_path}")

    print("\nProcessing complete!")


def _cmd_overlay(args: argparse.Namespace) -> None:
    """Colorize an index raster and (optionally) composite it over an RGB image.

    Verbatim port of the former ``create_overlay.py``; validation errors go through
    the overlay subparser's ``error()`` (usage + ``SystemExit(2)``), matching the shim.
    """
    if args.opacity < 0.0 or args.opacity > 1.0:
        args.parser.error("--opacity must be between 0.0 and 1.0")

    if args.threshold < 0.0 or args.threshold > 100.0:
        args.parser.error("--threshold must be between 0.0 and 100.0")

    for level in args.levels:
        if level < 0.0 or level > 100.0:
            args.parser.error("--levels values must be between 0.0 and 100.0")

    if args.mode == "class":
        if len(args.levels) != len(args.colors) + 1:
            args.parser.error(
                f"For 'class' mode, number of levels ({len(args.levels)}) must be one more "
                f"than the number of colors ({len(args.colors)})."
            )
    elif args.mode == "gradient":
        if len(args.levels) != len(args.colors):
            args.parser.error(
                f"For 'gradient' mode, number of levels ({len(args.levels)}) must equal "
                f"the number of colors ({len(args.colors)})."
            )
        if len(args.levels) < 2:
            args.parser.error("For 'gradient' mode, you need at least 2 levels/colors.")

    try:
        for color in args.colors:
            hex_to_rgba(color)
    except ValueError as e:
        args.parser.error(f"Invalid hex color in --colors: {e}")

    create_overlay(
        args.rgb,
        args.index,
        args.output,
        args.levels,
        args.colors,
        args.opacity,
        args.threshold,
        args.mode,
    )


def _cmd_basemap(args: argparse.Namespace) -> None:
    """Download and georeference a basemap for the AOI bbox (headless).

    Wraps :meth:`core.basemap.BasemapDownloader.download_basemap` on its
    non-aligned path and streams its progress to stdout. The reference-alignment
    path (fitting a basemap to an existing raster's grid) is deliberately not
    exposed here — it is a GUI-only concern driven by a loaded reference profile.
    """
    _result, downloaded, failed, total = BasemapDownloader.download_basemap(
        args.bbox,
        args.zoom,
        args.source,
        args.output,
        progress=print,
    )

    message = f"Downloaded {downloaded}/{total} tiles successfully"
    if failed > 0:
        message += f" ({failed} failed)"

    print(message)


def _cmd_self_check(args: argparse.Namespace) -> None:
    """Prove GDAL and PROJ data are wired — the smoke test for a frozen build.

    A PyInstaller bundle can import ``rasterio`` yet still fail at runtime when
    ``GDAL_DATA`` / ``PROJ_DATA`` are missing (see the ``geospatial-packaging`` recipe).
    This exercises both: a round-trip 1x1 GeoTIFF through an in-memory dataset (GDAL
    drivers + ``GDAL_DATA``) and an EPSG lookup (needs ``proj.db`` from ``PROJ_DATA``).
    Exits 0 on success, 1 on any failure, so CI can gate the build on it.
    """
    try:
        from rasterio.crs import CRS
        from rasterio.io import MemoryFile
        from rasterio.transform import from_bounds

        transform = from_bounds(0, 0, 1, 1, 1, 1)
        with MemoryFile() as memfile:
            with memfile.open(
                driver="GTiff", height=1, width=1, count=1,
                dtype="uint8", crs=CRS.from_epsg(4326), transform=transform,
            ) as dataset:
                dataset.write(np.zeros((1, 1, 1), dtype="uint8"))
            with memfile.open() as dataset:
                _ = dataset.read(1)
                epsg = dataset.crs.to_epsg()
        if epsg != 4326:
            raise RuntimeError(f"CRS round-trip returned EPSG:{epsg}, expected 4326")
    except Exception as e:  # noqa: BLE001 - report any wiring failure and fail the build
        print(f"self-check FAILED: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"self-check OK (GDAL {rasterio.gdal_version()}, PROJ data resolved)")
    sys.exit(0)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser with one subparser per subcommand."""
    parser = argparse.ArgumentParser(
        prog="sentinelgui",
        description="Headless SentinelGUI tools. Run with no arguments to launch the GUI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="Search for Sentinel-2 scenes and list them")
    _add_search_arguments(search)
    search.set_defaults(func=_cmd_search)

    process = subparsers.add_parser(
        "process",
        help="Search then process a single Sentinel-2 scene",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --bbox 11.0 46.0 11.5 46.5 --date-start 2024-06-01 "
            "--date-end 2024-06-30 --algorithm NDVI --output ./output/ndvi\n"
            "  %(prog)s --geojson aoi.geojson --date-start 2024-07-01 "
            "--date-end 2024-07-31 --bands b04 b08 --save-bands --output ./data\n"
        ),
    )
    _add_search_arguments(process)
    process.add_argument(
        "--scene-index", type=int, default=0,
        help="Index of scene to process from search results (default: 0)",
    )
    process.add_argument(
        "--algorithm", type=str, choices=list(Sentinel2COGProcessor.ALGORITHMS.keys()),
        help="Spectral index algorithm to calculate",
    )
    process.add_argument(
        "--bands", type=str, nargs="+", help="Specific bands to download (e.g., b02 b03 b04)",
    )
    process.add_argument("--rgb", action="store_true", help="Create RGB composite (B04, B03, B02)")
    process.add_argument(
        "--save-bands", action="store_true", help="Save individual band data locally",
    )
    process.add_argument(
        "--output", type=str, required=True, help="Output base path for saved files",
    )
    process.add_argument(
        "--bit-depth", type=int, choices=[8, 16, 32], default=16,
        help="Bit depth for output (default: 16)",
    )
    process.add_argument(
        "--visualize", type=str, choices=["gradient", "class"],
        help="Visualize the calculated index",
    )
    process.add_argument(
        "--class-breaks", type=float, nargs="+",
        help="Custom class breaks for visualization (requires --visualize class)",
    )
    process.set_defaults(func=_cmd_process)

    overlay = subparsers.add_parser(
        "overlay", help="Overlay a colorized index map onto an RGB image",
    )
    overlay.add_argument(
        "--rgb",
        help="Path to the base RGB image. If not provided, only the colorized "
             "index map will be generated.",
    )
    overlay.add_argument(
        "--index", required=True, help="Path to the grayscale index map (8-bit or 16-bit).",
    )
    overlay.add_argument(
        "--output", required=True,
        help="Path for the output composite image (e.g., output.tif).",
    )
    overlay.add_argument(
        "--opacity", type=float, default=0.7,
        help="Opacity of the overlay (0.0 to 1.0). Default: 0.7 "
             "(Used only if --rgb is provided)",
    )
    overlay.add_argument(
        "--threshold", type=float, default=10.0,
        help="Index values below this percentile (0.0-100.0) will be fully "
             "transparent. Default: 10.0 (Used only if --rgb is provided)",
    )
    overlay.add_argument(
        "--levels", type=float, nargs="+", default=[0.0, 25.0, 50.0, 75.0, 100.0],
        help="List of percentile bin edges for 'class' mode, or color stops for "
             "'gradient' mode (0.0-100.0). Default: 0.0 25.0 50.0 75.0 100.0",
    )
    overlay.add_argument(
        "--colors", type=str, nargs="+",
        default=["#0000FF", "#FF0000", "#FFFF00", "#00FF00", "#007200"],
        help="List of hex colors. For 'class' mode, needs 1 fewer than levels. "
             "For 'gradient' mode, must match number of levels.",
    )
    overlay.add_argument(
        "--mode", choices=["class", "gradient"], default="gradient",
        help="Coloring mode: 'class' (discrete bins) or 'gradient' (continuous "
             "gradient). Default: gradient",
    )
    overlay.set_defaults(func=_cmd_overlay, parser=overlay)

    basemap = subparsers.add_parser(
        "basemap", help="Download a georeferenced basemap for an AOI bounding box",
    )
    basemap.add_argument(
        "--bbox", type=float, nargs=4, required=True, metavar=("MINX", "MINY", "MAXX", "MAXY"),
        help="Bounding box in WGS84 (lon_min lat_min lon_max lat_max)",
    )
    basemap.add_argument("--zoom", type=int, required=True, help="Slippy-map zoom level")
    basemap.add_argument(
        "--source", choices=["esri", "google", "osm"], default="esri",
        help="Imagery source (default: esri)",
    )
    basemap.add_argument(
        "--output", type=str, required=True, help="Output GeoTIFF path for the basemap",
    )
    basemap.set_defaults(func=_cmd_basemap)

    self_check = subparsers.add_parser(
        "self-check",
        help="Verify bundled GDAL/PROJ data resolve (smoke test for frozen builds)",
    )
    self_check.set_defaults(func=_cmd_self_check)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
