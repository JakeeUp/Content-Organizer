"""Flat surface primitives: card, metric tile, divider and label helpers."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from content_organizer.gui import theme


def label(text: str = "", role: str = "", *, wrap: bool = False, tone: str = "") -> QLabel:
    """A ``QLabel`` with a typography ``role`` (title, h2, h3, muted, caption ...)."""
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    if tone:
        widget.setProperty("tone", tone)
    widget.setWordWrap(wrap)
    return widget


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFixedHeight(1)
    return line


class Card(QFrame):
    """A bordered surface with an optional title row and a :attr:`body` layout."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
        *,
        margins: tuple[int, int, int, int] = (20, 18, 20, 20),
    ) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*margins)
        outer.setSpacing(14)

        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = label(title, "h3")
        self.subtitle_label = label(subtitle, "caption", wrap=True)
        self.subtitle_label.setVisible(bool(subtitle))
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        self.header.addLayout(titles, 1)
        if title:
            outer.addLayout(self.header)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)

    def add_header_widget(self, widget: QWidget) -> None:
        self.header.addWidget(widget, 0, Qt.AlignmentFlag.AlignTop)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class MetricTile(QFrame):
    """A small number with a caption, e.g. "Moved / 320"."""

    def __init__(self, caption: str, value: str = "0", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tile")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(2)
        self.caption_label = label(caption, "caption")
        self.value_label = label(value, "metric")
        column.addWidget(self.caption_label)
        column.addWidget(self.value_label)

    def set_value(self, value: str, tone: str = "") -> None:
        self.value_label.setText(value)
        theme.set_props(self.value_label, tone=tone or None)

    def value(self) -> str:
        return self.value_label.text()
