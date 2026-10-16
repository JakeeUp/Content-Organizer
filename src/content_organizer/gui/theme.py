"""Design tokens, light/dark palettes and the application style sheet.

Every colour the GUI uses comes from the active :class:`Palette`; widgets never hardcode
hex values. :class:`ThemeManager` resolves the user's appearance choice (System / Light /
Dark) to a palette, follows the OS colour scheme when set to System, and emits
:attr:`ThemeManager.changed` so custom-painted widgets can repaint.

Visual language: neutral surfaces separated by hairline borders, one accent colour, muted
category colours grouped by media type (videos blue/teal, audio purple, images amber,
projects rose, other grey), an 8 px spacing grid and 8-12 px radii.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

from content_organizer.categories import Category

APP_DISPLAY_NAME: Final = "Content Organizer"
ORG_NAME: Final = "content-organizer"
SETTINGS_KEY: Final = "appearance/theme"

# Spacing grid and radii (px).
SPACE: Final = 8
RADIUS_SM: Final = 6
RADIUS: Final = 8
RADIUS_LG: Final = 12

# Type scale (px).
FONT_TITLE: Final = 24
FONT_H2: Final = 18
FONT_H3: Final = 14
FONT_BODY: Final = 13
FONT_CAPTION: Final = 12

_UI_FAMILIES: Final = (
    "Segoe UI Variable Text",
    "Segoe UI Variable",
    "Segoe UI",
    "Inter",
    "SF Pro Text",
    "Helvetica Neue",
    "Noto Sans",
    "Cantarell",
    "Arial",
)
_DISPLAY_FAMILIES: Final = (
    "Segoe UI Variable Display",
    "Segoe UI Variable",
    "Segoe UI",
    "Inter",
    "SF Pro Display",
    "Helvetica Neue",
    "Noto Sans",
    "Arial",
)
_MONO_FAMILIES: Final = ("Cascadia Mono", "Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono")


class Appearance(StrEnum):
    """The user's choice in Settings; ``SYSTEM`` follows the OS colour scheme."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class Palette:
    """One complete set of colour tokens (hex strings)."""

    name: str
    bg: str  # content area
    sidebar: str
    surface: str  # cards
    surface_alt: str  # secondary buttons, segmented track
    raised: str  # tooltips, menus, selected segment
    input: str
    hover: str
    pressed: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str  # selection / selected chip background
    accent_text: str  # accent used as text on surfaces (links)
    on_accent: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    track: str  # empty part of bars and progress
    categories: Mapping[Category, str] = field(default_factory=dict)

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"

    def qcolor(self, token: str, alpha: float = 1.0) -> QColor:
        """The named token as a ``QColor`` with an optional alpha (0..1)."""
        color = QColor(getattr(self, token))
        color.setAlphaF(alpha)
        return color

    def category(self, category: Category, alpha: float = 1.0) -> QColor:
        color = QColor(self.categories[category])
        color.setAlphaF(alpha)
        return color


DARK: Final = Palette(
    name="dark",
    bg="#111216",
    sidebar="#0C0D10",
    surface="#17181D",
    surface_alt="#1E2026",
    raised="#25272E",
    input="#0F1014",
    hover="#24262D",
    pressed="#1A1B20",
    border="#262830",
    border_strong="#363944",
    text="#ECEDF1",
    text_muted="#A1A3AD",
    text_faint="#6E717C",
    accent="#7C6CF2",
    accent_hover="#8D7FF5",
    accent_pressed="#6C5BE6",
    accent_soft="#252240",
    accent_text="#A99FF8",
    on_accent="#FFFFFF",
    success="#45B987",
    success_soft="#15281F",
    warning="#E3AC4A",
    warning_soft="#2A2214",
    danger="#EC5F67",
    danger_soft="#2E1719",
    track="#23252C",
    categories={
        Category.VERTICAL: "#7193F4",
        Category.HORIZONTAL: "#52A9DE",
        Category.VIDEOS: "#8592A8",
        Category.GREENSCREEN: "#4DBE96",
        Category.FINALIZED: "#4FC4CF",
        Category.IMAGES: "#E2A951",
        Category.MUSIC: "#B08AF0",
        Category.SOUND_EFFECTS: "#D08FDC",
        Category.AUDIO: "#9C95CC",
        Category.PROJECTS: "#E57F93",
        Category.OTHER: "#868993",
    },
)

