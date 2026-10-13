"""Small line icons drawn from inline SVG, so buttons never depend on emoji fonts."""

from __future__ import annotations

from functools import cache

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from content_organizer.gui import theme

# 24x24 stroke paths (stroke-width 2, round caps). Drawn for this project.
_PATHS: dict[str, str] = {
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5'
    'a2 2 0 0 1-2-2z"/>',
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/>'
    '<circle cx="12" cy="12" r="3"/>',
    "review": '<path d="M9 11l3 3 8-8"/>'
    '<path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "open": '<path d="M14 4h6v6"/><path d="M10 14L20 4"/>'
    '<path d="M19 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4"/>',
    "cancel": '<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.6-4.5L4 8"/><path d="M4 4v4h4"/>'
    '<path d="M4 13a8 8 0 0 0 14.6 4.5L20 16"/><path d="M20 20v-4h-4"/>',
    "download": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
    "warning": '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
    "skip": '<path d="M5 5l8 7-8 7z"/><path d="M17 5v14"/>',
    "back": '<path d="M19 5l-8 7 8 7z"/><path d="M7 5v14"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 3v5h5"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "log": '<path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
}


def _svg(name: str, color: str) -> bytes:
    body = _PATHS[name]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    ).encode()


def _render(svg: bytes, sizes: tuple[int, ...]) -> QIcon:
    renderer = QSvgRenderer(QByteArray(svg))
    result = QIcon()
    for size in sizes:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        result.addPixmap(pixmap)
    return result


@cache
def icon(name: str, color: str = theme.TEXT) -> QIcon:
    """Return a crisp multi-resolution icon in ``color``."""
    return _render(_svg(name, color), (16, 20, 24, 32, 48, 64))


_APP_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#8B5CF6"/><stop offset="1" stop-color="#0A84FF"/>'
    "</linearGradient></defs>"
    '<rect x="2" y="2" width="60" height="60" rx="14" fill="url(#g)"/>'
    '<path d="M14 22a4 4 0 0 1 4-4h9l4 4h15a4 4 0 0 1 4 4v16a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4z" '
    'fill="none" stroke="white" stroke-width="3.5" stroke-linejoin="round"/>'
    '<path d="M22 36h8M22 30h14" stroke="#FFD60A" stroke-width="3.5" stroke-linecap="round"/>'
    "</svg>"
)


@cache
def app_icon() -> QIcon:
    """The application/window icon."""
    return _render(_APP_ICON.encode(), (16, 24, 32, 48, 64, 128, 256))


def names() -> list[str]:
    return sorted(_PATHS)
