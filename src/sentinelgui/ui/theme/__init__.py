"""Theme runtime: build QSS from tokens, apply a palette, toggle and persist.

The tokens in :mod:`sentinelgui.ui.theme.tokens` are canonical. :func:`build_qss`
renders a full stylesheet from a :class:`~sentinelgui.ui.theme.tokens.Palette` at apply
time, so light and dark share one structure and cannot drift — there are **no committed
``light.qss``/``dark.qss`` files** (a deliberate deviation from the target layout in
CLAUDE.md §4: tokens are the single source of truth).

:func:`load_theme` sets the Fusion style, a matching :class:`QPalette`, and the generated
stylesheet on the ``QApplication``, and records the choice via :class:`QSettings`.
:func:`toggle_theme` flips between the two modes; :func:`current_mode` reads the persisted
choice (defaulting to ``"light"``) so the last selection sticks across launches.

Widgets are targeted only through ``objectName`` (``QPushButton#accent``) and dynamic
properties (``QLabel[role="hint"]`` / ``[role="caption"]``, ``QCheckBox[role="index"]``);
no widget carries an inline color literal.
"""

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette

from .tokens import DARK, FONT, LIGHT, PALETTES, RADIUS, SPACE, Palette

_ORG = "SentinelGUI"
_APP = "app"
_DEFAULT_MODE = "light"


def build_qss(p: Palette) -> str:
    """Render the application stylesheet from a palette. Pure string; no Qt needed."""
    return f"""
    QWidget {{
        background-color: {p.surface};
        color: {p.on_surface};
        font-family: {FONT["family"]};
        font-size: {FONT["size"]}px;
    }}
    QGroupBox {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS["md"]}px;
        margin-top: {SPACE["md"]}px;
        padding: {SPACE["md"]}px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: {SPACE["sm"]}px;
        padding: 0 {SPACE["xs"]}px;
        color: {p.muted};
        font-weight: {FONT["weight_bold"]};
    }}
    QLabel {{ background-color: transparent; }}
    QLabel[role="hint"] {{ color: {p.muted}; font-style: italic; }}
    QLabel[role="caption"] {{ color: {p.muted}; font-size: {FONT["size_sm"]}px; }}
    QCheckBox[role="index"] {{ font-weight: {FONT["weight_bold"]}; }}
    QPushButton {{
        background-color: {p.surface_alt};
        color: {p.on_surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS["sm"]}px;
        padding: {SPACE["sm"]}px {SPACE["md"]}px;
    }}
    QPushButton:hover {{ border-color: {p.primary}; }}
    QPushButton:pressed {{ background-color: {p.border}; }}
    QPushButton:disabled {{ color: {p.muted}; border-color: {p.surface_alt}; }}
    QPushButton#accent {{
        background-color: {p.primary};
        color: {p.on_primary};
        border: none;
        font-weight: {FONT["weight_bold"]};
    }}
    QPushButton#accent:hover {{ background-color: {p.primary}; border: 1px solid {p.on_primary}; }}
    QPushButton#accent:disabled {{ background-color: {p.surface_alt}; color: {p.muted}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
        background-color: {p.surface_alt};
        color: {p.on_surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS["sm"]}px;
        padding: {SPACE["xs"]}px;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
    QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border-color: {p.primary};
    }}
    QTableWidget, QTableView {{
        background-color: {p.surface};
        alternate-background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: {RADIUS["sm"]}px;
        gridline-color: {p.border};
        selection-background-color: {p.primary};
        selection-color: {p.on_primary};
    }}
    QHeaderView::section {{
        background-color: {p.surface_alt};
        color: {p.muted};
        border: none;
        border-bottom: 1px solid {p.border};
        padding: {SPACE["xs"]}px {SPACE["sm"]}px;
    }}
    QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: {RADIUS["md"]}px; }}
    QTabBar::tab {{
        background-color: {p.surface_alt};
        color: {p.muted};
        border: 1px solid {p.border};
        border-bottom: none;
        border-top-left-radius: {RADIUS["sm"]}px;
        border-top-right-radius: {RADIUS["sm"]}px;
        padding: {SPACE["sm"]}px {SPACE["md"]}px;
    }}
    QTabBar::tab:selected {{ background-color: {p.surface}; color: {p.on_surface}; }}
    QProgressBar {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: {RADIUS["sm"]}px;
        text-align: center;
    }}
    QProgressBar::chunk {{ background-color: {p.primary}; border-radius: {RADIUS["sm"]}px; }}
    QMenuBar {{ background-color: {p.surface}; color: {p.on_surface}; }}
    QMenuBar::item:selected {{ background-color: {p.surface_alt}; }}
    QMenu {{ background-color: {p.surface}; color: {p.on_surface}; border: 1px solid {p.border}; }}
    QMenu::item:selected {{ background-color: {p.primary}; color: {p.on_primary}; }}
    QSlider::groove:horizontal {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: {RADIUS["sm"]}px;
        height: {SPACE["xs"]}px;
    }}
    QSlider::sub-page:horizontal {{
        background-color: {p.primary};
        border-radius: {RADIUS["sm"]}px;
    }}
    QSlider::handle:horizontal {{
        background-color: {p.primary};
        border: 1px solid {p.on_primary};
        width: {SPACE["md"]}px;
        margin: -{SPACE["sm"]}px 0;
        border-radius: {RADIUS["sm"]}px;
    }}
    QSlider::handle:horizontal:disabled {{
        background-color: {p.muted};
        border-color: {p.surface_alt};
    }}
    QGraphicsView {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: {RADIUS["sm"]}px;
    }}
    """


