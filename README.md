# SentinelGUI

Desktop application for downloading and processing **Sentinel-2** satellite imagery:
search scenes via a STAC API, read Cloud-Optimized GeoTIFFs band-by-band, compute
spectral indices, build RGB composites, and download aligned basemaps.

> This project is being refactored from a flat monolith into an installable package.
> This README is a placeholder; full install/usage/build docs land with the release.

## Development

```bash
uv venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

python -m sentinelgui                      # GUI
pytest -q                                  # tests (headless, no network)
ruff check .                               # lint
```