LIGHT: Final = Palette(
    name="light",
    bg="#F7F7F9",
    sidebar="#EFEFF3",
    surface="#FFFFFF",
    surface_alt="#F4F4F7",
    raised="#FFFFFF",
    input="#FFFFFF",
    hover="#EBEBF0",
    pressed="#E2E2E8",
    border="#E3E3E9",
    border_strong="#CFCFD8",
    text="#17181C",
    text_muted="#5C5F6A",
    text_faint="#8B8E99",
    accent="#5B4BDB",
    accent_hover="#4D3DCC",
    accent_pressed="#4334B8",
    accent_soft="#EEEBFD",
    accent_text="#4F3FD0",
    on_accent="#FFFFFF",
    success="#1D9A62",
    success_soft="#E6F5EE",
    warning="#B57414",
    warning_soft="#FBF3E4",
    danger="#D3343F",
    danger_soft="#FCEBEC",
    track="#EBEBF0",
    categories={
        Category.VERTICAL: "#3F64D6",
        Category.HORIZONTAL: "#2385C2",
        Category.VIDEOS: "#66738A",
        Category.GREENSCREEN: "#1E9168",
        Category.FINALIZED: "#16929E",
        Category.IMAGES: "#B87A17",
        Category.MUSIC: "#7F4FD0",
        Category.SOUND_EFFECTS: "#A24DB8",
        Category.AUDIO: "#6B63A6",
        Category.PROJECTS: "#C6475F",
        Category.OTHER: "#777A84",
    },
)

PALETTES: Final = {"dark": DARK, "light": LIGHT}


# ---------------------------------------------------------------------- fonts


def _first_available(families: tuple[str, ...]) -> list[str]:
    installed = set(QFontDatabase.families())
    available = [f for f in families if f in installed]
    return available or list(families)


def ui_font(pixel_size: int = FONT_BODY) -> QFont:
    font = QFont()
    font.setFamilies(_first_available(_UI_FAMILIES))
    font.setPixelSize(pixel_size)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def display_font(
    pixel_size: int = FONT_TITLE, weight: QFont.Weight = QFont.Weight.DemiBold
) -> QFont:
    font = QFont()
    font.setFamilies(_first_available(_DISPLAY_FAMILIES))
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def _css_families(families: tuple[str, ...]) -> str:
    return ", ".join(f'"{f}"' for f in _first_available(families))


# --------------------------------------------------------------------- manager


class ThemeManager(QObject):
    """Owns the active palette; re-styles the application when it changes."""

    changed = pyqtSignal()

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._mode = Appearance.SYSTEM
        self._palette: Palette = DARK
        self._applying = False
        hints = QGuiApplication.styleHints()
        if hints is not None:
            hints.colorSchemeChanged.connect(self._on_system_scheme_changed)

    @property
    def mode(self) -> Appearance:
        return self._mode

    @property
    def palette(self) -> Palette:
        return self._palette

    def set_mode(self, mode: Appearance | str) -> None:
        """Switch appearance; applied immediately (no restart)."""
        try:
            self._mode = Appearance(mode)
        except ValueError:
            self._mode = Appearance.SYSTEM
        self._sync_native_scheme()
        self.apply()

    def system_is_dark(self) -> bool:
        hints = QGuiApplication.styleHints()
        scheme = hints.colorScheme() if hints is not None else Qt.ColorScheme.Unknown
        return scheme != Qt.ColorScheme.Light  # unknown (e.g. headless) -> dark

    def resolve(self) -> Palette:
        if self._mode is Appearance.LIGHT:
            return LIGHT
        if self._mode is Appearance.DARK:
            return DARK
        return DARK if self.system_is_dark() else LIGHT

    def apply(self) -> None:
        self._palette = self.resolve()
        self._app.setPalette(qpalette(self._palette))
        self._app.setStyleSheet(build_stylesheet(self._palette))
        self.changed.emit()

    def _sync_native_scheme(self) -> None:
        """Tell Qt about a forced scheme so native title bars match (Qt 6.8+)."""
        hints = QGuiApplication.styleHints()
        if hints is None:
            return
        self._applying = True
        try:
            if self._mode is Appearance.SYSTEM:
                if hasattr(hints, "unsetColorScheme"):
                    hints.unsetColorScheme()
            elif hasattr(hints, "setColorScheme"):
                hints.setColorScheme(
                    Qt.ColorScheme.Dark if self._mode is Appearance.DARK else Qt.ColorScheme.Light
                )
        finally:
            self._applying = False

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._mode is Appearance.SYSTEM and not self._applying:
            self.apply()


