"""Step through files the rules could not place confidently and file them by hand.

The files come from the output's review folders (``REVIEW_CATEGORIES``: ``Videos`` and
``Other``). Every category is offered as a destination. Moves go through the core
executor with a one-file plan, so each one is journaled (undoable), never overwrites,
and skips byte-identical duplicates.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QImageReader, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from content_organizer.categories import Category, MediaType
from content_organizer.config import Config
from content_organizer.executor import Mode, Outcome, ProgressEvent, RunResult, execute
from content_organizer.gui import icons, theme
from content_organizer.gui.presenters import (
    current_category,
    describe_file,
    review_destination,
    review_files,
)
from content_organizer.gui.widgets import ElidedLabel
from content_organizer.planner import Options, Plan, PlannedMove
from content_organizer.rules import media_type_for

log = logging.getLogger(__name__)

#: Shortcut keys for the category buttons, in ``Category`` order.
CATEGORY_KEYS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-")
_PREVIEW_SIZE = QSize(360, 280)


def move_one(
    path: Path, category: Category, output: Path, config: Config
) -> tuple[RunResult, Path | None]:
    """Move ``path`` into ``category`` through the core (journaled, no overwrite).

    Returns the run result and the actual destination (``None`` if nothing moved).
    """
    output = Path(output).resolve()
    dest = review_destination(path, category, output, config)
    move = PlannedMove(path, dest, category, "Manual review")
    plan = Plan(source=output, output=output, options=Options(probe=False), moves=[move])
    events: list[ProgressEvent] = []
    result = execute(plan, Mode.MOVE, progress=events.append)
    moved = events and events[0].outcome is Outcome.MOVED
    return result, (events[0].dest if moved else None)


class ReviewDialog(QDialog):
    """Modal review session. :attr:`moved_count` tells the caller to refresh."""

    fileMoved = pyqtSignal(str, str)  # destination path, category value

    def __init__(self, output: Path, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.output = Path(output).resolve()
        self.config = config
        self.files: list[Path] = review_files(self.output, config)
        self.index = 0
        self.moved_count = 0
        self.setWindowTitle("Review files")  # Qt appends the app display name
        self.setMinimumSize(880, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        self.stack = QStackedWidget()
        self.empty_page = self._build_empty_page()
        self.review_page = self._build_review_page()
        self.stack.addWidget(self.empty_page)
        self.stack.addWidget(self.review_page)
        layout.addWidget(self.stack)
        self._install_shortcuts()
        self._show_current()

    # ----------------------------------------------------------------- pages

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.addStretch(1)
        badge = QLabel()
        badge.setPixmap(icons.icon("check", theme.SUCCESS).pixmap(56, 56))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(badge)
        self.empty_title = QLabel("Nothing to review")
        self.empty_title.setObjectName("emptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.empty_title)
        self.empty_text = QLabel()
        self.empty_text.setObjectName("cardSubtitle")
        self.empty_text.setWordWrap(True)
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.empty_text)
        column.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        column.addLayout(row)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Review files")
        title.setObjectName("statusTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.position_label = QLabel()
        self.position_label.setObjectName("cardSubtitle")
        header.addWidget(self.position_label)
        column.addLayout(header)
        self.position_bar = QProgressBar()
        self.position_bar.setTextVisible(False)
        self.position_bar.setFixedHeight(6)
        self.position_bar.setStyleSheet("QProgressBar { min-height: 6px; max-height: 6px; }")
        column.addWidget(self.position_bar)

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(self._build_preview_pane())
        body.addLayout(self._build_info_column(), 1)
        column.addLayout(body, 1)

        move_label = QLabel("Move to  (press the number key shown)")
        move_label.setObjectName("fieldLabel")
        column.addWidget(move_label)
        column.addLayout(self._build_category_grid())

        self.status_label = QLabel(" ")
        self.status_label.setObjectName("statusNeutral")
        self.status_label.setWordWrap(True)
        column.addWidget(self.status_label)
        column.addLayout(self._build_nav_row())
        return page

    def _build_preview_pane(self) -> QFrame:
        pane = QFrame()
        pane.setObjectName("previewPane")
        pane.setFixedSize(_PREVIEW_SIZE + QSize(24, 24))
        inner = QVBoxLayout(pane)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setAccessibleName("File preview")
        inner.addWidget(self.preview)
        return pane

    def _build_info_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(8)
        self.name_label = QLabel()
        self.name_label.setObjectName("cardTitle")
        self.name_label.setWordWrap(True)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(self.name_label)
        self.reason_label = QLabel()
        self.reason_label.setObjectName("statusWarn")
        self.reason_label.setWordWrap(True)
        column.addWidget(self.reason_label)
        self.info_form = QFormLayout()
        self.info_form.setHorizontalSpacing(14)
        self.info_form.setVerticalSpacing(6)
        column.addLayout(self.info_form)
        column.addStretch(1)
        buttons = QHBoxLayout()
        self.open_button = QPushButton(icons.icon("open"), "Open file")
        self.open_button.setToolTip("Open with the default app (O)")
        self.open_button.clicked.connect(self.open_current)
        buttons.addWidget(self.open_button)
        self.reveal_button = QPushButton(icons.icon("folder"), "Open folder")
        self.reveal_button.setToolTip("Open the folder that contains this file")
        self.reveal_button.clicked.connect(self.open_current_folder)
        buttons.addWidget(self.reveal_button)
        buttons.addStretch(1)
        column.addLayout(buttons)
        return column

    def _build_category_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(8)
        self.category_buttons: dict[Category, QPushButton] = {}
        for i, (category, key) in enumerate(zip(Category, CATEGORY_KEYS, strict=True)):
            button = QPushButton(f"{key}   {category.label}")
            button.setObjectName("categoryButton")
            button.setToolTip(f"Move to {category.value}  (key {key})")
            button.setStyleSheet(
                f"QPushButton#categoryButton {{ border-left: 4px solid "
                f"{theme.CATEGORY_COLORS[category]}; }}"
            )
            button.clicked.connect(lambda _=False, c=category: self.categorize(c))
            grid.addWidget(button, i // 4, i % 4)
            self.category_buttons[category] = button
        return grid

    def _build_nav_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.back_button = QPushButton(icons.icon("back"), "Previous")
        self.back_button.setToolTip("Go back to the previous file (Left arrow)")
        self.back_button.clicked.connect(self.previous)
        row.addWidget(self.back_button)
        self.skip_button = QPushButton(icons.icon("skip"), "Skip")
        self.skip_button.setToolTip("Leave this file where it is (Right arrow or S)")
        self.skip_button.clicked.connect(self.skip)
        row.addWidget(self.skip_button)
        row.addStretch(1)
        done = QPushButton(icons.icon("check"), "Done")
        done.setToolTip("Finish reviewing; skipped files stay in their folder (Esc)")
        done.clicked.connect(self.accept)
        row.addWidget(done)
        return row

    def _install_shortcuts(self) -> None:
        for category, key in zip(Category, CATEGORY_KEYS, strict=True):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda c=category: self._shortcut_categorize(c))
        for key, slot in (
            ("Right", self.skip),
            ("S", self.skip),
            ("Left", self.previous),
            ("O", self.open_current),
        ):
            QShortcut(QKeySequence(key), self).activated.connect(slot)

    # ----------------------------------------------------------------- state

    @property
    def current(self) -> Path | None:
        return self.files[self.index] if 0 <= self.index < len(self.files) else None

    def _show_current(self) -> None:
        path = self.current
        if path is None:
            self._show_empty()
            return
        self.stack.setCurrentWidget(self.review_page)
        total = len(self.files)
        self.position_label.setText(f"File {self.index + 1} of {total}")
        self.position_bar.setRange(0, total)
        self.position_bar.setValue(self.index + 1)
        self.name_label.setText(path.name)
        here = current_category(path, self.output, self.config)
        self.reason_label.setText(self._reason_text(here))
        self._fill_info(path)
        self._show_preview(path)
        for category, button in self.category_buttons.items():
            button.setEnabled(category != here)
        self.back_button.setEnabled(self.index > 0)

    def _reason_text(self, here: Category | None) -> str:
        if here is Category.VIDEOS:
            return "Orientation could not be detected. Is it vertical, horizontal or finished?"
        if here is Category.OTHER:
            return "Unrecognised file type. Choose where it belongs, or skip it."
        return ""

    def _show_empty(self) -> None:
        self.stack.setCurrentWidget(self.empty_page)
        folders = " and ".join(
            f"'{self.config.folder_for(c)}'" for c in (Category.VIDEOS, Category.OTHER)
        )
        if self.moved_count:
            self.empty_title.setText("All done")
            self.empty_text.setText(
                f"You filed {self.moved_count} file{'s' if self.moved_count != 1 else ''}. "
                "Use Undo last run in the main window to reverse the most recent move."
            )
        else:
            self.empty_title.setText("Nothing to review")
            self.empty_text.setText(
                f"There are no files in the {folders} folders of {self.output}.\n"
                "Files land there when their video orientation or file type can't be "
                "determined automatically."
            )

    def _fill_info(self, path: Path) -> None:
        while self.info_form.rowCount():
            self.info_form.removeRow(0)
        for label, value in describe_file(path, self.output):
            value_label = ElidedLabel(value)
            key_label = QLabel(label)
            key_label.setObjectName("hint")
            self.info_form.addRow(key_label, value_label)

    def _show_preview(self, path: Path) -> None:
        pixmap = QPixmap()
        if media_type_for(path.name, self.config) is MediaType.IMAGE:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(size.scaled(_PREVIEW_SIZE, Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self.preview.setPixmap(icons.icon("file", theme.TEXT_FAINT).pixmap(96, 96))
            self.preview.setToolTip(f"No preview for {path.suffix or 'this file'}")
        else:
            self.preview.setPixmap(pixmap)
            self.preview.setToolTip(path.name)

    # --------------------------------------------------------------- actions

    def _shortcut_categorize(self, category: Category) -> None:
        button = self.category_buttons.get(category)
        if self.current is not None and button is not None and button.isEnabled():
            self.categorize(category)

    def categorize(self, category: Category) -> None:
        path = self.current
        if path is None:
            return
        result, dest = move_one(path, category, self.output, self.config)
        if result.errors:
            self._set_status("error", f"Could not move the file: {result.errors[0].message}")
            return
        if result.skipped_duplicates:
            dup = result.skipped_duplicates[0].dest
            self._set_status(
                "warn", f"An identical file already exists at {dup}; this copy was left in place."
            )
            return
        self.moved_count += 1
        self.fileMoved.emit(str(dest), category.value)
        self._set_status("ok", f"Moved {path.name} to {category.label}.")
        del self.files[self.index]
        self.index = min(self.index, max(0, len(self.files) - 1))
        self._show_current()

    def skip(self) -> None:
        if self.current is None:
            return
        if self.index + 1 >= len(self.files):
            self._set_status("neutral", "That was the last file. Press Done to finish.")
            return
        self.index += 1
        self._set_status("neutral", " ")
        self._show_current()

    def previous(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._set_status("neutral", " ")
            self._show_current()

    def open_current(self) -> None:
        if self.current is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current)))

    def open_current_folder(self) -> None:
        if self.current is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current.parent)))

    def _set_status(self, kind: str, text: str) -> None:
        names = {"ok": "statusOk", "warn": "statusWarn", "error": "statusError"}
        self.status_label.setObjectName(names.get(kind, "statusNeutral"))
        self.status_label.setText(text)
        style = self.status_label.style()
        if style is not None:
            style.unpolish(self.status_label)
            style.polish(self.status_label)
