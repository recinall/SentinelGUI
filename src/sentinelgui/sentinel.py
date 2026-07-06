import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, calculate_default_transform, reproject, Resampling
import numpy as np
import argparse
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import requests
from datetime import datetime, timedelta
from shapely.geometry import box, shape
import matplotlib.pyplot as plt
import matplotlib.colors as colors

from sentinelgui.core.indices import ALGORITHMS, BAND_MAPPING


class Sentinel2COGProcessor:
    
    STAC_API = "https://earth-search.aws.element84.com/v1"
    COLLECTION_ID = "sentinel-2-l2a"
    
    BAND_MAPPING = BAND_MAPPING
    ALGORITHMS = ALGORITHMS

    def __init__(self, aoi: Dict, date_start: str, date_end: str, 
                 cloud_cover_max: float = 20.0):
        self.aoi = aoi
        self.date_start = date_start
        self.date_end = date_end
        self.cloud_cover_max = cloud_cover_max
        self.scenes = []
        
    def parse_aoi(self) -> Dict:
        if 'bbox' in self.aoi:
            bbox = self.aoi['bbox']
            return {'bbox': list(bbox)}
        elif 'type' in self.aoi:
            if self.aoi['type'] == 'Feature':
                geom = self.aoi['geometry']
            elif self.aoi['type'] in ['Polygon', 'MultiPolygon', 'Point', 'LineString']:
                geom = self.aoi
            else:
                raise ValueError(f"Unsupported GeoJSON type: {self.aoi['type']}")
            
            return {'intersects': geom}
        else:
            raise ValueError("AOI must contain 'type' (GeoJSON) or 'bbox' (list)")
    
    def search_scenes(self) -> List[Dict]:
        aoi_params = self.parse_aoi()
        
        try:
            start_dt = datetime.strptime(self.date_start, "%Y-%m-%d")
            end_dt = datetime.strptime(self.date_end, "%Y-%m-%d")
            
            start_rfc3339 = start_dt.strftime("%Y-%m-%dT00:00:00Z")
            end_rfc3339 = end_dt.strftime("%Y-%m-%dT23:59:59Z")
            
            datetime_str = f"{start_rfc3339}/{end_rfc3339}"
        except ValueError as e:
            print(f"Error parsing dates: {e}. Use format YYYY-MM-DD", file=sys.stderr)
            sys.exit(1)
        
        search_params = {
            "collections": [self.COLLECTION_ID],
            "datetime": datetime_str,
            "limit": 100,
            "query": {
                "eo:cloud_cover": {
                    "lt": self.cloud_cover_max
                }
            }
        }
        
        search_params.update(aoi_params)
        
        try:
            response = requests.post(
                f"{self.STAC_API}/search",
                json=search_params,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if not response.ok:
                error_msg = f"STAC API error ({response.status_code}): {response.text}"
                print(error_msg, file=sys.stderr)
                response.raise_for_status()
            
            data = response.json()
            
            self.scenes = data.get('features', [])
            
            print(f"Found {len(self.scenes)} scenes")
            for idx, scene in enumerate(self.scenes[:10]):
                props = scene['properties']
                print(f"  [{idx}] {props.get('datetime', 'N/A')} - "
                      f"Cloud: {props.get('eo:cloud_cover', 'N/A'):.1f}% - "
                      f"MGRS: {props.get('mgrs:utm_zone', '')}{props.get('mgrs:latitude_band', '')}{props.get('mgrs:grid_square', '')}")
            
            return self.scenes
            
        except requests.exceptions.RequestException as e:
            print(f"Error querying STAC API: {e}", file=sys.stderr)
            sys.exit(1)
    
    def get_scene_assets(self, scene_index: int = 0) -> Dict[str, str]:
        if not self.scenes:
            raise ValueError("No scenes available. Run search_scenes() first.")
        
        if scene_index >= len(self.scenes):
            raise ValueError(f"Scene index {scene_index} out of range (max: {len(self.scenes)-1})")
        
        scene = self.scenes[scene_index]
        assets = scene.get('assets', {})
        
        band_urls = {}
        for band_key, asset_key in self.BAND_MAPPING.items():
            if asset_key in assets:
                band_urls[band_key] = assets[asset_key]['href']
        
        return band_urls
    
    def get_bbox_from_aoi(self) -> Tuple[float, float, float, float]:
        if 'bbox' in self.aoi:
            return tuple(self.aoi['bbox'])
        elif 'type' in self.aoi:
            if self.aoi['type'] == 'Feature':
                geom = shape(self.aoi['geometry'])
            else:
                geom = shape(self.aoi)
            return geom.bounds
        else:
            raise ValueError("Cannot extract bbox from AOI")
    
    def load_band_window(self, cog_url: str, bbox: Tuple[float, float, float, float],
                         target_crs: str = "EPSG:4326", 
                         reference_profile: Dict = None) -> Tuple[np.ndarray, Dict]:
        try:
            with rasterio.open(cog_url) as src:
                
                if reference_profile is not None:
                    ref_transform = reference_profile['transform']
                    ref_crs = reference_profile['crs']
                    ref_height = reference_profile['height']
                    ref_width = reference_profile['width']
                    
                    data = np.zeros((ref_height, ref_width), dtype=np.float32)
                    
                    reproject(
                        source=rasterio.band(src, 1),
                        destination=data,
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=ref_transform,
                        dst_crs=ref_crs,
                        resampling=Resampling.bilinear
                    )
                    
                    data = self.normalize_to_reflectance(data, src.profile['dtype'])
                    return data, reference_profile
                
                bbox_native = transform_bounds(target_crs, src.crs, *bbox)
                
                dst_transform, dst_width, dst_height = calculate_default_transform(
                    src.crs,
                    src.crs,
                    src.width,
                    src.height,
                    *bbox_native,
                    resolution=abs(src.transform.a)
                )
                
                out_array = np.zeros((dst_height, dst_width), dtype=np.float32)
                
                reproject(
                    source=rasterio.band(src, 1),
                    destination=out_array,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=dst_transform,
                    dst_crs=src.crs,
                    resampling=Resampling.bilinear
                )
                
                profile = {
                    'driver': 'GTiff',
                    'dtype': 'float32',
                    'width': dst_width,
                    'height': dst_height,
                    'count': 1,
                    'crs': src.crs,
                    'transform': dst_transform,
                    'compress': 'lzw'
                }
                
                out_array = self.normalize_to_reflectance(out_array, src.profile['dtype'])
                
                return out_array, profile
                
        except Exception as e:
            print(f"Error loading band from {cog_url}: {e}", file=sys.stderr)
            raise
    
    def normalize_to_reflectance(self, data: np.ndarray, dtype) -> np.ndarray:
        dtype_str = str(dtype)
        
        if dtype_str == 'uint16':
            return data / 10000.0
        elif dtype_str == 'uint8':
            return data / 255.0
        elif 'float' in dtype_str:
            return data
        else:
            print(f"Warning: Unhandled dtype {dtype_str}, using raw values", file=sys.stderr)
            return data
    
    def calculate_index(self, algorithm: str, bands: Dict[str, np.ndarray]) -> np.ndarray:
        if algorithm not in self.ALGORITHMS:
            raise ValueError(f"Algorithm {algorithm} not supported")
        
        algo_def = self.ALGORITHMS[algorithm]
        required_bands = algo_def['bands']
        
        for band in required_bands:
            if band not in bands:
                raise ValueError(f"Missing required band {band} for {algorithm}")
        
        if algorithm == 'IISV':
            ndvi = self.calculate_index('NDVI', bands)
            ndre = self.calculate_index('NDRE', bands)
            ndwi = self.calculate_index('NDWI', bands)
            msi = self.calculate_index('MSI', bands)
            
            msi_normalized = np.clip(msi, 0, 2) / 2
            
            iisv = 0.4 * ndvi + 0.3 * ndre + 0.2 * ndwi + 0.1 * (1 - msi_normalized)
            
            return np.clip(iisv, -1.0, 1.0)
        
        elif algorithm == 'MSI':
            n = bands['b08']
            s = bands['b11']
            
            np.seterr(divide='ignore', invalid='ignore')
            msi = s / np.where(n != 0, n, np.nan)
            msi = np.nan_to_num(msi, nan=0.0, posinf=10.0, neginf=0.0)
            
            return msi
        
        else:
            band_arrays = [bands[b] for b in required_bands]
            
            np.seterr(divide='ignore', invalid='ignore')
            index_data = algo_def['formula'](*band_arrays)
            
            index_data = np.nan_to_num(index_data, nan=0.0, posinf=1.0, neginf=-1.0)
            index_data = np.clip(index_data, -1.0, 1.0)
            
            return index_data
    
    def save_raster(self, data: np.ndarray, profile: Dict, output_path: str,
                    bit_depth: int = 8, scale_range: Tuple[float, float] = None):
        
        profile = profile.copy()
        
        if bit_depth == 8:
            dtype_out = rasterio.uint8
            max_val = 255
        elif bit_depth == 16:
            dtype_out = rasterio.uint16
            max_val = 65535
        elif bit_depth == 32:
            dtype_out = rasterio.float32
            max_val = 1.0
        else:
            raise ValueError(f"Unsupported bit depth: {bit_depth}")
        
        if bit_depth in [8, 16]:
            if scale_range is None:
                data_min, data_max = data.min(), data.max()
            else:
                data_min, data_max = scale_range
            
            if data_max > data_min:
                data_scaled = ((data - data_min) / (data_max - data_min) * max_val)
            else:
                data_scaled = np.zeros_like(data)
            data_scaled = np.clip(data_scaled, 0, max_val).astype(dtype_out)
        else:
            data_scaled = data.astype(dtype_out)
        
        output_path = str(output_path)
        if not output_path.lower().endswith('.tif') and not output_path.lower().endswith('.tiff'):
            output_path = output_path + '.tif'
        
        profile.update({
            'dtype': dtype_out,
            'count': 1,
            'driver': 'GTiff',
            'compress': 'lzw',
            'tiled': True,
            'blockxsize': 256,
            'blockysize': 256,
            'interleave': 'band'
        })
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(data_scaled, 1)
            
            dst.update_tags(
                PROCESSING_SOFTWARE='Sentinel2COGProcessor',
                CREATION_DATE=datetime.now().isoformat(),
                SOURCE='Sentinel-2 L2A COG from AWS'
            )
        
        print(f"Saved GeoTIFF: {output_path}")
    
    def create_rgb_composite(self, bands: Dict[str, np.ndarray], 
                            rgb_bands: List[str] = ['b04', 'b03', 'b02']) -> np.ndarray:
        
        rgb_arrays = []
        for band in rgb_bands:
            if band not in bands:
                raise ValueError(f"Missing band {band} for RGB composite")
            rgb_arrays.append(bands[band])
        
        rgb = np.stack(rgb_arrays, axis=0)
        
        p2, p98 = np.percentile(rgb, (2, 98))
        if p98 > p2:
            rgb_stretched = np.clip((rgb - p2) / (p98 - p2), 0, 1)
        else:
            rgb_stretched = rgb
        
        return rgb_stretched
    
    def visualize_index(self, index_data: np.ndarray, algorithm: str,
                       mode: str = 'gradient', class_breaks: List[float] = None):
        
        fig, ax = plt.subplots(figsize=(12, 10))
        
        if mode == 'gradient':
            cmap = 'RdYlGn' if algorithm in ['NDVI', 'NDWI', 'SAVI', 'EVI', 'NDRE', 'GNDVI', 'IISV'] else 'RdYlBu_r'
            im = ax.imshow(index_data, cmap=cmap, vmin=-1, vmax=1)
            cbar = fig.colorbar(im, ax=ax, label=algorithm)
            ax.set_title(f"{algorithm} (Gradient)", fontsize=14, fontweight='bold')
        
        elif mode == 'class':
            if class_breaks:
                breaks = sorted(list(set(class_breaks)))
                if breaks[0] > -1:
                    breaks.insert(0, -1)
                if breaks[-1] < 1:
                    breaks.append(1)
            else:
                breaks = [-1, -0.1, 0.1, 0.3, 0.6, 1]
            
            n_classes = len(breaks) - 1
            labels = [f"{breaks[i]:.2f} to {breaks[i+1]:.2f}" for i in range(n_classes)]
            
            cmap = plt.get_cmap('RdYlGn', n_classes)
            norm = colors.BoundaryNorm(breaks, cmap.N)
            im = ax.imshow(index_data, cmap=cmap, norm=norm)
            
            tick_locs = [(breaks[i] + breaks[i+1]) / 2 for i in range(n_classes)]
            cbar = fig.colorbar(im, ax=ax, boundaries=breaks, ticks=tick_locs)
            cbar.set_ticklabels(labels, fontsize=9)
            cbar.set_label(f'{algorithm} Classes', fontsize=11)
            ax.set_title(f"{algorithm} (Classified)", fontsize=14, fontweight='bold')
        
        ax.axis('off')
        plt.tight_layout()
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Process Sentinel-2 COG data from AWS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --bbox 11.0 46.0 11.5 46.5 --date-start 2024-06-01 --date-end 2024-06-30 --algorithm NDVI --output ./output/ndvi
  %(prog)s --geojson aoi.geojson --date-start 2024-07-01 --date-end 2024-07-31 --bands b04 b08 --save-bands --output ./data
        """
    )
    
    aoi_group = parser.add_mutually_exclusive_group(required=True)
    aoi_group.add_argument('--bbox', type=float, nargs=4, metavar=('MINX', 'MINY', 'MAXX', 'MAXY'),
                          help="Bounding box in WGS84 (lon_min lat_min lon_max lat_max)")
    aoi_group.add_argument('--geojson', type=str, help="Path to GeoJSON file with AOI geometry")
    
    parser.add_argument('--date-start', type=str, required=True,
                       help="Start date (YYYY-MM-DD)")
    parser.add_argument('--date-end', type=str, required=True,
                       help="End date (YYYY-MM-DD)")
    parser.add_argument('--cloud-cover', type=float, default=20.0,
                       help="Maximum cloud cover percentage (default: 20)")
    parser.add_argument('--scene-index', type=int, default=0,
                       help="Index of scene to process from search results (default: 0)")
    
    parser.add_argument('--algorithm', type=str, choices=list(Sentinel2COGProcessor.ALGORITHMS.keys()),
                       help="Spectral index algorithm to calculate")
    parser.add_argument('--bands', type=str, nargs='+',
                       help="Specific bands to download (e.g., b02 b03 b04)")
    parser.add_argument('--rgb', action='store_true',
                       help="Create RGB composite (B04, B03, B02)")
    
    parser.add_argument('--save-bands', action='store_true',
                       help="Save individual band data locally")
    parser.add_argument('--output', type=str, required=True,
                       help="Output base path for saved files")
    parser.add_argument('--bit-depth', type=int, choices=[8, 16, 32], default=16,
                       help="Bit depth for output (default: 16)")
    
    parser.add_argument('--visualize', type=str, choices=['gradient', 'class'],
                       help="Visualize the calculated index")
    parser.add_argument('--class-breaks', type=float, nargs='+',
                       help="Custom class breaks for visualization (requires --visualize class)")
    
    args = parser.parse_args()
    
    if args.bbox:
        aoi = {'bbox': args.bbox}
    else:
        with open(args.geojson, 'r') as f:
            aoi = json.load(f)
    
    processor = Sentinel2COGProcessor(
        aoi=aoi,
        date_start=args.date_start,
        date_end=args.date_end,
        cloud_cover_max=args.cloud_cover
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
        required = Sentinel2COGProcessor.ALGORITHMS[args.algorithm]['bands']
        bands_to_load.update(required)
    
    if args.bands:
        bands_to_load.update(args.bands)
    
    if args.rgb:
        bands_to_load.update(['b04', 'b03', 'b02'])
    
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
        
        print(f"Loading {band}...", end=' ')
        
        data, band_profile = processor.load_band_window(
            band_urls[band], 
            bbox,
            reference_profile=reference_profile
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
        processor.save_raster(index_data, reference_profile, output_path, 
                            bit_depth=args.bit_depth, scale_range=(-1, 1))
        
        if args.visualize:
            processor.visualize_index(index_data, args.algorithm, 
                                     mode=args.visualize, 
                                     class_breaks=args.class_breaks)
    
    if args.rgb:
        print("\nCreating RGB composite...")
        rgb_data = processor.create_rgb_composite(loaded_bands)
        
        rgb_profile = reference_profile.copy()
        rgb_profile.update({'count': 3})
        
        output_path = f"{args.output}_rgb.tif"
        
        rgb_8bit = (rgb_data * 255).astype(np.uint8)
        
        rgb_profile.update({
            'dtype': rasterio.uint8,
            'count': 3,
            'photometric': 'RGB'
        })
        
        with rasterio.open(output_path, 'w', **rgb_profile) as dst:
            dst.write(rgb_8bit)
        
        print(f"Saved: {output_path}")
    
    print("\nProcessing complete!")


if __name__ == "__main__":
    main()