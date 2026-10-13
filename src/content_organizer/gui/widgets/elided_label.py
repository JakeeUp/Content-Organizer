"""A label that elides long text (paths) instead of widening the layout."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPainter, QPaintEvent
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    """Shows the full text as a tooltip; paints it elided to the available width."""

    def __init__(
        self,
        text: str = "",
        mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setToolTip(text)

    def setText(self, text: str | None) -> None:
        super().setText(text)
        self.setToolTip(text or "")

    def minimumSizeHint(self) -> QSize:
        return QSize(20, super().minimumSizeHint().height())

    def paintEvent(self, event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        rect = self.contentsRect()
        elided = self.fontMetrics().elidedText(self.text(), self._mode, rect.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(rect, int(self.alignment()), elided)
        painter.end()
