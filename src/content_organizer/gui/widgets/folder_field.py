"""A numbered folder step: drop zone when empty, editable path, Browse, live status."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PyQt6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from content_organizer.gui import theme
from content_organizer.gui.widgets.buttons import button
from content_organizer.gui.widgets.card import label


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

    hoverChanged = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setClearButtonEnabled(True)

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        if event is not None and _dropped_folder(event) is not None:
            event.acceptProposedAction()
            self.hoverChanged.emit(True)
        elif event is not None:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent | None) -> None:
        self.hoverChanged.emit(False)

    def dropEvent(self, event: QDropEvent | None) -> None:
        self.hoverChanged.emit(False)
        if event is None:
            return
        folder = _dropped_folder(event)
        if folder is not None:
            self.setText(str(folder))
            event.acceptProposedAction()


class FolderField(QFrame):
    """Step number, title, hint, path edit, Browse button and a validation line.

    The whole card is a drop target; it is drawn with a dashed border while empty.
    """

    pathChanged = pyqtSignal(str)

    def __init__(
        self,
        label_text: str,
        hint: str,
        dialog_title: str,
        step: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dialog_title = dialog_title
        self.setProperty("card", True)
        self.setAcceptDrops(True)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(14)
        self.step_label = label(str(step), "step")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_label.setVisible(step > 0)
        outer.addWidget(self.step_label, 0, Qt.AlignmentFlag.AlignTop)

        column = QVBoxLayout()
        column.setSpacing(8)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        self.label = label(label_text, "h3")
        heading.addWidget(self.label)
        self.hint_label = label(hint, "caption")
        heading.addWidget(self.hint_label, 1)
        column.addLayout(heading)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = FolderLineEdit()
        self.edit.setPlaceholderText("Drop a folder here, paste a path, or browse")
        self.edit.setAccessibleName(label_text)
        self.label.setBuddy(self.edit)
        row.addWidget(self.edit, 1)
        self.browse_button = button(
            "Browse…", "folder", tooltip=f"Choose the {label_text.lower()} with a folder dialog"
        )
        self.browse_button.setAccessibleName(f"Browse for {label_text.lower()}")
        row.addWidget(self.browse_button)
        column.addLayout(row)

        self.status = label(" ", "caption", wrap=True, tone="neutral")
        column.addWidget(self.status)
        outer.addLayout(column, 1)

        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.hoverChanged.connect(self._set_drop_hover)
        self.browse_button.clicked.connect(self._browse)
        self._refresh_zone()

    # ------------------------------------------------------------------ api

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, text: str) -> None:
        self.edit.setText(text)

    def set_status(self, kind: str, message: str) -> None:
        """``kind`` is ``ok``, ``warn``, ``error`` or ``neutral``."""
        self.status.setText(message or " ")
        theme.set_props(self.status, tone=kind)
        theme.set_props(self.edit, validity=kind)
        theme.set_props(self.step_label, done="true" if kind in ("ok", "warn") else "false")

    def tone(self) -> str:
        return str(self.status.property("tone"))

    # -------------------------------------------------------------- drop zone

    def _on_text_changed(self, text: str) -> None:
        self._refresh_zone()
        self.pathChanged.emit(text)

    def _refresh_zone(self, hover: bool = False) -> None:
        state = "active" if hover else ("empty" if not self.text() else "set")
        if self.property("dropzone") != state:
            theme.set_props(self, dropzone=state)

    def _set_drop_hover(self, on: bool) -> None:
        self._refresh_zone(hover=on)

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        self.edit.dragEnterEvent(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent | None) -> None:
        self.edit.dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent | None) -> None:
        self.edit.dropEvent(event)

    def _browse(self) -> None:
        start = self.text() if Path(self.text()).is_dir() else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, self._dialog_title, start)
        if chosen:
            self.edit.setText(str(Path(chosen)))
            self.edit.setFocus()
