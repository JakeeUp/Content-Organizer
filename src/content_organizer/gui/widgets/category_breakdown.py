"""Category composition: a stacked bar on top, then one row per category."""

from __future__ import annotations

from collections.abc import Mapping

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPaintEvent
from PyQt6.QtWidgets import QSizePolicy, QWidget

from content_organizer.categories import Category
from content_organizer.gui import theme

_STACK_H = 10.0
_ROW_H = 30.0
_GAP = 18.0


class CategoryBreakdown(QWidget):
    """Shows non-empty categories in ``Category`` order with share-of-total bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._counts: dict[Category, int] = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        theme.manager().changed.connect(self.update)

    def set_counts(self, counts: Mapping[Category, int]) -> None:
        self._counts = {c: int(counts.get(c, 0)) for c in Category if counts.get(c, 0)}
        tips = [f"{c.label}: {n:,}" for c, n in self._counts.items()]
        self.setToolTip("\n".join(tips))
        self.updateGeometry()
        self.update()

    @property
    def total(self) -> int:
        return sum(self._counts.values())

    def count(self, category: Category) -> int:
        return self._counts.get(category, 0)

    def rows(self) -> list[Category]:
        return list(self._counts)

    def sizeHint(self) -> QSize:
        return QSize(320, round(_STACK_H + _GAP + _ROW_H * max(1, len(self._counts))))

    def minimumSizeHint(self) -> QSize:
        return QSize(220, self.sizeHint().height())

    def paintEvent(self, event: QPaintEvent | None) -> None:
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = float(self.width())
        total = self.total
        self._paint_stack(painter, p, width, total)
        font = QFont(self.font())
        font.setPixelSize(theme.FONT_BODY)
        small = QFont(font)
        small.setPixelSize(theme.FONT_CAPTION)
        y = _STACK_H + _GAP
        count_w, pct_w = 52.0, 40.0
        label_w = min(170.0, width * 0.42)
        bar_x = label_w + 8
        bar_w = max(10.0, width - bar_x - count_w - pct_w - 12)
        for category, count in self._counts.items():
            mid = y + _ROW_H / 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(p.category(category))
            painter.drawEllipse(QRectF(0, mid - 4, 8, 8))
            painter.setFont(font)
            painter.setPen(QColor(p.text))
            label = painter.fontMetrics().elidedText(
                category.label, Qt.TextElideMode.ElideRight, round(label_w - 18)
            )
            painter.drawText(QRectF(18, y, label_w - 18, _ROW_H), _LEFT_V, label)
            track = QRectF(bar_x, mid - 3, bar_w, 6)
            self._rounded(painter, track, QColor(p.track))
            share = count / total if total else 0.0
            if share:
                fill = QRectF(track.left(), track.top(), max(6.0, bar_w * share), 6)
                self._rounded(painter, fill, p.category(category, 0.9))
            painter.setPen(QColor(p.text))
            painter.drawText(QRectF(bar_x + bar_w, y, count_w, _ROW_H), _RIGHT_V, f"{count:,}")
            painter.setFont(small)
            painter.setPen(QColor(p.text_faint))
            painter.drawText(QRectF(width - pct_w, y, pct_w, _ROW_H), _RIGHT_V, f"{share:.0%}")
            y += _ROW_H
        painter.end()

    def _paint_stack(self, painter: QPainter, p: theme.Palette, width: float, total: int) -> None:
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(0, 0, width, _STACK_H), _STACK_H / 2, _STACK_H / 2)
        painter.fillPath(outline, QColor(p.track))
        if not total:
            return
        painter.save()
        painter.setClipPath(outline)
        x = 0.0
        for category, count in self._counts.items():
            span = width * count / total
            painter.fillRect(QRectF(x, 0, span + 0.5, _STACK_H), p.category(category))
            x += span
            if x < width - 1:  # hairline gap between segments
                painter.fillRect(QRectF(x - 1, 0, 2, _STACK_H), QColor(p.surface))
        painter.restore()

    @staticmethod
    def _rounded(painter: QPainter, rect: QRectF, color: QColor) -> None:
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.fillPath(path, color)


_LEFT_V = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
_RIGHT_V = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
