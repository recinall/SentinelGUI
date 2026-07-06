"""Thin CLI shim for the colorized-overlay generator.

The overlay logic now lives in the Qt-free ``sentinelgui.core.overlay`` module.
This file re-exports ``create_overlay`` and ``hex_to_rgba`` for backward
compatibility and keeps the standalone argparse command-line entry point.
"""

import argparse

from sentinelgui.core.overlay import create_overlay, hex_to_rgba

__all__ = ["create_overlay", "hex_to_rgba", "main"]


def main():
    parser = argparse.ArgumentParser(description="Overlay a colorized index map onto an RGB image.")
    
    parser.add_argument("--rgb", help="Path to the base RGB image. If not provided, only the colorized index map will be generated.")
    parser.add_argument("--index", required=True, help="Path to the grayscale index map (8-bit or 16-bit).")
    parser.add_argument("--output", required=True, help="Path for the output composite image (e.g., output.tif).")
    
    parser.add_argument(
        "--opacity", 
        type=float, 
        default=0.7, 
        help="Opacity of the overlay (0.0 to 1.0). Default: 0.7 (Used only if --rgb is provided)"
    )
    
    parser.add_argument(
        "--threshold", 
        type=float, 
        default=10.0, 
        help="Index values below this percentile (0.0-100.0) will be fully transparent. Default: 10.0 (Used only if --rgb is provided)"
    )
    
    parser.add_argument(
        "--levels", 
        type=float, 
        nargs='+', 
        default=[0.0, 25.0, 50.0, 75.0, 100.0], 
        help="List of percentile bin edges for 'class' mode, or color stops for 'gradient' mode (0.0-100.0). "
             "Default: 0.0 25.0 50.0 75.0 100.0"
    )
    
    parser.add_argument(
        "--colors", 
        type=str, 
        nargs='+', 
        default=['#0000FF', "#FF0000", '#FFFF00', "#00FF00", "#007200"],
        help="List of hex colors. For 'class' mode, needs 1 fewer than levels. For 'gradient' mode, must match number of levels. "
             "Default: '#0000FF' '#00FFFF' '#FFFF00' '#FF0000'"
    )

    parser.add_argument(
        "--mode", 
        choices=['class', 'gradient'], 
        default='gradient', 
        help="Coloring mode: 'class' (discrete bins) or 'gradient' (continuous gradient). Default: class"
    )

    args = parser.parse_args()

    if args.opacity < 0.0 or args.opacity > 1.0:
        parser.error("--opacity must be between 0.0 and 1.0")

    if args.threshold < 0.0 or args.threshold > 100.0:
        parser.error("--threshold must be between 0.0 and 100.0")
        
    for level in args.levels:
        if level < 0.0 or level > 100.0:
            parser.error("--levels values must be between 0.0 and 100.0")

    if args.mode == 'class':
        if len(args.levels) != len(args.colors) + 1:
            parser.error(f"For 'class' mode, number of levels ({len(args.levels)}) must be one more than the number of colors ({len(args.colors)}).")
    elif args.mode == 'gradient':
        if len(args.levels) != len(args.colors):
            parser.error(f"For 'gradient' mode, number of levels ({len(args.levels)}) must equal the number of colors ({len(args.colors)}).")
        if len(args.levels) < 2:
            parser.error(f"For 'gradient' mode, you need at least 2 levels/colors.")

    try:
        for color in args.colors:
            hex_to_rgba(color)
    except ValueError as e:
        parser.error(f"Invalid hex color in --colors: {e}")

    create_overlay(
        args.rgb, 
        args.index, 
        args.output, 
        args.levels, 
        args.colors, 
        args.opacity, 
        args.threshold,
        args.mode
    )

if __name__ == "__main__":
    main()