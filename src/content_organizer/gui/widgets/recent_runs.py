"""The Recent runs card on the Organize page."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from content_organizer.gui import icons
from content_organizer.gui.presenters import RunRecord, format_when
from content_organizer.gui.widgets.buttons import button
from content_organizer.gui.widgets.card import Card, divider, label
from content_organizer.gui.widgets.elided_label import ElidedLabel


class _RunRow(QWidget):
    def __init__(self, record: RunRecord, latest: bool) -> None:
        super().__init__()
        self.setObjectName("plain")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 10, 0, 10)
        row.setSpacing(12)
        badge = QFrame()
        badge.setProperty("card", True)
        badge.setFixedSize(32, 32)
        inner = QVBoxLayout(badge)
        inner.setContentsMargins(0, 0, 0, 0)
        glyph = QLabel()
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icons.themed(glyph, "clock", "text_muted", 16)
        inner.addWidget(glyph)
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        heading.addWidget(label(record.title, "strong"))
        if latest:
            heading.addWidget(label("Undo available", "tag"))
        heading.addStretch(1)
        texts.addLayout(heading)
        source = Path(record.source).name or record.source
        detail = ElidedLabel(f"{format_when(record.started)} · from {source}")
        detail.setProperty("role", "caption")
        detail.setToolTip(f"Source: {record.source}\nJournal: {record.journal}")
        texts.addWidget(detail)
        row.addLayout(texts, 1)


class RecentRuns(Card):
    """Lists undoable runs, newest first. The newest one can be undone."""

    undoRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            "Recent runs", "Every run is journaled, so the latest can be undone.", parent
        )
        self.undo_link = button(
            "Undo latest", variant="link", tooltip="Undo the latest run (Ctrl+Z)"
        )
        self.undo_link.clicked.connect(self.undoRequested)
        self.add_header_widget(self.undo_link)
        self._rows = QVBoxLayout()
        self._rows.setSpacing(0)
        self.body.addLayout(self._rows)
        self.body.addStretch(1)
        self.empty_label = label("", "muted", wrap=True)
        self._rows.addWidget(self.empty_label)
        self.records: list[RunRecord] = []
        self.set_records([], "Runs will appear here after you organize a folder.")

    def set_records(self, records: list[RunRecord], empty_text: str = "") -> None:
        self.records = list(records)
        while self._rows.count() > 1:
            item = self._rows.takeAt(1)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        for i, record in enumerate(records):
            if i:
                self._rows.addWidget(divider())
            self._rows.addWidget(_RunRow(record, latest=i == 0))
        self.empty_label.setText(empty_text or "No runs yet for this output folder.")
        self.empty_label.setVisible(not records)
        self.undo_link.setVisible(bool(records))
