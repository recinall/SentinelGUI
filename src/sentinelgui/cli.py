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

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
