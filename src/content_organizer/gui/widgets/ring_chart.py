"""Donut chart: one coloured arc per segment, total in the centre."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from content_organizer.gui import theme

_GAP_DEGREES = 2.0  # visual gap between neighbouring arcs
_MAX_SIDE = 230


@dataclass(frozen=True)
class Segment:
    label: str
    count: int
    color: QColor


class RingChart(QWidget):
    """Replaces all segments on every :meth:`set_segments` call (no stale arcs)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._segments: list[Segment] = []
        self._caption = "files"
        self.setMinimumSize(150, 150)
        self.setMaximumHeight(_MAX_SIDE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        return QSize(190, 190)

    @property
    def segments(self) -> list[Segment]:
        return list(self._segments)

    @property
    def total(self) -> int:
        return sum(s.count for s in self._segments)

    def set_segments(self, segments: list[Segment], caption: str = "files") -> None:
        self._segments = [s for s in segments if s.count > 0]
        self._caption = caption
        self.setToolTip(
            "\n".join(f"{s.label}: {s.count}" for s in self._segments) or "No files yet"
        )
        self.update()

    def clear(self) -> None:
        self.set_segments([])

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height(), _MAX_SIDE)
        thickness = max(10.0, side * 0.085)
        radius = side / 2 - thickness / 2 - 4
        cx, cy = self.width() / 2, self.height() / 2
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        pen = QPen(QColor(theme.BG_DEEP), thickness)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)
        self._draw_arcs(painter, rect, thickness)
        self._draw_centre(painter, radius)
        painter.end()

    def _draw_arcs(self, painter: QPainter, rect: QRectF, thickness: float) -> None:
        total = self.total
        if total <= 0:
            return
        gap = _GAP_DEGREES if len(self._segments) > 1 else 0.0
        start = 90.0  # 12 o'clock, clockwise
        for segment in self._segments:
            span = segment.count / total * 360.0
            visible = max(0.6, span - gap)
            pen = QPen(segment.color, thickness)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawArc(rect, round((start - gap / 2) * 16), round(-visible * 16))
            start -= span

    def _draw_centre(self, painter: QPainter, radius: float) -> None:
        number_font = QFont(self.font())
        number_font.setPointSizeF(max(14.0, radius * 0.32))
        number_font.setBold(True)
        painter.setFont(number_font)
        painter.setPen(QColor(theme.TEXT))
        box = QRectF(0, 0, self.width(), self.height())
        number_rect = box.adjusted(0, -radius * 0.16, 0, -radius * 0.16)
        painter.drawText(number_rect, Qt.AlignmentFlag.AlignCenter, f"{self.total:,}")

        caption_font = QFont(self.font())
        caption_font.setPointSizeF(max(8.0, min(10.0, radius * 0.09)))
        painter.setFont(caption_font)
        painter.setPen(QColor(theme.TEXT_MUTED))
        caption_rect = box.adjusted(0, radius * 0.36, 0, radius * 0.36)
        painter.drawText(caption_rect, Qt.AlignmentFlag.AlignCenter, self._caption)
