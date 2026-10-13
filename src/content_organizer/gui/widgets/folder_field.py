"""Labelled folder picker: editable path (the source of truth), Browse button, drop target."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from content_organizer.gui import icons


def _dropped_folder(event: QDragEnterEvent | QDropEvent) -> Path | None:
    mime = event.mimeData()
    if mime is None or not mime.hasUrls():
        return None
    for url in mime.urls():
        if url.isLocalFile():
            path = Path(url.toLocalFile())
            if path.is_dir():
                return path
    return None


class FolderLineEdit(QLineEdit):
    """Line edit that accepts a folder dragged from the file manager."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setClearButtonEnabled(True)

    def _set_drop_highlight(self, on: bool) -> None:
        self.setProperty("dropTarget", "true" if on else "false")
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        if event is not None and _dropped_folder(event) is not None:
            event.acceptProposedAction()
            self._set_drop_highlight(True)
        elif event is not None:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent | None) -> None:
        self._set_drop_highlight(False)

    def dropEvent(self, event: QDropEvent | None) -> None:
        self._set_drop_highlight(False)
        if event is None:
            return
        folder = _dropped_folder(event)
        if folder is not None:
            self.setText(str(folder))
            event.acceptProposedAction()


class FolderField(QWidget):
    """Label + hint + path edit + Browse button + live validation message."""

    pathChanged = pyqtSignal(str)

    def __init__(
        self, label: str, hint: str, dialog_title: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._dialog_title = dialog_title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        heading = QHBoxLayout()
        self.label = QLabel(label)
        self.label.setObjectName("fieldLabel")
        heading.addWidget(self.label)
        hint_label = QLabel(hint)
        hint_label.setObjectName("hint")
        heading.addWidget(hint_label)
        heading.addStretch(1)
        layout.addLayout(heading)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = FolderLineEdit()
        self.edit.setPlaceholderText("Type, paste or drop a folder here")
        self.edit.setAccessibleName(label)
        self.label.setBuddy(self.edit)
        row.addWidget(self.edit, 1)
        self.browse_button = QPushButton(icons.icon("folder"), "Browse…")
        self.browse_button.setToolTip(f"Choose the {label.lower()} with a folder dialog")
        self.browse_button.setAccessibleName(f"Browse for {label.lower()}")
        row.addWidget(self.browse_button)
        layout.addLayout(row)

        self.status = QLabel(" ")
        self.status.setObjectName("statusNeutral")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.edit.textChanged.connect(self.pathChanged)
        self.browse_button.clicked.connect(self._browse)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, text: str) -> None:
        self.edit.setText(text)

    def set_status(self, kind: str, message: str) -> None:
        """``kind`` is ``ok``, ``warn``, ``error`` or ``neutral``."""
        self.status.setObjectName(
            {"ok": "statusOk", "warn": "statusWarn", "error": "statusError"}.get(
                kind, "statusNeutral"
            )
        )
        self.status.setText(message or " ")
        self.edit.setProperty("validity", kind)
        for widget in (self.status, self.edit):
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)

    def _browse(self) -> None:
        start = self.text() if Path(self.text()).is_dir() else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, self._dialog_title, start)
        if chosen:
            self.edit.setText(str(Path(chosen)))
            self.edit.setFocus()
