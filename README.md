# SentinelGUI

Desktop application for downloading and processing **Sentinel-2** satellite imagery. It searches
scenes through a STAC API, reads Cloud-Optimized GeoTIFFs (COGs) band-by-band with `rasterio`,
computes spectral indices, builds RGB composites, and downloads aligned high-resolution basemaps.

The business logic is a Qt-free, headless-runnable `core/` package, so everything the GUI does is
also available from the command line.

- **AOI** — Area of Interest: a WGS84 bbox or a GeoJSON geometry.
- **Indices** — NDVI, NDWI, EVI, SAVI, NDRE, MSI, GNDVI, NDSI, SI, BI, IISV.
- **Basemap sources** — ESRI, Google, OSM.
- **Themes** — light and dark, switchable at runtime (View → Dark Mode).

## Install (development)

Requires **Python 3.12+** (rasterio 1.5 needs ≥ 3.12). [`uv`](https://docs.astral.sh/uv/) is
preferred; `pip` works as a fallback.

```bash
uv venv && source .venv/bin/activate       # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

## Run

```bash
python -m sentinelgui                       # launch the GUI (no arguments)
python -m sentinelgui --help                # headless CLI (any argument)
```

### CLI subcommands

With no arguments the entry point launches the GUI; any argument routes to the headless CLI.

| Command      | What it does                                                              |
|--------------|---------------------------------------------------------------------------|
| `search`     | List the Sentinel-2 scenes matching an AOI + date range.                  |
| `process`    | Search, then download bands / compute an index / build an RGB composite.  |
| `overlay`    | Colorize an index raster and optionally composite it over an RGB image.   |
| `basemap`    | Download and georeference a basemap for an AOI bbox.                       |
| `self-check` | Verify bundled GDAL/PROJ data resolve (smoke test for frozen builds).     |

```bash
# search scenes
python -m sentinelgui search --bbox 11.0 46.0 11.5 46.5 \
    --date-start 2024-06-01 --date-end 2024-06-30

# compute NDVI for the first matching scene
python -m sentinelgui process --bbox 11.0 46.0 11.5 46.5 \
    --date-start 2024-06-01 --date-end 2024-06-30 --algorithm NDVI --output ./output/ndvi

# download an ESRI basemap for the AOI
python -m sentinelgui basemap --bbox 11.0 46.0 11.5 46.5 --zoom 14 --output ./basemap.tif
```

Run `python -m sentinelgui <command> --help` for the full option list of any subcommand.

## Quality gates

```bash
ruff check .                                # lint (E, F, I, UP, B, SIM)
QT_QPA_PLATFORM=offscreen pytest -q         # tests run headless, no network, no display
```

## Build a desktop release

The app is frozen with **PyInstaller** (`onedir`). rasterio ships its own GDAL/PROJ data and uses
dynamic imports, so the build relies on the custom hooks under `packaging/hooks/` and a runtime
hook that points `GDAL_DATA` / `PROJ_DATA` at the bundled copies.

```bash
python packaging/make_icons.py              # derive app.ico + Linux PNGs from resources/icon.png
pyinstaller packaging/sentinelgui.spec --noconfirm
QT_QPA_PLATFORM=offscreen ./dist/SentinelGUI/SentinelGUI self-check   # must print "self-check OK" and exit 0
```

`self-check` opens an in-memory GeoTIFF and does an EPSG lookup; a green exit means GDAL and PROJ
are correctly wired in the frozen bundle.

### Per-OS installers

Installer configs live under `packaging/installers/`:

- **Linux** — AppImage via `linuxdeploy` (`linux/build-appimage.sh`, `linux/sentinelgui.desktop`).
- **Windows** — Inno Setup (`windows/sentinelgui.iss`) → `SentinelGUI-Setup.exe`.
- **macOS** — `create-dmg` over the `.app` bundle (`macos/build-dmg.sh`).

The `.github/workflows/release.yml` matrix builds, self-checks, and packages all three OSes on
`ubuntu-latest`, `windows-latest`, and `macos-latest`. Only the Linux path is verified locally;
Windows and macOS are validated in CI.

## Layout

```
src/sentinelgui/
├── app.py            # QApplication bootstrap + theme install
├── cli.py            # unified headless CLI (search / process / overlay / basemap / self-check)
├── core/             # pure logic — no Qt (processor, basemap, overlay, indices, models)
├── workers/          # QThread wrappers around core
├── ui/               # main_window + tabs + widgets + theme (tokens, QSS, icons)
└── resources/        # SVG icons + app icon
```
