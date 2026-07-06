"""Tokens are the canonical source of visual values — freeze their shape and integrity.

Pure-data tests: no Qt, no display. They guard that light and dark stay structurally
identical (so a QSS built from either can't reference a missing field) and that every
color is a well-formed ``#rrggbb`` hex string.
"""

import re

from sentinelgui.ui.theme.tokens import (
    DARK,
    FONT,
    LIGHT,
    PALETTE_FIELDS,
    PALETTES,
    RADIUS,
    SPACE,
    Palette,
)

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_light_and_dark_expose_the_same_fields():
    assert set(vars(LIGHT)) == set(vars(DARK)) == set(PALETTE_FIELDS)
    assert PALETTES == {"light": LIGHT, "dark": DARK}


def test_every_palette_value_is_a_hex_color():
    for palette in (LIGHT, DARK):
        for name in PALETTE_FIELDS:
            value = getattr(palette, name)
            assert _HEX.match(value), f"{palette}.{name} = {value!r} is not #rrggbb"


def test_light_and_dark_are_distinct_and_dark_is_actually_dark():
    # A true dark theme, not an inverted light one: dark surface must be darker.
    assert LIGHT.surface != DARK.surface
    assert int(DARK.surface[1:], 16) < int(LIGHT.surface[1:], 16)


def test_palette_is_frozen():
    p = Palette(**vars(LIGHT))
    try:
        p.surface = "#000000"
    except Exception as exc:  # frozen dataclass raises FrozenInstanceError
        assert "cannot assign" in str(exc) or "frozen" in type(exc).__name__.lower()
    else:
        raise AssertionError("Palette should be immutable")


def test_scale_tokens_are_present_and_numeric():
    for scale in (SPACE, RADIUS):
        assert scale and all(isinstance(v, int) for v in scale.values())
    assert isinstance(FONT["family"], str) and FONT["size"] > 0
