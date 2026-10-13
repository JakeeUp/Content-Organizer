"""Colours, category palette and the application style sheet - the single source of look.

The dark navy dashboard with rounded cards is the project's visual identity. Every
colour used by widgets lives here; widgets never hardcode hex values.
"""

from __future__ import annotations

from typing import Final

from PyQt6.QtGui import QColor, QFont, QLinearGradient
from PyQt6.QtWidgets import QApplication

from content_organizer.categories import Category

APP_DISPLAY_NAME: Final = "Content Organizer"
ORG_NAME: Final = "content-organizer"

BG: Final = "#0F172A"  # slate 900 - window
BG_DEEP: Final = "#0B1222"  # inputs / tracks
CARD: Final = "#1E293B"  # slate 800 - cards
CARD_RAISED: Final = "#273449"
BORDER: Final = "#334155"  # slate 700
TEXT: Final = "#F1F5F9"  # slate 100
TEXT_MUTED: Final = "#94A3B8"  # slate 400
TEXT_FAINT: Final = "#64748B"  # slate 500
ACCENT: Final = "#8B5CF6"  # violet 500 - primary action
ACCENT_HOVER: Final = "#A78BFA"
BLUE: Final = "#3B82F6"
AMBER: Final = "#F59E0B"
SUCCESS: Final = "#10B981"
DANGER: Final = "#F43F5E"
WARNING_BG: Final = "#3B2A0B"

GRADIENT_STOPS: Final = ("#FFD60A", "#32D74B", "#0A84FF")  # yellow -> green -> blue

CATEGORY_COLORS: Final[dict[Category, str]] = {
    Category.VERTICAL: "#0A84FF",
    Category.HORIZONTAL: "#32D74B",
    Category.VIDEOS: "#AC8E68",
    Category.GREENSCREEN: "#2DD4BF",
    Category.FINALIZED: "#FFD60A",
    Category.IMAGES: "#FF9500",
    Category.MUSIC: "#BF5AF2",
    Category.SOUND_EFFECTS: "#64D2FF",
    Category.AUDIO: "#7B68EE",
    Category.PROJECTS: "#FF2D55",
    Category.OTHER: "#8E8E93",
}

FONT_FAMILIES: Final = ["Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Noto Sans", "Arial"]


def category_color(category: Category) -> QColor:
    return QColor(CATEGORY_COLORS[category])


def horizontal_gradient(x0: float, x1: float) -> QLinearGradient:
    """The signature yellow -> green -> blue gradient spanning ``x0..x1``."""
    gradient = QLinearGradient(x0, 0, x1, 0)
    for stop, color in zip((0.0, 0.5, 1.0), GRADIENT_STOPS, strict=True):
        gradient.setColorAt(stop, QColor(color))
    return gradient


def gradient_color(t: float) -> QColor:
    """Colour at position ``t`` (0..1) along the signature gradient."""
    t = min(1.0, max(0.0, t))
    a, b, local = (0, 1, t * 2) if t < 0.5 else (1, 2, (t - 0.5) * 2)
    ca, cb = QColor(GRADIENT_STOPS[a]), QColor(GRADIENT_STOPS[b])
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * local),
        round(ca.green() + (cb.green() - ca.green()) * local),
        round(ca.blue() + (cb.blue() - ca.blue()) * local),
    )


def app_font(point_size: float = 10.0) -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSizeF(point_size)
    return font


def apply_theme(app: QApplication) -> None:
    """Install the font and style sheet on the application."""
    app.setStyle("Fusion")  # consistent rendering of native controls on every OS
    app.setFont(app_font())
    app.setStyleSheet(STYLESHEET)


