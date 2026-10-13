"""Rounded dashboard card with an optional title row."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    """A ``QFrame#card`` with a soft shadow, a title, an optional subtitle and a body.

    Add content to :attr:`body`; widgets for the right side of the title row (for
    example a refresh button) go into :meth:`add_header_widget`.
    """

    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 20)
        outer.setSpacing(12)

        self._header = QHBoxLayout()
        self._header.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("cardTitle")
        titles.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("cardSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        titles.addWidget(self.subtitle_label)
        self._header.addLayout(titles, 1)
        if title:
            outer.addLayout(self._header)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)

    def add_header_widget(self, widget: QWidget) -> None:
        self._header.addWidget(widget)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))
