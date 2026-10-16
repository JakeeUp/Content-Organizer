"""Monthly distribution as a single-accent bar chart.

Months are ``(year, month)`` buckets in time order; gaps inside the range are shown as
empty months so the time axis stays honest. Years are separated by a hairline and a
label. Hover highlights a bar and shows a tooltip; click, or Left/Right then Enter,
emits :attr:`MonthlyChart.monthClicked`.
"""

from __future__ import annotations

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

_LEFT = 36.0
_RIGHT = 8.0
_TOP = 26.0
_BOTTOM = 44.0
_MAX_BAR = 34.0
_MAX_FILLED_MONTHS = 240


def month_label(key: YearMonth) -> str:
    year, month = key
    return f"{MONTH_NAMES[month - 1]} {year}"


def _month_index(key: YearMonth) -> int:
    return key[0] * 12 + key[1] - 1


def fill_gaps(series: Sequence[tuple[YearMonth, int]]) -> list[tuple[YearMonth, int]]:
    """Sort chronologically and insert zero months between the first and last month."""
    data = sorted(series)
    if len(data) < 2:
        return data
    first, last = _month_index(data[0][0]), _month_index(data[-1][0])
    if last - first >= _MAX_FILLED_MONTHS:
        return data
    counts = dict(data)
    return [
        ((i // 12, i % 12 + 1), counts.get((i // 12, i % 12 + 1), 0))
        for i in range(first, last + 1)
    ]


def _nice_ceiling(value: int) -> int:
    """Round ``value`` up to 1, 2, 2.5 or 5 times a power of ten."""
    if value <= 4:
        return max(1, value)
    exponent = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * exponent:
            return int(step * exponent)
    return value


class MonthlyChart(QWidget):
    """Bars for ``[((year, month), count), ...]``; emits :attr:`monthClicked`."""

    monthClicked = pyqtSignal(int, int)  # year, month

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._series: list[tuple[YearMonth, int]] = []
        self._hover = -1
        self._empty_text = "No data yet"
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Monthly distribution chart")
        theme.manager().changed.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(520, 260)

    # ------------------------------------------------------------------ data

    @property
    def series(self) -> list[tuple[YearMonth, int]]:
        return list(self._series)

    def set_series(self, series: Sequence[tuple[YearMonth, int]], empty_text: str = "") -> None:
        self._series = fill_gaps(series)
        self._hover = -1
        if empty_text:
            self._empty_text = empty_text
        self.update()

    @property
    def hover_index(self) -> int:
        return self._hover

    def index_of(self, year: int, month: int) -> int:
        keys = [key for key, _ in self._series]
        return keys.index((year, month)) if (year, month) in keys else -1

    # -------------------------------------------------------------- geometry

    def _plot_rect(self) -> QRectF:
        return QRectF(
            _LEFT,
            _TOP,
            max(1.0, self.width() - _LEFT - _RIGHT),
            max(1.0, self.height() - _TOP - _BOTTOM),
        )

    def _scale_max(self) -> int:
        return _nice_ceiling(max((count for _, count in self._series), default=0))

    def _slot(self) -> float:
        return self._plot_rect().width() / max(1, len(self._series))

    def bar_rects(self) -> list[QRectF]:
        """Widget rectangles of every bar (zero-height bars included; public for tests)."""
        if not self._series:
            return []
        plot = self._plot_rect()
        slot = self._slot()
        width = max(2.0, min(_MAX_BAR, slot * 0.62))
        peak = self._scale_max()
        rects = []
        for i, (_, count) in enumerate(self._series):
            cx = plot.left() + slot * (i + 0.5)
            height = plot.height() * count / peak
            if count:
                height = max(height, 2.0)
            rects.append(QRectF(cx - width / 2, plot.bottom() - height, width, height))
        return rects

    def bar_centers(self) -> list[QPointF]:
        """A clickable point inside each bar's column (bottom area of the plot)."""
        plot = self._plot_rect()
        return [QPointF(r.center().x(), plot.bottom() - 4) for r in self.bar_rects()]

    def index_at(self, x: float) -> int:
        """Index of the month column under ``x``, else -1."""
        if not self._series:
            return -1
        plot = self._plot_rect()
        if not plot.left() <= x <= plot.right():
            return -1
        return min(len(self._series) - 1, int((x - plot.left()) / self._slot()))

    # ---------------------------------------------------------------- events

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        self._set_hover(self.index_at(event.position().x()))
        if self._hover >= 0:
            key, count = self._series[self._hover]
            hint = "Click to open this month's folder" if count else "No files this month"
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"<b>{month_label(key)}</b><br>{count:,} file{'s' if count != 1 else ''}"
                f"<br><span style='color:{theme.current().text_faint}'>{hint}</span>",
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
        elif key in (Qt.Key.Key_Home, Qt.Key.Key_End):
            self._set_hover(0 if key == Qt.Key.Key_Home else len(self._series) - 1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self._hover >= 0:
            self._activate(self._hover)
        else:
            super().keyPressEvent(event)

    def set_hover(self, index: int) -> None:
        self._set_hover(index)

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

    def _font(self, scale: float = 1.0, bold: bool = False) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(max(9, round(theme.FONT_CAPTION * scale)))
        font.setBold(bold)
        return font

    def paintEvent(self, event: QPaintEvent | None) -> None:
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._series:
            painter.setFont(self._font(1.1))
            painter.setPen(QColor(p.text_muted))
            painter.drawText(
                QRectF(self.rect()).adjusted(20, 0, -20, 0),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._empty_text,
            )
        else:
            rects = self.bar_rects()
            self._paint_grid(painter, p)
            self._paint_years(painter, p, rects)
            self._paint_bars(painter, p, rects)
            self._paint_month_labels(painter, p, rects)
        if self.hasFocus():
            painter.setPen(QPen(p.qcolor("accent", 0.6), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        painter.end()

    def _paint_grid(self, painter: QPainter, p: theme.Palette) -> None:
        plot = self._plot_rect()
        peak = self._scale_max()
        painter.setFont(self._font(0.92))
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = round(plot.bottom() - plot.height() * fraction) + 0.5
            painter.setPen(QPen(QColor(p.border if fraction else p.border_strong), 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            if fraction in (0.0, 0.5, 1.0):
                painter.setPen(QColor(p.text_faint))
                painter.drawText(
                    QRectF(0, y - 9, _LEFT - 10, 18),
                    int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                    f"{round(peak * fraction):,}",
                )

    def _paint_years(self, painter: QPainter, p: theme.Palette, rects: list[QRectF]) -> None:
        """A hairline before each January (when the range spans years) plus year labels."""
        plot = self._plot_rect()
        slot = self._slot()
        painter.setFont(self._font(0.92, bold=True))
        years_seen: set[int] = set()
        for i, ((year, _month), _) in enumerate(self._series):
            if year in years_seen:
                continue
            years_seen.add(year)
            x = plot.left() + slot * i
            if i > 0:
                painter.setPen(QPen(QColor(p.border_strong), 1, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(x, plot.top() - 18), QPointF(x, plot.bottom()))
            painter.setPen(QColor(p.text_muted))
            painter.drawText(
                QRectF(x + 6, plot.top() - 24, 80, 16),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                str(year),
            )

    def _paint_bars(self, painter: QPainter, p: theme.Palette, rects: list[QRectF]) -> None:
        hovering = self._hover >= 0
        for i, rect in enumerate(rects):
            if rect.height() <= 0:
                continue
            if i == self._hover:
                color = p.qcolor("accent_hover")
            else:
                color = p.qcolor("accent", 0.45 if hovering else 0.85)
            radius = min(4.0, rect.width() / 2, rect.height())
            path = QPainterPath()
            path.addRoundedRect(rect.adjusted(0, 0, 0, radius), radius, radius)
            painter.save()
            painter.setClipRect(rect)
            painter.fillPath(path, color)
            painter.restore()
        if hovering:
            self._paint_value(painter, p, rects[self._hover], self._series[self._hover][1])

    def _paint_value(self, painter: QPainter, p: theme.Palette, rect: QRectF, value: int) -> None:
        painter.setFont(self._font(1.0, bold=True))
        text = f"{value:,}"
        width = painter.fontMetrics().horizontalAdvance(text) + 14
        box = QRectF(rect.center().x() - width / 2, rect.top() - 26, width, 20)
        box.moveLeft(max(0.0, min(box.left(), self.width() - width)))
        painter.setPen(QPen(QColor(p.border_strong), 1))
        painter.setBrush(QColor(p.raised))
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(QColor(p.text))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_month_labels(self, painter: QPainter, p: theme.Palette, rects: list[QRectF]) -> None:
        plot = self._plot_rect()
        slot = self._slot()
        painter.setFont(self._font(0.92))
        widest = painter.fontMetrics().horizontalAdvance("Mmm") + 10
        step = max(1, math.ceil(widest / slot))
        for i, ((_year, month), _) in enumerate(self._series):
            if i != self._hover and (month - 1) % step:
                continue
            x = rects[i].center().x()
            hovered = i == self._hover
            painter.setPen(QColor(p.text if hovered else p.text_faint))
            text = MONTH_NAMES[month - 1][:3] if step < 3 or hovered else MONTH_NAMES[month - 1][0]
            painter.drawText(
                QRectF(x - 24, plot.bottom() + 8, 48, 16), Qt.AlignmentFlag.AlignCenter, text
            )
