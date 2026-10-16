"""Shared page scaffolding: a scrollable column under a :class:`PageHeader`."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from content_organizer.gui import theme
from content_organizer.gui.widgets import PageHeader

PAGE_MARGINS = (32, 28, 32, 24)


class Page(QWidget):
    """``header`` on top, then :attr:`body` inside a vertical scroll area.

    :attr:`outer` is the non-scrolling column, for footers that must stay visible.
    """

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(*PAGE_MARGINS)
        self.outer.setSpacing(2 * theme.SPACE)
        self.header = PageHeader(title, subtitle)
        self.outer.addWidget(self.header)

        content = QWidget()
        content.setObjectName("page")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(2 * theme.SPACE)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)
        self.outer.addWidget(self.scroll_area, 1)