STYLESHEET: Final = f"""
QMainWindow, QDialog {{ background-color: {BG}; }}
QWidget {{ color: {TEXT}; }}
QWidget#central, QWidget#content {{ background-color: {BG}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QToolTip {{
    background-color: {CARD_RAISED}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 6px 8px; border-radius: 6px;
}}

QMenuBar {{ background-color: {BG}; color: {TEXT_MUTED}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background-color: {CARD}; color: {TEXT}; }}
QMenu {{ background-color: {CARD}; border: 1px solid {BORDER}; padding: 6px; border-radius: 8px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background-color: {CARD_RAISED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QFrame#card {{ background-color: {CARD}; border-radius: 18px; }}
QLabel#appTitle {{ font-size: 22pt; font-weight: 700; }}
QLabel#appSubtitle {{ color: {TEXT_MUTED}; font-size: 10pt; }}
QLabel#cardTitle {{ font-size: 12pt; font-weight: 700; }}
QLabel#cardSubtitle, QLabel#hint {{ color: {TEXT_MUTED}; font-size: 9pt; }}
QLabel#fieldLabel {{ font-weight: 600; }}
QLabel#statusTitle {{ font-size: 15pt; font-weight: 700; }}
QLabel#currentFile {{ color: {TEXT_MUTED}; }}
QLabel#statValue {{ font-size: 11pt; font-weight: 700; }}
QLabel#statusOk {{ color: {SUCCESS}; font-size: 9pt; }}
QLabel#statusWarn {{ color: {AMBER}; font-size: 9pt; }}
QLabel#statusError {{ color: {DANGER}; font-size: 9pt; }}
QLabel#statusNeutral {{ color: {TEXT_FAINT}; font-size: 9pt; }}
QLabel#emptyTitle {{ font-size: 15pt; font-weight: 700; }}

QLineEdit, QPlainTextEdit, QComboBox {{
    background-color: {BG_DEEP}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 8px 10px; color: {TEXT}; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit[validity="error"] {{ border: 1px solid {DANGER}; }}
QLineEdit[validity="warn"] {{ border: 1px solid {AMBER}; }}
QLineEdit[dropTarget="true"] {{ border: 2px dashed {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background-color: {CARD}; border: 1px solid {BORDER}; }}

QPushButton {{
    background-color: {CARD_RAISED}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 10px; padding: 8px 14px; font-weight: 600;
}}
QPushButton:hover {{ background-color: #31405A; border-color: #475569; }}
QPushButton:pressed {{ background-color: #1A2436; }}
QPushButton:focus {{ border: 1px solid {ACCENT_HOVER}; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; background-color: #1A2333; border-color: #243044; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_HOVER});
    border: none; color: white; padding: 10px 22px; font-size: 11pt;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9D74F8, stop:1 #B9A2FC);
}}
QPushButton#primary:focus {{ border: 2px solid white; }}
QPushButton#primary:disabled {{ background: #3B3561; color: #8D86B0; }}
QPushButton#accentAmber {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {AMBER}, stop:1 #FBBF5A);
    border: none; color: #1F1300; padding: 10px 20px; font-size: 11pt;
}}
QPushButton#accentAmber:hover {{ background: #FBBF5A; }}
QPushButton#accentAmber:focus {{ border: 2px solid white; }}
QPushButton#accentAmber:disabled {{ background: #4A3A1C; color: #9C8A66; }}
QPushButton#danger {{ color: #FDA4AF; border-color: #7F1D3A; background-color: #2A1624; }}
QPushButton#danger:hover {{ background-color: #3A1B2E; }}
QPushButton#link {{
    background: transparent; border: none; color: {ACCENT_HOVER}; padding: 2px 4px;
    text-align: left;
}}
QPushButton#link:hover {{ color: white; text-decoration: underline; }}
QPushButton#categoryButton {{ text-align: left; padding: 9px 12px; }}

QProgressBar {{
    border: none; border-radius: 13px; background-color: {BG_DEEP}; min-height: 26px;
    max-height: 26px; text-align: center; color: white; font-weight: 700;
}}
QProgressBar::chunk {{
    border-radius: 13px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {GRADIENT_STOPS[0]},
        stop:0.5 {GRADIENT_STOPS[1]}, stop:1 {GRADIENT_STOPS[2]});
}}

QFrame#banner {{
    background-color: {WARNING_BG}; border: 1px solid #6B4E16; border-radius: 12px;
}}
QLabel#bannerText {{ color: #FDE68A; }}

QTableView {{
    background-color: {BG_DEEP}; alternate-background-color: #111B2E; border: 1px solid {BORDER};
    border-radius: 10px; gridline-color: transparent; selection-background-color: #3B3561;
}}
QHeaderView::section {{
    background-color: {CARD}; color: {TEXT_MUTED}; border: none; padding: 6px 8px;
    font-weight: 600;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QFrame#chip {{ background-color: {BG_DEEP}; border-radius: 10px; }}
QFrame#previewPane {{ background-color: {BG_DEEP}; border-radius: 14px; }}
"""
