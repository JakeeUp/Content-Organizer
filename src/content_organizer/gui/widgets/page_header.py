"""Page title, subtitle and page-level actions on the right."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from content_organizer.gui import theme
from content_organizer.gui.widgets.card import label
from content_organizer.gui.widgets.elided_label import ElidedLabel


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACE)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = label(title, "title")
        self.subtitle_label = ElidedLabel(subtitle, Qt.TextElideMode.ElideMiddle)
        self.subtitle_label.setProperty("role", "subtitle")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        row.addLayout(titles, 1)
        self._actions = QHBoxLayout()
        self._actions.setSpacing(theme.SPACE)
        row.addLayout(self._actions)

    def add_action(self, widget: QWidget) -> None:
        self._actions.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_subtitle(self, text: str, tooltip: str = "") -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setToolTip(tooltip or text)
