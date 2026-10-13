"""Chronological monthly distribution chart (smooth area line, clickable points).

Fixes from the legacy ``WaveChart``: points are ``(year, month)`` buckets in time order
(no alphabetical months, no merged years), the curve never overshoots its data,
the nearest point wins hover/click, and it is keyboard accessible (Left/Right + Enter).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget

from content_organizer.gui import theme
from content_organizer.rules import MONTH_NAMES

YearMonth = tuple[int, int]

_MARGIN_LEFT = 40.0
_MARGIN_RIGHT = 20.0
_MARGIN_TOP = 28.0
_MARGIN_BOTTOM = 46.0
_MIN_LABEL_SPACING = 46.0


def month_label(key: YearMonth) -> str:
    year, month = key
    return f"{MONTH_NAMES[month - 1]} {year}"


class MonthlyChart(QWidget):
    """Plots ``[((year, month), count), ...]``; emits :attr:`monthClicked` on a point."""

    monthClicked = pyqtSignal(int, int)  # year, month

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._series: list[tuple[YearMonth, int]] = []
        self._hover = -1
        self._empty_text = "No data yet"
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Monthly distribution chart")

    def sizeHint(self) -> QSize:
        return QSize(420, 240)

    # ------------------------------------------------------------------ data

    @property
    def series(self) -> list[tuple[YearMonth, int]]:
        return list(self._series)

    def set_series(self, series: Sequence[tuple[YearMonth, int]], empty_text: str = "") -> None:
        """Set the data; it is sorted chronologically regardless of input order."""
        self._series = sorted(series)
        self._hover = -1
        if empty_text:
            self._empty_text = empty_text
        self.update()

    @property
    def hover_index(self) -> int:
        return self._hover

    # -------------------------------------------------------------- geometry

    def _plot_rect(self) -> QRectF:
        return QRectF(
            _MARGIN_LEFT,
            _MARGIN_TOP,
            max(1.0, self.width() - _MARGIN_LEFT - _MARGIN_RIGHT),
            max(1.0, self.height() - _MARGIN_TOP - _MARGIN_BOTTOM),
        )

    def point_positions(self) -> list[QPointF]:
        """Widget coordinates of every data point (public for tests)."""
        if not self._series:
            return []
        plot = self._plot_rect()
        peak = max(count for _, count in self._series) or 1
        n = len(self._series)
        points = []
        for i, (_, count) in enumerate(self._series):
            x = plot.center().x() if n == 1 else plot.left() + plot.width() * i / (n - 1)
            y = plot.bottom() - plot.height() * count / peak
            points.append(QPointF(x, y))
        return points

    def index_at(self, x: float) -> int:
        """Index of the point nearest to ``x`` within half the point spacing, else -1."""
        points = self.point_positions()
        if not points:
            return -1
        spacing = self._plot_rect().width() / max(1, len(points) - 1)
        reach = max(14.0, spacing / 2)
        best = min(range(len(points)), key=lambda i: abs(points[i].x() - x))
        return best if abs(points[best].x() - x) <= reach else -1

    # ---------------------------------------------------------------- events

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        self._set_hover(self.index_at(event.position().x()))
        if self._hover >= 0:
            key, count = self._series[self._hover]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{month_label(key)}: {count:,} file{'s' if count != 1 else ''}\n"
                "Click to open this month's folder",
                self,
            )
        else:
            QToolTip.hideText()

    def leaveEvent(self, event: object) -> None:
        self._set_hover(-1)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is None or event.button() != Qt.MouseButton.LeftButton:
            return
        index = self.index_at(event.position().x())
        if index >= 0:
            self._set_hover(index)
            self._activate(index)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None or not self._series:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Left):
            step = 1 if key == Qt.Key.Key_Right else -1
            start = self._hover if self._hover >= 0 else (-1 if step > 0 else len(self._series))
            self._set_hover(min(len(self._series) - 1, max(0, start + step)))
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self._hover >= 0:
            self._activate(self._hover)
        else:
            super().keyPressEvent(event)

    def _set_hover(self, index: int) -> None:
        if index != self._hover:
            self._hover = index
            if index >= 0:
                key, count = self._series[index]
                self.setAccessibleDescription(f"{month_label(key)}: {count} files")
            self.update()

    def _activate(self, index: int) -> None:
        (year, month), _ = self._series[index]
        self.monthClicked.emit(year, month)

    # -------------------------------------------------------------- painting

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._series:
            self._paint_empty(painter)
        else:
            points = self.point_positions()
            self._paint_grid(painter)
            self._paint_area(painter, points)
            self._paint_points(painter, points)
            self._paint_labels(painter, points)
        if self.hasFocus():
            painter.setPen(QPen(QColor(theme.BORDER), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        painter.end()

    def _paint_empty(self, painter: QPainter) -> None:
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() * 1.15)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT_MUTED))
        painter.drawText(
            QRectF(self.rect()).adjusted(20, 0, -20, 0),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self._empty_text,
        )

    def _paint_grid(self, painter: QPainter) -> None:
        plot = self._plot_rect()
        peak = max(count for _, count in self._series) or 1
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() * 0.82)
        painter.setFont(font)
        for fraction in (0.0, 0.5, 1.0):
            y = plot.bottom() - plot.height() * fraction
            painter.setPen(QPen(QColor(theme.BORDER), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(theme.TEXT_FAINT))
            painter.drawText(
                QRectF(0, y - 9, _MARGIN_LEFT - 8, 18),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                f"{round(peak * fraction):,}",
            )

    def _curve(self, points: list[QPointF]) -> QPainterPath:
        """Smooth path whose control points share the endpoints' y: never overshoots."""
        path = QPainterPath(points[0])
        for a, b in itertools.pairwise(points):
            mid = (a.x() + b.x()) / 2
            path.cubicTo(QPointF(mid, a.y()), QPointF(mid, b.y()), b)
        return path

    def _paint_area(self, painter: QPainter, points: list[QPointF]) -> None:
        plot = self._plot_rect()
        gradient = theme.horizontal_gradient(plot.left(), plot.right())
        if len(points) == 1:
            return
        line = self._curve(points)
        area = QPainterPath(line)
        area.lineTo(points[-1].x(), plot.bottom())
        area.lineTo(points[0].x(), plot.bottom())
        area.closeSubpath()
        painter.save()
        painter.setOpacity(0.22)
        painter.fillPath(area, gradient)
        painter.restore()
        pen = QPen()
        pen.setBrush(gradient)
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(line)

    def _paint_points(self, painter: QPainter, points: list[QPointF]) -> None:
        plot = self._plot_rect()
        n = len(points)
        dense = n > 40
        for i, point in enumerate(points):
            color = theme.gradient_color((point.x() - plot.left()) / max(1.0, plot.width()))
            if i == self._hover:
                painter.setPen(QPen(QColor(theme.TEXT_FAINT), 1, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(point.x(), point.y()), QPointF(point.x(), plot.bottom()))
                painter.setPen(QPen(QColor("white"), 2))
                painter.setBrush(color)
                painter.drawEllipse(point, 7.5, 7.5)
                self._paint_value(painter, point, self._series[i][1])
            elif not dense:
                painter.setPen(QPen(QColor(theme.CARD), 2))
                painter.setBrush(color)
                painter.drawEllipse(point, 5.0, 5.0)

    def _paint_value(self, painter: QPainter, point: QPointF, value: int) -> None:
        font = QFont(self.font())
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        rect = QRectF(point.x() - 40, point.y() - 28, 80, 18)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{value:,}")

    def _paint_labels(self, painter: QPainter, points: list[QPointF]) -> None:
        plot = self._plot_rect()
        n = len(points)
        spacing = plot.width() / max(1, n - 1)
        step = max(1, math.ceil(_MIN_LABEL_SPACING / spacing)) if n > 1 else 1
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() * 0.85)
        painter.setFont(font)
        last_year: int | None = None
        for i in range(0, n, step):
            (year, month), _ = self._series[i]
            x = points[i].x()
            painter.setPen(QColor(theme.TEXT_MUTED if i != self._hover else theme.TEXT))
            painter.drawText(
                QRectF(x - 24, plot.bottom() + 8, 48, 16),
                Qt.AlignmentFlag.AlignCenter,
                MONTH_NAMES[month - 1][:3],
            )
            if year != last_year:
                painter.setPen(QColor(theme.TEXT_FAINT))
                painter.drawText(
                    QRectF(x - 24, plot.bottom() + 24, 48, 16),
                    Qt.AlignmentFlag.AlignCenter,
                    str(year),
                )
                last_year = year
