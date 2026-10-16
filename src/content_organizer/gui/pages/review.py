"""Review: step through files the rules could not place confidently and file them by hand.

The files come from the output's review folders (``REVIEW_CATEGORIES``: ``Videos`` and
``Other``). Every category is offered as a destination. Moves go through the core
executor with a one-file plan, so each one is journaled (undoable), never overwrites,
and skips byte-identical duplicates.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut, QShowEvent
from PyQt6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from content_organizer.categories import Category
from content_organizer.config import Config
from content_organizer.executor import Mode, Outcome, ProgressEvent, RunResult, execute
from content_organizer.gui import theme
from content_organizer.gui.context import AppContext
from content_organizer.gui.pages.base import Page
from content_organizer.gui.presenters import (
    current_category,
    describe_file,
    plural,
    review_destination,
    review_files,
    review_reason,
)
from content_organizer.gui.widgets import Card, ElidedLabel, EmptyState, FilePreview, button, label
from content_organizer.planner import Options, Plan, PlannedMove
from content_organizer.rules import media_type_for

#: Shortcut keys for the category buttons, in ``Category`` order.
CATEGORY_KEYS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-")


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


class ReviewPage(Page):
    fileMoved = pyqtSignal(str, str)  # destination path, category value
    organizeRequested = pyqtSignal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__("Review", "File what the rules couldn't place confidently.", parent)
        self.context = context
        self.output: Path | None = None
        self.files: list[Path] = []
        self.index = 0
        self.moved_count = 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.position_label = label("", "muted")
        self.header.add_action(self.position_label)

        self.stack = QStackedWidget()
        self.empty = EmptyState("check-circle", "Nothing to review", "")
        self.empty.actionTriggered.connect(self.organizeRequested)
        self.stack.addWidget(self.empty)
        self.review_view = self._build_review_view()
        self.stack.addWidget(self.review_view)
        self.body.addWidget(self.stack, 1)
        self._install_shortcuts()
        context.outputChanged.connect(self.reload)
        context.busyChanged.connect(lambda _busy: self._show_current())
        self.reload()

    # ------------------------------------------------------------------ build

    def _build_review_view(self) -> QWidget:
        view = QWidget()
        view.setObjectName("page")
        column = QVBoxLayout(view)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2 * theme.SPACE)
        self.position_bar = QProgressBar()
        self.position_bar.setTextVisible(False)
        column.addWidget(self.position_bar)

        row = QHBoxLayout()
        row.setSpacing(2 * theme.SPACE)
        self.preview = FilePreview()
        row.addWidget(self.preview, 3)
        row.addWidget(self._build_info_card(), 2)
        column.addLayout(row, 1)

        moves = Card("Move to", "Press the number key shown on a category.")
        moves.body.addLayout(self._build_category_grid())
        self.status_label = label(" ", "caption", wrap=True, tone="neutral")
        moves.body.addWidget(self.status_label)
        column.addWidget(moves)
        return view

    def _build_info_card(self) -> Card:
        card = Card()
        self.name_label = label("", "h2", wrap=True)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(self.name_label)
        self.reason_label = label("", wrap=True, tone="warn")
        card.body.addWidget(self.reason_label)
        self.info_form = QFormLayout()
        self.info_form.setHorizontalSpacing(14)
        self.info_form.setVerticalSpacing(6)
        card.body.addLayout(self.info_form)
        card.body.addStretch(1)

        files = QHBoxLayout()
        files.setSpacing(theme.SPACE)
        self.open_button = button("Open file", "open", tooltip="Open with the default app (O)")
        self.open_button.clicked.connect(self.open_current)
        self.reveal_button = button(
            "Open folder", "folder", tooltip="Open the folder that contains this file"
        )
        self.reveal_button.clicked.connect(self.open_current_folder)
        files.addWidget(self.open_button)
        files.addWidget(self.reveal_button)
        files.addStretch(1)
        card.body.addLayout(files)

        nav = QHBoxLayout()
        nav.setSpacing(theme.SPACE)
        self.back_button = button(
            "Previous", "arrow-left", tooltip="Go back to the previous file (Left arrow)"
        )
        self.back_button.clicked.connect(self.previous)
        self.skip_button = button(
            "Skip", "skip", tooltip="Leave this file where it is (Right arrow or S)"
        )
        self.skip_button.clicked.connect(self.skip)
        nav.addWidget(self.back_button)
        nav.addStretch(1)
        nav.addWidget(self.skip_button)
        card.body.addLayout(nav)
        return card

    def _build_category_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(theme.SPACE)
        self.category_buttons: dict[Category, QPushButton] = {}
        for i, (category, key) in enumerate(zip(Category, CATEGORY_KEYS, strict=True)):
            widget = button(f"{key}   {category.label}", tooltip=f"Move to {category.value}")
            widget.setProperty("category", True)
            widget.clicked.connect(lambda _=False, c=category: self.categorize(c))
            grid.addWidget(widget, i // 4, i % 4)
            self.category_buttons[category] = widget
        return grid

    def _install_shortcuts(self) -> None:
        context = Qt.ShortcutContext.WidgetWithChildrenShortcut
        bindings: list[tuple[str, Callable[[], object]]] = [
            (key, partial(self._shortcut_categorize, category))
            for category, key in zip(Category, CATEGORY_KEYS, strict=True)
        ]
        bindings += [
            ("Right", self.skip),
            ("S", self.skip),
            ("Left", self.previous),
            ("O", self.open_current),
        ]
        for key, slot in bindings:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(context)
            shortcut.activated.connect(slot)

    # ------------------------------------------------------------------ state

    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        self.reload()
        self.setFocus()

    def reload(self) -> None:
        """Re-read the review folders and start from the first file."""
        self.output = self.context.output_dir()
        self.files = review_files(self.output, self.context.config) if self.output else []
        self.index = 0
        self._set_status("neutral", " ")
        self._show_current()

    @property
    def current(self) -> Path | None:
        return self.files[self.index] if 0 <= self.index < len(self.files) else None

    def _show_current(self) -> None:
        path = self.current
        if path is None or self.output is None:
            self._show_empty()
            return
        self.stack.setCurrentWidget(self.review_view)
        total = len(self.files)
        self.position_label.setText(f"File {self.index + 1} of {total}")
        self.position_bar.setRange(0, total)
        self.position_bar.setValue(self.index + 1)
        self.name_label.setText(path.name)
        here = current_category(path, self.output, self.context.config)
        self.reason_label.setText(review_reason(here))
        self._fill_info(path)
        self.preview.show_file(path, media_type_for(path.name, self.context.config))
        busy = self.context.is_busy
        for category, widget in self.category_buttons.items():
            widget.setEnabled(not busy and category != here)
        self.back_button.setEnabled(self.index > 0)

    def _show_empty(self) -> None:
        self.stack.setCurrentWidget(self.empty)
        self.position_label.setText("")
        self.preview.clear()
        if self.output is None:
            self.empty.set_content(
                "review",
                "No output folder",
                "Choose an output folder on the Organize page first.",
                "Go to Organize",
            )
        elif self.moved_count:
            self.empty.set_content(
                "check-circle",
                "All done",
                f"You filed {plural(self.moved_count, 'file')}. Each move is journaled, so "
                "Undo on the Organize page reverses the most recent one.",
            )
        else:
            config = self.context.config
            folders = " and ".join(
                f"'{config.folder_for(c)}'" for c in (Category.VIDEOS, Category.OTHER)
            )
            self.empty.set_content(
                "check-circle",
                "Nothing to review",
                f"There are no files in the {folders} folders. Files land there when "
                "their video orientation or file type can't be determined automatically.",
            )

    def _fill_info(self, path: Path) -> None:
        while self.info_form.rowCount():
            self.info_form.removeRow(0)
        for key, value in describe_file(path, self.output):
            self.info_form.addRow(label(key, "caption"), ElidedLabel(value))

    # ---------------------------------------------------------------- actions

    def _shortcut_categorize(self, category: Category) -> None:
        widget = self.category_buttons.get(category)
        if self.current is not None and widget is not None and widget.isEnabled():
            self.categorize(category)

    def categorize(self, category: Category) -> None:
        path = self.current
        if path is None or self.output is None or self.context.is_busy:
            return
        result, dest = move_one(path, category, self.output, self.context.config)
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
        self.context.libraryChanged.emit()

    def skip(self) -> None:
        if self.current is None:
            return
        if self.index + 1 >= len(self.files):
            self._set_status("neutral", "That was the last file.")
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
        self.status_label.setText(text)
        theme.set_props(self.status_label, tone=kind)
