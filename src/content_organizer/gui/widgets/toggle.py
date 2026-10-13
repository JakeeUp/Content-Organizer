"""An animated on/off switch that behaves like a real checkable button.

Being a :class:`QAbstractButton` gives it keyboard focus, Space to toggle, the
``toggled`` signal (also emitted by ``setChecked``), and accessibility for free.
"""

from __future__ import annotations

from PyQt6 import QtCore
from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
)
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from content_organizer.gui import theme

_ON = QColor(theme.SUCCESS)
_OFF = QColor("#3A4256")
_DISABLED = QColor("#2A3244")


class ToggleSwitch(QAbstractButton):
    """A 46x26 switch; the thumb slides when the checked state changes."""

    def __init__(self, parent: QWidget | None = None, *, checked: bool = False) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._offset = 1.0 if checked else 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to)

    def sizeHint(self) -> QSize:
        return QSize(46, 26)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    # pyqtProperty is missing from the PyQt6 stubs.
    offset = QtCore.pyqtProperty(float, fget=_get_offset, fset=_set_offset)  # type: ignore[attr-defined]

    def _animate_to(self, checked: bool) -> None:
        self._animation.stop()
        if not self.isVisible():
            self._set_offset(1.0 if checked else 0.0)
            return
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        # Only the primary button toggles (right-click used to toggle too).
        if event is not None and event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        super().mouseReleaseEvent(event)

    def hitButton(self, pos: QPoint) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = 46.0, 26.0
        x0 = (self.width() - w) / 2
        y0 = (self.height() - h) / 2
        track = QRectF(x0, y0, w, h)

        if not self.isEnabled():
            color = _DISABLED
        else:
            color = QColor(
                round(_OFF.red() + (_ON.red() - _OFF.red()) * self._offset),
                round(_OFF.green() + (_ON.green() - _OFF.green()) * self._offset),
                round(_OFF.blue() + (_ON.blue() - _OFF.blue()) * self._offset),
            )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(track, h / 2, h / 2)

        if self.hasFocus():
            painter.setPen(QPen(QColor(theme.ACCENT_HOVER), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track.adjusted(-2, -2, 2, 2), h / 2 + 2, h / 2 + 2)

        margin = 3.0
        diameter = h - 2 * margin
        thumb_x = x0 + margin + (w - diameter - 2 * margin) * self._offset
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF") if self.isEnabled() else QColor("#6B7280"))
        painter.drawEllipse(QRectF(thumb_x, y0 + margin, diameter, diameter))
        painter.end()


class ToggleRow(QWidget):
    """Title + description on the left, a :class:`ToggleSwitch` on the right.

    Clicking anywhere on the text toggles the switch; the switch is the label's buddy.
    """

    def __init__(
        self,
        title: str,
        description: str,
        *,
        checked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("fieldLabel")
        self.description_label = QLabel(description)
        self.description_label.setObjectName("hint")
        self.description_label.setWordWrap(True)
        texts.addWidget(self.title_label)
        texts.addWidget(self.description_label)
        layout.addLayout(texts, 1)
        self.switch = ToggleSwitch(checked=checked)
        self.switch.setAccessibleName(title)
        self.switch.setAccessibleDescription(description)
        self.title_label.setBuddy(self.switch)
        layout.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)

    def isChecked(self) -> bool:
        return self.switch.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.switch.setChecked(checked)

    def setToolTip(self, text: str | None) -> None:
        super().setToolTip(text)
        self.switch.setToolTip(text)

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.title_label.setEnabled(enabled)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if (
            event is not None
            and event.button() == Qt.MouseButton.LeftButton
            and self.switch.isEnabled()
        ):
            self.switch.toggle()
            self.switch.setFocus()
