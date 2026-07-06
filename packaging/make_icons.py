"""Generate launcher icons from the committed master PNG.

Reads ``src/sentinelgui/resources/icon.png`` (the 2048x2048 master) and writes
platform launcher icons into the gitignored ``packaging/build-icons/`` dir:

* ``app.ico`` — multi-size Windows icon (16/24/32/48/64/128/256).
* ``256.png`` / ``512.png`` — Linux launcher icons (LANCZOS downscale).

The macOS ``.icns`` is built separately in CI via ``iconutil``; this script
never touches or resizes the committed master.
"""

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
MASTER = REPO_ROOT / "src" / "sentinelgui" / "resources" / "icon.png"
OUT_DIR = HERE / "build-icons"

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_SIZES = [256, 512]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with Image.open(MASTER) as img:
        master = img.convert("RGBA")

        ico_path = OUT_DIR / "app.ico"
        master.save(ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
        print(f"wrote {ico_path} ({', '.join(str(s) for s in ICO_SIZES)})")

        for size in PNG_SIZES:
            png_path = OUT_DIR / f"{size}.png"
            resized = master.resize((size, size), Image.LANCZOS)
            resized.save(png_path, format="PNG")
            print(f"wrote {png_path} ({size}x{size})")


if __name__ == "__main__":
    main()
