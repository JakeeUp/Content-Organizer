"""Line icons drawn from inline SVG, recoloured from the active theme."""

from __future__ import annotations

from functools import cache

from PyQt6.QtCore import QByteArray, QObject, QRectF, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QAbstractButton, QLabel, QWidget

from content_organizer.gui import theme

# 24x24 stroke paths (round caps and joins).
_PATHS: dict[str, str] = {
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5'
    'a2 2 0 0 1-2-2z"/>',
    "folder-plus": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5'
    'a2 2 0 0 1-2-2z"/><path d="M12 10.5v5M9.5 13h5"/>',
    "sort": '<path d="M4 6h10M4 12h7M4 18h4"/><path d="M17 8v11"/><path d="M14 16l3 3 3-3"/>',
    "library": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/>'
    '<rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/>'
    '<rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/>'
    '<rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
    "inbox": '<path d="M3 13l2.6-7.2A2 2 0 0 1 7.5 4.5h9a2 2 0 0 1 1.9 1.3L21 13"/>'
    '<path d="M3 13v5a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5h-5l-1.5 2.5h-5L8 13z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/>'
    '<path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 '
    "1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1"
    "a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1"
    "a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 "
    "1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3"
    "l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 "
    '0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/>'
    '<circle cx="12" cy="12" r="3"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "arrow-left": '<path d="M19 12H5"/><path d="M11 6l-6 6 6 6"/>',
    "review": '<path d="M9 11l3 3 8-8"/>'
    '<path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "open": '<path d="M14 4h6v6"/><path d="M10 14L20 4"/>'
    '<path d="M19 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4"/>',
    "cancel": '<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.6-4.5L4 8"/><path d="M4 4v4h4"/>'
    '<path d="M4 13a8 8 0 0 0 14.6 4.5L20 16"/><path d="M20 20v-4h-4"/>',
    "download": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
    "upload": '<path d="M12 16V5"/><path d="M7 10l5-5 5 5"/><path d="M5 20h14"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
    "warning": '<path d="M12 3.5l9 16h-18z"/><path d="M12 10v4"/><path d="M12 17h.01"/>',
    "skip": '<path d="M5 5l8 7-8 7z"/><path d="M17 5v14"/>',
    "back": '<path d="M19 5l-8 7 8 7z"/><path d="M7 5v14"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 3v5h5"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.8 2.8L16.5 9.5"/>',
    "log": '<path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4'
    'M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/>'
    '<path d="M21 16l-5-5-9 9"/>',
    "music": '<path d="M9 18V5l11-2v13"/><circle cx="6.5" cy="18" r="2.5"/>'
    '<circle cx="17.5" cy="16" r="2.5"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "github": '<path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 '
    "5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0"
    "C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6"
    '-.6.6-.6 1.2-.5 2V21"/>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2"/>'
    '<path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
}


def _svg(name: str, color: str, stroke: float = 1.8) -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{_PATHS[name]}</svg>'
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
def icon(name: str, color: str | None = None) -> QIcon:
    """A crisp multi-resolution icon; ``color`` defaults to the theme's text colour."""
    return _render(_svg(name, color or theme.current().text), (16, 20, 24, 32, 40, 48, 64, 96))


def pixmap(name: str, color: str, size: int, ratio: float = 1.0) -> QPixmap:
    return icon(name, color).pixmap(QSize(size, size), ratio)


class _IconBinder(QObject):
    """Keeps a widget's icon in the theme colour ``token``; dies with the widget."""

    def __init__(self, target: QWidget, name: str, token: str, size: int) -> None:
        super().__init__(target)
        self._target = target
        self.name, self.token, self.size = name, token, size
        theme.manager().changed.connect(self.refresh)

    def refresh(self) -> None:
        color = getattr(theme.current(), self.token)
        target = self._target
        if isinstance(target, QAbstractButton):
            target.setIcon(icon(self.name, color))
            target.setIconSize(QSize(self.size, self.size))
        elif isinstance(target, QLabel):
            target.setPixmap(pixmap(self.name, color, self.size, target.devicePixelRatioF()))


def themed(widget: QWidget, name: str, token: str = "text_muted", size: int = 16) -> None:
    """Give a button or label icon ``name`` that follows theme changes."""
    binder = widget.findChild(_IconBinder, options=Qt.FindChildOption.FindDirectChildrenOnly)
    if binder is None:
        binder = _IconBinder(widget, name, token, size)
    else:
        binder.name, binder.token, binder.size = name, token, size
    binder.refresh()


def _app_icon_svg(accent: str = "#7C6CF2", accent2: str = "#5B8CF0") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="{accent2}"/>'
        "</linearGradient></defs>"
        '<rect x="2" y="2" width="60" height="60" rx="15" fill="url(#g)"/>'
        '<path d="M15 23a4 4 0 0 1 4-4h8l4 4h14a4 4 0 0 1 4 4v14a4 4 0 0 1-4 4H19a4 4 0 0 1-4-4z" '
        'fill="none" stroke="white" stroke-width="3.6" stroke-linejoin="round"/>'
        '<path d="M23 36h9M23 30h16" stroke="white" stroke-opacity="0.75" stroke-width="3.6" '
        'stroke-linecap="round"/></svg>'
    )


@cache
def app_icon() -> QIcon:
    """The application/window icon (the one place a gentle gradient is used)."""
    return _render(_app_icon_svg().encode(), (16, 20, 24, 28, 32, 48, 64, 128, 256))


def names() -> list[str]:
    return sorted(_PATHS)
