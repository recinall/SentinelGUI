"""PyInstaller hook for rasterio.

rasterio does dynamic imports (``._shim``, ``.sample``, ``.vrt``, ``._features``,
``.crs``, ...) that PyInstaller's static analysis misses, and it ships its own
GDAL + PROJ data *inside* the wheel. Collect all three so the frozen app can
actually open a dataset at runtime.
"""

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# Dynamic imports: ._shim, .sample, .vrt, ._features, .crs, ...
hiddenimports = collect_submodules("rasterio")

# The compiled GDAL libs rasterio links against.
binaries = collect_dynamic_libs("rasterio")

# The GDAL + PROJ data files shipped inside the wheel.
datas = collect_data_files(
    "rasterio",
    includes=[
        "gdal_data/*",
        "proj_data/*",
        "share/gdal/*",
        "share/proj/*",
    ],
)
