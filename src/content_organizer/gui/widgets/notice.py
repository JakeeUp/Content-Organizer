"""Inline notices and empty states."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from content_organizer.gui import icons
from content_organizer.gui.widgets.buttons import button
from content_organizer.gui.widgets.card import label


class Notice(QFrame):
    """A warning strip with optional action buttons."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("notice")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 10, 10)
        row.setSpacing(10)
        icon = QLabel()
        icons.themed(icon, "warning", "warning", 18)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        self.text_label = label(text, wrap=True)
        row.addWidget(self.text_label, 1)
        self._buttons = row

    def add_button(self, widget: QPushButton) -> None:
        self._buttons.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)


class EmptyState(QWidget):
    """Centred icon, title, text and an optional action."""

    actionTriggered = pyqtSignal()

    def __init__(
        self,
        icon: str,
        title: str,
        text: str,
        action: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(24, 24, 24, 24)
        column.setSpacing(6)
        column.addStretch(1)
        self.badge = _IconBadge(icon)
        column.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(10)
        self.title_label = label(title, "h2")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.title_label)
        self.text_label = label(text, "muted", wrap=True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setMaximumWidth(440)
        column.addWidget(self.text_label, 0, Qt.AlignmentFlag.AlignHCenter)
        self.action_button = button(action, variant="primary")
        self.action_button.setVisible(bool(action))
        self.action_button.clicked.connect(self.actionTriggered)
        column.addSpacing(10)
        column.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(2)

    def set_content(self, icon: str, title: str, text: str, action: str = "") -> None:
        self.badge.set_icon(icon)
        self.title_label.setText(title)
        self.text_label.setText(text)
        self.action_button.setText(action)
        self.action_button.setVisible(bool(action))


class _IconBadge(QFrame):
    """A 64px rounded tile holding a large muted icon."""

    def __init__(self, icon: str) -> None:
        super().__init__()
        self.setProperty("card", True)
        self.setFixedSize(64, 64)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon)
        self.set_icon(icon)

    def set_icon(self, name: str) -> None:
        icons.themed(self._icon, name, "text_muted", 28)
