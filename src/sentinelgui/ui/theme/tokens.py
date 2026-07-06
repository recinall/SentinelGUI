"""Design tokens — the single source of truth for every visual value.

Pure data, **no Qt imports**, so the token set is testable headless and reusable by the
QSS builder (:func:`sentinelgui.ui.theme.build_qss`). Widgets and stylesheets must draw
every color / spacing / radius / font value from here; a raw hex literal anywhere under
``ui/`` is a bug.

Two palettes share the same structure so light and dark can never drift. ``DARK`` uses
true dark surfaces (not an inversion of the light values) and keeps body text comfortably
legible against both ``surface`` and ``surface_alt``.
"""

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Palette:
    """A complete set of themeable colors, as ``#rrggbb`` strings."""

    surface: str
    surface_alt: str
    on_surface: str
    muted: str
    primary: str
    on_primary: str
    border: str
    success: str
    warning: str
    danger: str


LIGHT = Palette(
    surface="#ffffff",
    surface_alt="#f4f6f8",
    on_surface="#1b1f24",
    muted="#5b6672",
    primary="#2f6fed",
    on_primary="#ffffff",
    border="#d7dde3",
    success="#2e9e5b",
    warning="#c88a00",
    danger="#d33a3a",
)

DARK = Palette(
    surface="#15181d",
    surface_alt="#1e232b",
    on_surface="#e7edf3",
    muted="#9aa6b2",
    primary="#5b8cff",
    on_primary="#0b0e12",
    border="#2a313a",
    success="#3fbf78",
    warning="#e0a83a",
    danger="#ef5a5a",
)

PALETTES: dict[str, Palette] = {"light": LIGHT, "dark": DARK}

# Spacing / radius scales in pixels; typography as a small named set.
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
RADIUS = {"sm": 4, "md": 8, "lg": 12}
FONT = {
    "family": "Inter, Segoe UI, system-ui, sans-serif",
    "size": 13,
    "size_sm": 11,
    "size_xs": 10,
    "weight_bold": 600,
}

# Field names of :class:`Palette`, handy for tests and introspection.
PALETTE_FIELDS = tuple(f.name for f in fields(Palette))
