"""The generated QSS must come from tokens and carry no stray literals.

``build_qss`` is a pure token->string transform, so these run without a QApplication
(importing the module under the offscreen platform from conftest is enough). They freeze
the contract the widget cleanup depends on: the light/dark stylesheets differ, each
references only its own palette's surface color, and none of the old inline hex
(``#4CAF50``/``#666``/``#999``) leaks back in.
"""

import re

from sentinelgui.ui.theme import build_qss, current_mode, toggle_theme
from sentinelgui.ui.theme.tokens import DARK, LIGHT

_LEGACY_HEX = ("#4CAF50", "#666", "#999")


def test_qss_is_built_from_the_given_palette():
    light = build_qss(LIGHT)
    dark = build_qss(DARK)
    assert LIGHT.surface in light and DARK.surface in dark
    assert light != dark
    # The dark surface must not appear in the light sheet and vice versa.
    assert DARK.surface not in light
    assert LIGHT.surface not in dark


def test_qss_carries_no_legacy_inline_literals():
    for sheet in (build_qss(LIGHT), build_qss(DARK)):
        for legacy in _LEGACY_HEX:
            assert legacy.lower() not in sheet.lower()


def test_qss_targets_role_and_objectname_hooks():
    sheet = build_qss(LIGHT)
    for selector in ('QPushButton#accent', 'QLabel[role="hint"]',
                     'QLabel[role="caption"]', 'QCheckBox[role="index"]'):
        assert selector in sheet


def test_every_color_in_qss_belongs_to_the_palette():
    # No hex string appears that isn't one of the palette's own tokens.
    palette_colors = {c.lower() for c in vars(LIGHT).values()}
    found = {m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}", build_qss(LIGHT))}
    assert found <= palette_colors, f"unexpected colors: {found - palette_colors}"


def test_toggle_flips_and_persists(qapp):
    start = current_mode()
    flipped = toggle_theme(qapp)
    assert flipped != start
    assert current_mode() == flipped
    back = toggle_theme(qapp)
    assert back == start
    assert current_mode() == start
