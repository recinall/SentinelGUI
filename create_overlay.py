import sys
import argparse
import numpy as np
from PIL import Image
from matplotlib.colors import ListedColormap, BoundaryNorm, LinearSegmentedColormap
import matplotlib.colors

def hex_to_rgba(hex_color):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (*rgb, 255)
    elif len(hex_color) == 8:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4, 6))
    else:
        raise ValueError(f"Invalid hex color format: {hex_color}")

def create_overlay(rgb_path, index_path, output_path, levels_pct, colors, opacity, threshold_pct, mode):
    
    base_image = None
    if rgb_path:
        try:
            base_image = Image.open(rgb_path).convert('RGBA')
        except IOError as e:
            print(f"Error opening RGB file: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        index_image = Image.open(index_path)
    except IOError as e:
        print(f"Error opening index file: {e}", file=sys.stderr)
        sys.exit(1)

    if base_image and base_image.size != index_image.size:
        index_image = index_image.resize(base_image.size, Image.Resampling.NEAREST)

    index_data = np.array(index_image)
    
    if index_data.ndim == 3:
        print(f"Warning: Index image appears to be RGB. Converting to grayscale.", file=sys.stderr)
        index_image = index_image.convert('L')
        index_data = np.array(index_image)

    if index_data.size == 0:
        print(f"Error: Index image is empty.", file=sys.stderr)
        sys.exit(1)

    try:
        levels_val = np.percentile(index_data, levels_pct)
        threshold_val = np.percentile(index_data, threshold_pct)
    except Exception as e:
        print(f"Error calculating percentiles: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not isinstance(levels_val, np.ndarray):
        levels_val = np.array([levels_val])

    if np.any(np.isnan(levels_val)):
        print(f"Error: Percentile calculation resulted in NaN. Check index image.", file=sys.stderr)
        sys.exit(1)

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
            cmap_list = list(zip(norm_levels, colors))
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

    try:
        final_image.save(output_path)
    except IOError as e:
        print(f"Error saving output file: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, ValueError) as e:
        print(f"Error saving as TIFF. Ensure output file has .tif extension. Error: {e}", file=sys.stderr)
        sys.exit(1)

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