_manager: ThemeManager | None = None


def manager() -> ThemeManager:
    """The application's theme manager (created on first use; needs a QApplication)."""
    global _manager
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        raise RuntimeError("theme.manager() needs a QApplication")
    if _manager is None or _manager.parent() is not app:
        _manager = ThemeManager(app)
        _manager.apply()
    return _manager


def current() -> Palette:
    """The active palette (dark before the application exists)."""
    if _manager is None or QApplication.instance() is None:
        return DARK
    return _manager.palette


def category_color(category: Category, alpha: float = 1.0) -> QColor:
    return current().category(category, alpha)


def apply_theme(app: QApplication, mode: Appearance | str | None = None) -> ThemeManager:
    """Install Fusion, the UI font and the palette for ``mode`` (default: keep current)."""
    app.setStyle("Fusion")  # consistent rendering of native controls on every OS
    app.setFont(ui_font())
    themes = manager()
    if mode is not None:
        themes.set_mode(mode)
    else:
        themes.apply()
    return themes


def repolish(widget: QWidget) -> None:
    """Re-evaluate style sheet rules after changing a dynamic property."""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def set_props(widget: QWidget, **props: object) -> None:
    """Set dynamic style properties (``role``, ``variant``, ``tone`` ...) and repolish."""
    for key, value in props.items():
        widget.setProperty(key, value)
    repolish(widget)


# --------------------------------------------------------------------- styling


def qpalette(p: Palette) -> QPalette:
    """A QPalette matching the tokens, for the parts Fusion paints itself."""
    pal = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup
    pairs = {
        role.Window: p.bg,
        role.WindowText: p.text,
        role.Base: p.input,
        role.AlternateBase: p.surface_alt,
        role.ToolTipBase: p.raised,
        role.ToolTipText: p.text,
        role.PlaceholderText: p.text_faint,
        role.Text: p.text,
        role.Button: p.surface_alt,
        role.ButtonText: p.text,
        role.BrightText: p.on_accent,
        role.Highlight: p.accent,
        role.HighlightedText: p.on_accent,
        role.Link: p.accent_text,
        role.Mid: p.border,
        role.Midlight: p.border,
        role.Dark: p.border_strong,
        role.Light: p.raised,
        role.Shadow: "#000000",
    }
    for r, color in pairs.items():
        pal.setColor(r, QColor(color))
    for r in (role.WindowText, role.Text, role.ButtonText):
        pal.setColor(group.Disabled, r, QColor(p.text_faint))
    return pal


