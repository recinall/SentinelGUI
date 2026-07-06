"""PyInstaller runtime hook: point GDAL/PROJ at the bundled data.

Runs *before* rasterio is imported. Sets ``GDAL_DATA``, ``PROJ_DATA`` and
``PROJ_LIB`` to the copies bundled inside the onedir bundle (under
``sys._MEIPASS``), probing the candidate relative paths that different wheels
and PyInstaller layouts use. Without this, a frozen rasterio build crashes with
"Cannot find proj.db" / "not recognized as a supported file format".
"""

import os
import sys

base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))

for env, candidates in {
    "GDAL_DATA": ("rasterio/gdal_data", "gdal_data", "share/gdal"),
    "PROJ_DATA": ("rasterio/proj_data", "proj_data", "share/proj"),
    "PROJ_LIB": ("rasterio/proj_data", "proj_data", "share/proj"),
}.items():
    for rel in candidates:
        p = os.path.join(base, rel)
        if os.path.isdir(p):
            os.environ[env] = p
            break
