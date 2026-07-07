"""Qt-free spectral-index registry for Sentinel-2 processing.

This module holds the pure data definitions shared across the app:

- ``BAND_MAPPING`` maps Sentinel-2 band identifiers (``b01``..``b12``) to the
  STAC asset names used by the processor.
- ``ALGORITHMS`` maps each spectral index name to the bands it needs and a
  ``formula`` callable. The lambdas use only arithmetic operators, so they work
  transparently on numpy arrays via broadcasting at call time without importing
  numpy here.

The ``IISV`` (and the ``MSI``) computation is intentionally special-cased inside
``Sentinel2COGProcessor.calculate_index`` in ``sentinel.py``; the ``IISV`` entry
below carries a placeholder ``formula`` (``lambda ...: None``) to preserve the
registry shape without duplicating that logic here.
"""

BAND_MAPPING = {
    'b01': 'coastal',
    'b02': 'blue',
    'b03': 'green',
    'b04': 'red',
    'b05': 'rededge1',
    'b06': 'rededge2',
    'b07': 'rededge3',
    'b08': 'nir',
    'b08a': 'nir08',
    'b09': 'nir09',
    'b11': 'swir16',
    'b12': 'swir22',
}

# Native ground sampling distance (metres) of each Sentinel-2 L2A band. Used to pick the
# finest-resolution band as the resampling reference grid when the user leaves the reference
# on "Auto". Keys mirror ``BAND_MAPPING`` exactly (note the ``b08a`` narrow-NIR key).
BAND_RESOLUTION = {
    'b01': 60,
    'b02': 10,
    'b03': 10,
    'b04': 10,
    'b05': 20,
    'b06': 20,
    'b07': 20,
    'b08': 10,
    'b08a': 20,
    'b09': 60,
    'b11': 20,
    'b12': 20,
}

ALGORITHMS = {
    'NDVI': {'bands': ['b04', 'b08'], 'formula': lambda r, n: (n - r) / (n + r)},
    'NDSI': {'bands': ['b08', 'b11'], 'formula': lambda n, s: (s - n) / (s + n)},
    'SI': {'bands': ['b04', 'b11'], 'formula': lambda r, s: (s - r) / (s + r)},
    'NDWI': {'bands': ['b03', 'b08'], 'formula': lambda g, n: (g - n) / (g + n)},
    'BI': {'bands': ['b02', 'b04', 'b08', 'b11'],
           'formula': lambda b, r, n, s: ((s + r) - (n + b)) / ((s + r) + (n + b))},
    'EVI': {'bands': ['b02', 'b04', 'b08'],
            'formula': lambda b, r, n: 2.5 * ((n - r) / (n + 6 * r - 7.5 * b + 1))},
    'SAVI': {'bands': ['b04', 'b08'],
             'formula': lambda r, n: 1.5 * ((n - r) / (n + r + 0.5))},
    'NDRE': {'bands': ['b05', 'b08'], 'formula': lambda re, n: (n - re) / (n + re)},
    'MSI': {'bands': ['b08', 'b11'], 'formula': lambda n, s: s / n},
    'GNDVI': {'bands': ['b03', 'b08'], 'formula': lambda g, n: (n - g) / (n + g)},
    'IISV': {'bands': ['b03', 'b04', 'b05', 'b08', 'b11'],
             'formula': lambda g, r, re, n, s: None},
}

# Vegetation/water indices that read best on a red-yellow-green ramp; everything else
# uses a diverging red-yellow-blue ramp. Kept in sync with the choice hard-coded in
# ``Sentinel2COGProcessor.colorize_index`` (the raster writer) so the on-disk ``_color``
# companion and the results viewer's live colormap agree.
GRADIENT_INDICES = {'NDVI', 'NDWI', 'SAVI', 'EVI', 'NDRE', 'GNDVI', 'IISV'}


def index_colormap(algorithm: str) -> str:
    """Return the matplotlib colormap name used to display a spectral index.

    ``RdYlGn`` for the vegetation/water indices in :data:`GRADIENT_INDICES`, ``RdYlBu_r``
    for the rest. Unknown or empty names fall back to ``RdYlBu_r``. Mirrors the colormap
    choice in ``Sentinel2COGProcessor.colorize_index``.
    """
    return 'RdYlGn' if algorithm in GRADIENT_INDICES else 'RdYlBu_r'