def build_stylesheet(p: Palette) -> str:
    ui = _css_families(_UI_FAMILIES)
    display = _css_families(_DISPLAY_FAMILIES)
    mono = _css_families(_MONO_FAMILIES)
    return f"""
QWidget {{ color: {p.text}; font-family: {ui}; font-size: {FONT_BODY}px; }}
QMainWindow, QDialog {{ background-color: {p.bg}; }}
QWidget#shell, QStackedWidget#pages, QWidget#page {{ background-color: {p.bg}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

QToolTip {{
    background-color: {p.raised}; color: {p.text}; border: 1px solid {p.border_strong};
    padding: 6px 8px; border-radius: {RADIUS_SM}px; font-size: {FONT_CAPTION}px;
}}
QMenu {{
    background-color: {p.raised}; border: 1px solid {p.border_strong}; padding: 4px;
    border-radius: {RADIUS}px;
}}
QMenu::item {{ padding: 6px 20px 6px 10px; border-radius: {RADIUS_SM}px; }}
QMenu::item:selected {{ background-color: {p.hover}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 6px; }}
QMenu::icon {{ padding-left: 8px; }}

/* ---------- shell ---------- */
QFrame#sidebar {{ background-color: {p.sidebar}; border-right: 1px solid {p.border}; }}
QFrame#divider {{ background-color: {p.border}; border: none; }}

/* ---------- typography ---------- */
QLabel[role="title"] {{ font-family: {display}; font-size: {FONT_TITLE}px; font-weight: 600; }}
QLabel[role="h2"] {{ font-family: {display}; font-size: {FONT_H2}px; font-weight: 600; }}
QLabel[role="h3"] {{ font-size: {FONT_H3}px; font-weight: 600; }}
QLabel[role="strong"] {{ font-weight: 600; }}
QLabel[role="subtitle"], QLabel[role="muted"] {{ color: {p.text_muted}; }}
QLabel[role="caption"] {{ color: {p.text_faint}; font-size: {FONT_CAPTION}px; }}
QLabel[role="overline"] {{
    color: {p.text_faint}; font-size: 11px; font-weight: 600;
}}
QLabel[role="metric"] {{ font-family: {display}; font-size: 26px; font-weight: 600; }}
QLabel[role="step"] {{
    background-color: {p.surface_alt}; color: {p.text_muted}; border: 1px solid {p.border};
    border-radius: 11px; font-size: {FONT_CAPTION}px; font-weight: 600;
    min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px;
}}
QLabel[role="step"][done="true"] {{
    background-color: {p.accent_soft}; color: {p.accent_text}; border-color: {p.accent_soft};
}}
QLabel[role="tag"] {{
    background-color: {p.surface_alt}; color: {p.text_muted}; border: 1px solid {p.border};
    border-radius: 9px; padding: 1px 8px; font-size: 11px; font-weight: 600;
}}
QLabel[role="kbd"] {{
    background-color: {p.surface_alt}; color: {p.text_faint}; border: 1px solid {p.border};
    border-radius: 4px; padding: 0 5px; font-size: 11px;
}}
QLabel[tone="ok"] {{ color: {p.success}; }}
QLabel[tone="warn"] {{ color: {p.warning}; }}
QLabel[tone="error"] {{ color: {p.danger}; }}
QLabel[tone="neutral"] {{ color: {p.text_faint}; }}
QLabel[role="caption"][tone="ok"] {{ color: {p.success}; }}
QLabel[role="caption"][tone="warn"] {{ color: {p.warning}; }}
QLabel[role="caption"][tone="error"] {{ color: {p.danger}; }}

/* ---------- surfaces ---------- */
QFrame[card="true"] {{
    background-color: {p.surface}; border: 1px solid {p.border}; border-radius: {RADIUS_LG}px;
}}
QFrame[card="true"][dropzone="empty"] {{ border: 1px dashed {p.border_strong}; }}
QFrame[card="true"][dropzone="active"] {{
    border: 1px dashed {p.accent}; background-color: {p.accent_soft};
}}
QFrame[card="true"] QLabel, QFrame[card="true"] QWidget#plain {{ background: transparent; }}
QFrame#tile {{
    background-color: {p.surface}; border: 1px solid {p.border}; border-radius: {RADIUS_LG}px;
}}
QFrame#notice {{
    background-color: {p.warning_soft}; border: 1px solid {p.border}; border-radius: 10px;
}}
QFrame#notice QLabel {{ background: transparent; }}
QFrame#footerBar {{
    background-color: {p.surface}; border: 1px solid {p.border}; border-radius: {RADIUS_LG}px;
}}
QFrame#footerBar QLabel {{ background: transparent; }}
QFrame#badgeCircle {{ border-radius: 20px; }}
QFrame#badgeCircle[tone="ok"] {{ background-color: {p.success_soft}; }}
QFrame#badgeCircle[tone="warn"] {{ background-color: {p.warning_soft}; }}
QFrame#badgeCircle[tone="error"] {{ background-color: {p.danger_soft}; }}

/* ---------- inputs ---------- */
QLineEdit, QPlainTextEdit {{
    background-color: {p.input}; border: 1px solid {p.border}; border-radius: {RADIUS}px;
    color: {p.text}; selection-background-color: {p.accent}; selection-color: {p.on_accent};
}}
QLineEdit {{ padding: 0 10px; min-height: 34px; }}
QPlainTextEdit {{ padding: 6px; font-family: {mono}; font-size: {FONT_CAPTION}px; }}
QLineEdit:hover, QPlainTextEdit:hover {{ border-color: {p.border_strong}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {p.accent}; }}
QLineEdit:disabled {{ color: {p.text_faint}; }}
QLineEdit[validity="error"] {{ border-color: {p.danger}; }}
QLineEdit[validity="warn"] {{ border-color: {p.warning}; }}
QLineEdit#search {{ padding-left: 30px; }}

/* ---------- buttons ---------- */
QPushButton {{
    background-color: {p.surface_alt}; color: {p.text}; border: 1px solid {p.border};
    border-radius: {RADIUS}px; padding: 0 14px; min-height: 32px; font-weight: 500;
}}
QPushButton:hover {{ background-color: {p.hover}; border-color: {p.border_strong}; }}
QPushButton:pressed {{ background-color: {p.pressed}; }}
QPushButton:focus {{ border-color: {p.accent}; }}
QPushButton:disabled {{
    color: {p.text_faint}; background-color: transparent; border-color: {p.border};
}}
QPushButton[size="lg"] {{ min-height: 38px; padding: 0 18px; font-size: {FONT_H3}px; }}
QPushButton[variant="primary"] {{
    background-color: {p.accent}; color: {p.on_accent}; border: 1px solid {p.accent};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background-color: {p.accent_hover}; border-color: {p.accent_hover};
}}
QPushButton[variant="primary"]:pressed {{ background-color: {p.accent_pressed}; }}
QPushButton[variant="primary"]:focus {{ border-color: {p.accent_text}; }}
QPushButton[variant="primary"]:disabled {{
    background-color: {p.surface_alt}; color: {p.text_faint}; border-color: {p.border};
}}
QPushButton[variant="ghost"] {{
    background-color: transparent; border-color: transparent; color: {p.text_muted};
}}
QPushButton[variant="ghost"]:hover {{ background-color: {p.hover}; color: {p.text}; }}
QPushButton[variant="ghost"]:focus {{ border-color: {p.border_strong}; }}
QPushButton[variant="ghost"]:disabled {{ color: {p.text_faint}; }}
QPushButton[variant="danger"] {{
    background-color: transparent; color: {p.danger}; border-color: {p.border};
}}
QPushButton[variant="danger"]:hover {{
    background-color: {p.danger_soft}; border-color: {p.danger};
}}
QPushButton[variant="link"] {{
    background: transparent; border: none; color: {p.accent_text}; padding: 0;
    min-height: 20px; text-align: left; font-weight: 500;
}}
QPushButton[variant="link"]:hover {{ text-decoration: underline; }}
QPushButton[variant="link"]:disabled {{ color: {p.text_faint}; }}
QPushButton[chip="true"] {{
    background-color: transparent; border: 1px solid {p.border}; border-radius: 14px;
    min-height: 26px; padding: 0 11px; color: {p.text_muted}; font-size: {FONT_CAPTION}px;
}}
QPushButton[chip="true"]:hover {{ background-color: {p.hover}; color: {p.text}; }}
QPushButton[chip="true"]:checked {{
    background-color: {p.accent_soft}; border-color: {p.accent}; color: {p.text};
}}
QPushButton[category="true"] {{
    text-align: left; padding: 0 10px; min-height: 34px; background-color: {p.surface};
}}
QPushButton[category="true"]:hover {{ background-color: {p.hover}; }}
QPushButton[category="true"]:disabled {{ background-color: transparent; }}

/* ---------- progress ---------- */
QProgressBar {{
    background-color: {p.track}; border: none; border-radius: 3px;
    min-height: 6px; max-height: 6px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background-color: {p.accent}; border-radius: 3px; }}

/* ---------- tables & lists ---------- */
QTableView {{
    background-color: {p.surface}; border: none; gridline-color: transparent;
    selection-background-color: {p.accent_soft}; selection-color: {p.text}; outline: 0;
}}
QTableView::item {{ border-bottom: 1px solid {p.border}; padding: 0 4px; }}
QTableView::item:selected {{ background-color: {p.accent_soft}; color: {p.text}; }}
QHeaderView {{ background-color: {p.surface}; border: none; }}
QHeaderView::section {{
    background-color: {p.surface}; color: {p.text_faint}; border: none;
    border-bottom: 1px solid {p.border}; padding: 0 8px; min-height: 34px;
    font-size: {FONT_CAPTION}px; font-weight: 600;
}}
QHeaderView::section:first {{ padding-left: 16px; }}
QTableCornerButton::section {{ background-color: {p.surface}; border: none; }}
QListWidget {{ background: transparent; border: none; outline: 0; }}
QListWidget::item {{
    padding: 7px 10px; border-radius: {RADIUS}px; margin: 1px 0; color: {p.text_muted};
}}
QListWidget::item:hover {{ background-color: {p.hover}; color: {p.text}; }}
QListWidget::item:selected {{ background-color: {p.accent_soft}; color: {p.text}; }}

/* ---------- scrollbars ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {p.border_strong}; border-radius: 3px; min-height: 32px; margin: 0 2px;
}}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {p.border_strong}; border-radius: 3px; min-width: 32px; margin: 2px 0;
}}
QScrollBar::handle:hover {{ background: {p.text_faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMessageBox, QProgressDialog {{ background-color: {p.surface}; }}
QMessageBox QLabel, QProgressDialog QLabel {{ background: transparent; }}
"""
