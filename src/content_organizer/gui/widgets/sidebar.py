"""Left navigation: logo, page items with an optional count badge, status footer."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QEnterEvent, QFont, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from content_organizer.gui import icons, theme
from content_organizer.gui.widgets.card import label

EXPANDED_WIDTH = 224
COLLAPSED_WIDTH = 64


class NavButton(QAbstractButton):
    """Icon + label + badge; collapses to an icon (with a badge dot) in narrow mode."""

    def __init__(self, text: str, icon: str, shortcut: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(text)
        self.setToolTip(f"{text}  ({shortcut})")
        self._icon_name = icon
        self._badge = 0
        self._hover = False
        self.collapsed = False
        theme.manager().changed.connect(self.update)

    @property
    def badge(self) -> int:
        return self._badge

    def set_badge(self, count: int) -> None:
        self._badge = max(0, count)
        self.setAccessibleDescription(f"{count} waiting" if count else "")
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(40, 36)

    def enterEvent(self, event: QEnterEvent | None) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event: object) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(p.hover))
            painter.drawRoundedRect(rect, theme.RADIUS, theme.RADIUS)
            painter.setBrush(QColor(p.accent))
            painter.drawRoundedRect(QRectF(0, rect.center().y() - 8, 3, 16), 1.5, 1.5)
        elif self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(p.qcolor("hover", 0.6))
            painter.drawRoundedRect(rect, theme.RADIUS, theme.RADIUS)
        if self.hasFocus():
            painter.setPen(QColor(p.accent))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, theme.RADIUS, theme.RADIUS)

        token = "text" if self.isChecked() else "text_muted"
        icon_x = (self.width() - 18) / 2 if self.collapsed else 12
        icon_rect = QRectF(icon_x, (self.height() - 18) / 2, 18, 18)
        icons.icon(self._icon_name, getattr(p, token)).paint(painter, icon_rect.toRect())
        if self.collapsed:
            if self._badge:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(p.accent))
                painter.drawEllipse(QRectF(icon_rect.right() - 2, icon_rect.top() - 3, 8, 8))
            painter.end()
            return

        font = QFont(self.font())
        font.setPixelSize(theme.FONT_BODY)
        font.setWeight(QFont.Weight.DemiBold if self.isChecked() else QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor(getattr(p, token)))
        text_rect = QRectF(40, 0, self.width() - 40 - 44, self.height())
        painter.drawText(
            text_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.text()
        )
        if self._badge:
            self._paint_badge(painter, p, font)
        painter.end()

    def _paint_badge(self, painter: QPainter, p: theme.Palette, font: QFont) -> None:
        small = QFont(font)
        small.setPixelSize(11)
        small.setWeight(QFont.Weight.DemiBold)
        painter.setFont(small)
        text = f"{self._badge:,}" if self._badge < 1000 else "999+"
        width = max(20.0, painter.fontMetrics().horizontalAdvance(text) + 12.0)
        box = QRectF(self.width() - width - 10, (self.height() - 18) / 2, width, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p.accent_soft))
        painter.drawRoundedRect(box, 9, 9)
        painter.setPen(QColor(p.accent_text))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)


class StatusDot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self.tone = "ok"
        theme.manager().changed.connect(self.update)

    def set_tone(self, tone: str) -> None:
        self.tone = tone
        self.update()

    def paintEvent(self, event: QPaintEvent | None) -> None:
        p = theme.current()
        token = {"ok": "success", "warn": "warning", "error": "danger"}.get(self.tone, "text_faint")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(getattr(p, token)))
        painter.drawEllipse(QRectF(0, 0, 8, 8))
        painter.end()


class _StatusButton(QAbstractButton):
    """Footer row: dot + text; clickable (opens Settings)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 6, 8, 6)
        row.setSpacing(8)
        self.dot = StatusDot()
        row.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.text_label = label("", "caption")
        row.addWidget(self.text_label, 1)

    def sizeHint(self) -> QSize:
        return QSize(40, 30)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        if self.underMouse() or self.hasFocus():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.current().qcolor("hover", 0.6))
            painter.drawRoundedRect(QRectF(self.rect()), theme.RADIUS, theme.RADIUS)
            painter.end()


class Sidebar(QFrame):
    """Emits :attr:`pageRequested` with the page index when an item is clicked."""

    pageRequested = pyqtSignal(int)
    statusClicked = pyqtSignal()

    def __init__(self, version: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(EXPANDED_WIDTH)
        self._collapsed = False
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 18, 12, 14)
        column.setSpacing(2)
        column.addLayout(self._build_brand())
        column.addSpacing(22)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.items: list[NavButton] = []
        self.group.idClicked.connect(self.pageRequested)
        self._nav = column
        column.addStretch(1)
        self.status = _StatusButton()
        self.status.clicked.connect(self.statusClicked)
        column.addWidget(self.status)
        self.version_label = label(f"Version {version}", "caption")
        self.version_label.setContentsMargins(12, 2, 0, 0)
        column.addWidget(self.version_label)

    def _build_brand(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(8, 0, 0, 0)
        row.setSpacing(10)
        self.logo = QLabel()
        self.logo.setPixmap(icons.app_icon().pixmap(QSize(28, 28), self.devicePixelRatioF()))
        self.logo.setFixedSize(28, 28)
        row.addWidget(self.logo)
        self.brand_label = label(theme.APP_DISPLAY_NAME, "h3")
        row.addWidget(self.brand_label, 1)
        return row

    def add_item(self, text: str, icon: str, shortcut: str) -> NavButton:
        item = NavButton(text, icon, shortcut)
        item.collapsed = self._collapsed
        index = len(self.items)
        self.items.append(item)
        self.group.addButton(item, index)
        self._nav.insertWidget(2 + index, item)
        return item

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self.items):
            self.items[index].setChecked(True)

    def current(self) -> int:
        return self.group.checkedId()

    def set_status(self, tone: str, text: str, tooltip: str = "") -> None:
        self.status.dot.set_tone(tone)
        self.status.text_label.setText(text)
        self.status.setToolTip(tooltip or text)
        self.status.setAccessibleName(text)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setFixedWidth(COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH)
        layout = self.layout()
        if layout is not None:
            side = 10 if collapsed else 12
            layout.setContentsMargins(side, 18, side, 14)
        for widget in (self.brand_label, self.version_label, self.status.text_label):
            widget.setVisible(not collapsed)
        for item in self.items:
            item.collapsed = collapsed
            item.update()
