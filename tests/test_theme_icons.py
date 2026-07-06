"""The SVG icon loader must rasterize the bundled assets and honor the tint color.

Needs a live QApplication (QPixmap/QPainter), so it uses the shared ``qapp`` fixture and
runs under the offscreen platform. Freezes that every action icon exists, renders to a
non-null pixmap, and that a different color yields a different rasterization (proving the
``currentColor`` substitution actually takes effect).
"""

import pytest

from sentinelgui.ui.theme.icons import render_icon

ICON_NAMES = ["search", "basemap", "process"]


@pytest.mark.parametrize("name", ICON_NAMES)
def test_each_action_icon_renders(qapp, name):
    icon = render_icon(name, "#1b1f24")
    assert not icon.isNull()
    assert icon.availableSizes(), f"{name} produced no pixmap"


def test_tint_color_changes_the_pixels(qapp):
    dark = render_icon("search", "#000000", size=32).pixmap(32, 32).toImage()
    light = render_icon("search", "#ffffff", size=32).pixmap(32, 32).toImage()
    assert dark != light
