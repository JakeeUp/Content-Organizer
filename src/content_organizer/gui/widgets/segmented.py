"""A segmented control (e.g. System / Light / Dark)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from content_organizer.gui import icons, theme

_SEGMENT_W = 92
_HEIGHT = 34
_PAD = 3


class SegmentedControl(QWidget):
    """Options are ``(value, label, icon)``; emits :attr:`changed` with the value."""

    changed = pyqtSignal(str)

    def __init__(
        self, options: Sequence[tuple[str, str, str]], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._options = list(options)
        self._index = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Segmented control")
        theme.manager().changed.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(_SEGMENT_W * len(self._options) + 2 * _PAD, _HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def value(self) -> str:
        return self._options[self._index][0]

    def values(self) -> list[str]:
        return [value for value, _, _ in self._options]

    def set_value(self, value: str, *, emit: bool = False) -> None:
        if value in self.values():
            self._select(self.values().index(value), emit=emit)

    def _select(self, index: int, *, emit: bool = True) -> None:
        index = max(0, min(len(self._options) - 1, index))
        changed = index != self._index
        self._index = index
        self.setAccessibleDescription(self._options[index][1])
        self.update()
        if changed and emit:
            self.changed.emit(self.value())

    def _segment_rect(self, index: int) -> QRectF:
        return QRectF(_PAD + index * _SEGMENT_W, _PAD, _SEGMENT_W, _HEIGHT - 2 * _PAD)

    def _index_at(self, x: float) -> int:
        index = int((x - _PAD) // _SEGMENT_W)
        return index if 0 <= index < len(self._options) else -1

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is not None:
            self._hover = self._index_at(event.position().x())
            self.update()

    def leaveEvent(self, event: object) -> None:
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at(event.position().x())
            if index >= 0:
                self._select(index)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is not None and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._select(self._index + (1 if event.key() == Qt.Key.Key_Right else -1))
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRectF(0.5, 0.5, self.sizeHint().width() - 1, _HEIGHT - 1)
        painter.setPen(QPen(QColor(p.accent if self.hasFocus() else p.border), 1))
        painter.setBrush(QColor(p.surface_alt))
        painter.drawRoundedRect(outer, theme.RADIUS + 1, theme.RADIUS + 1)
        font = QFont(self.font())
        font.setPixelSize(theme.FONT_BODY)
        for i, (_value, text, icon) in enumerate(self._options):
            rect = self._segment_rect(i)
            selected = i == self._index
            if selected:
                painter.setPen(QPen(QColor(p.border_strong), 1))
                painter.setBrush(QColor(p.raised if not p.is_dark else p.hover))
                painter.drawRoundedRect(rect, theme.RADIUS - 1, theme.RADIUS - 1)
            elif i == self._hover:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(p.qcolor("hover", 0.6))
                painter.drawRoundedRect(rect, theme.RADIUS - 1, theme.RADIUS - 1)
            font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Normal)
            painter.setFont(font)
            color = p.text if selected else p.text_muted
            text_w = painter.fontMetrics().horizontalAdvance(text)
            left = rect.center().x() - (text_w + 22) / 2
            icons.icon(icon, color).paint(
                painter, QRectF(left, rect.center().y() - 8, 16, 16).toRect()
            )
            painter.setPen(QColor(color))
            painter.drawText(
                QRectF(left + 22, rect.top(), text_w + 2, rect.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                text,
            )
        painter.end()