def _qpalette(p: Palette) -> QPalette:
    """Map tokens onto a QPalette so Fusion-drawn chrome matches the stylesheet."""
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(p.surface))
    pal.setColor(QPalette.WindowText, QColor(p.on_surface))
    pal.setColor(QPalette.Base, QColor(p.surface_alt))
    pal.setColor(QPalette.AlternateBase, QColor(p.surface))
    pal.setColor(QPalette.Text, QColor(p.on_surface))
    pal.setColor(QPalette.Button, QColor(p.surface_alt))
    pal.setColor(QPalette.ButtonText, QColor(p.on_surface))
    pal.setColor(QPalette.ToolTipBase, QColor(p.surface_alt))
    pal.setColor(QPalette.ToolTipText, QColor(p.on_surface))
    pal.setColor(QPalette.PlaceholderText, QColor(p.muted))
    pal.setColor(QPalette.Highlight, QColor(p.primary))
    pal.setColor(QPalette.HighlightedText, QColor(p.on_primary))
    pal.setColor(QPalette.Link, QColor(p.primary))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(p.muted))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(p.muted))
    return pal


def load_theme(app, mode: str) -> None:
    """Apply ``mode`` ('light'|'dark') to ``app`` and persist the choice."""
    p = PALETTES.get(mode, LIGHT)
    app.setStyle("Fusion")
    app.setPalette(_qpalette(p))
    app.setStyleSheet(build_qss(p))
    QSettings(_ORG, _APP).setValue("theme", mode)


def current_mode() -> str:
    """The persisted theme mode, defaulting to ``'light'`` on first launch."""
    mode = QSettings(_ORG, _APP).value("theme", _DEFAULT_MODE)
    return mode if mode in PALETTES else _DEFAULT_MODE


def toggle_theme(app) -> str:
    """Flip light<->dark, apply, persist, and return the new mode."""
    new_mode = "light" if current_mode() == "dark" else "dark"
    load_theme(app, new_mode)
    return new_mode


__all__ = [
    "DARK",
    "LIGHT",
    "Palette",
    "build_qss",
    "current_mode",
    "load_theme",
    "toggle_theme",
]
