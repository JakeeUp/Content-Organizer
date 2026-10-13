"""Main dashboard window: pick folders, preview, organize, undo, review, library stats.

All file work is delegated to the Qt-free core through :mod:`.workers`; this module only
wires widgets to tasks and renders their results (text comes from :mod:`.presenters`).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings, Qt, QThread, QTimer, QUrl
from PyQt6.QtGui import QAction, QCloseEvent, QCursor, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from content_organizer import __version__, logging_setup
from content_organizer import config as config_module
from content_organizer.categories import REVIEW_CATEGORIES
from content_organizer.config import (
    Config,
    ConfigError,
    build_config,
    load_config,
    load_defaults_dict,
)
from content_organizer.executor import (
    Mode,
    ProgressEvent,
    RunResult,
    UndoResult,
    list_journals,
    read_journal,
)
from content_organizer.ffmpeg_install import manual_install_hint
from content_organizer.gui import icons, theme
from content_organizer.gui.panels import (
    ActivityPanel,
    FfmpegBanner,
    FfmpegInstallDialog,
    LibraryPanel,
)
from content_organizer.gui.presenters import (
    FolderValidation,
    plural,
    run_summary,
    undo_summary,
    validate_folders,
)
from content_organizer.gui.preview_dialog import PreviewDialog
from content_organizer.gui.review_dialog import ReviewDialog
from content_organizer.gui.widgets import Card, FolderField, MonthlyChart, ToggleRow
from content_organizer.gui.widgets.monthly_chart import month_label
from content_organizer.gui.workers import (
    ExecuteTask,
    FfmpegInstallTask,
    PlanTask,
    StatsTask,
    Task,
    UndoTask,
    start_task,
)
from content_organizer.planner import Options, Plan, PlanError, check_paths
from content_organizer.probe import Prober, find_ffprobe
from content_organizer.stats import LibraryStats

log = logging.getLogger(__name__)

MIN_WIDTH, MIN_HEIGHT = 1100, 720
_DEBOUNCE_MS = 450
_ORGANIZE_TIP = (
    "Build a dry-run preview of every move; nothing changes until you confirm (Ctrl+Enter)"
)
_VIDEO_TIP_ON = "Reads each video's dimensions and rotation to tell vertical from horizontal."
_VIDEO_TIP_OFF = (
    "FFmpeg (ffprobe) was not found. Install it to detect vertical vs horizontal videos; "
    "until then untagged videos go to 'Videos' for review."
)


class MainWindow(QMainWindow):
    """The dashboard. Dependencies are injectable for tests (settings, config, prober)."""

    def __init__(
        self,
        settings: QSettings | None = None,
        config: Config | None = None,
        prober: Prober | None = None,
        ffprobe_locator: Callable[[], Path | None] = find_ffprobe,
    ) -> None:
        super().__init__()
        self._config_error: str | None = None
        self.settings = settings if settings is not None else QSettings()
        self.config = config if config is not None else self._load_config()
        self.prober = prober
        self._locate_ffprobe = ffprobe_locator
        self.ffprobe: Path | None = None
        self.stats: LibraryStats | None = None
        self.last_result: RunResult | None = None
        self._tasks: set[Task] = set()
        self._threads: set[QThread] = set()
        self._busy_task: Task | None = None
        self._library_task: StatsTask | None = None
        self._inbox_task: StatsTask | None = None
        self._run_mode = Mode.MOVE
        self._inbox_count: tuple[str, int] | None = None
        self._video_preference = True
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._refresh_background_stats)

        self.setWindowTitle(theme.APP_DISPLAY_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self._build_ui()
        self._build_menu()
        self._restore_settings()
        self._connect_signals()
        self.check_ffmpeg()  # fast: a PATH lookup plus a few stat calls
        self._on_paths_changed()
        self._debounce.stop()
        self._refresh_background_stats()
        if self._config_error:
            QTimer.singleShot(0, self._warn_config_error)

    # ================================================================== setup

    def _load_config(self) -> Config:
        try:
            return load_config()
        except ConfigError as exc:
            log.error("Invalid config, using defaults: %s", exc)
            self._config_error = str(exc)
            return build_config(load_defaults_dict())

    def _warn_config_error(self) -> None:
        QMessageBox.warning(
            self,
            "Configuration problem",
            "Your config file could not be loaded, so the defaults are used:\n\n"
            f"{self._config_error}",
        )

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 14, 24, 16)
        root.setSpacing(14)
        root.addLayout(self._build_header())
        self.banner = FfmpegBanner()
        root.addWidget(self.banner)

        content = QWidget()
        content.setObjectName("content")
        columns = QHBoxLayout(content)
        columns.setContentsMargins(4, 4, 4, 12)
        columns.setSpacing(18)
        self.activity = ActivityPanel()
        self.library = LibraryPanel()
        columns.addWidget(self._column(self._build_folders_card(), self._build_options_card()), 5)
        columns.addWidget(self._column(self.activity, self._build_chart_card()), 5)
        columns.addWidget(self._column(self.library), 6)
        scroll = QScrollArea()  # nothing is ever clipped on small screens
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        root.addLayout(self._build_action_bar())
        self.setCentralWidget(central)
        status = self.statusBar()
        if status is not None:
            status.setSizeGripEnabled(False)

    @staticmethod
    def _column(*cards: QWidget) -> QWidget:
        """A dashboard column; columns share width by stretch factor, not content."""
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        widget.setMinimumWidth(320)
        column = QVBoxLayout(widget)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(18)
        for i, card in enumerate(cards):
            column.addWidget(card, 1 if i == len(cards) - 1 else 0)
        return widget

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(44, 44))
        row.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(theme.APP_DISPLAY_NAME)
        title.setObjectName("appTitle")
        titles.addWidget(title)
        subtitle = QLabel(
            "Sort a messy media inbox into tidy folders. Preview every move first, undo any run."
        )
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(subtitle)
        row.addLayout(titles, 1)
        version = QLabel(f"v{__version__}")
        version.setObjectName("hint")
        row.addWidget(version, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _build_folders_card(self) -> Card:
        card = Card("Folders", "Drop folders onto the fields, paste a path or browse.")
        self.source_field = FolderField(
            "Source folder", "Your messy inbox", "Choose the folder to organize"
        )
        self.output_field = FolderField(
            "Output folder", "Organized destination", "Choose where organized files go"
        )
        card.body.addWidget(self.source_field)
        card.body.addWidget(self.output_field)
        return card

    def _build_options_card(self) -> Card:
        card = Card("Options")
        self.video_option = ToggleRow(
            "Video analysis", "Detect vertical / horizontal videos with ffprobe", checked=True
        )
        self.date_option = ToggleRow(
            "Date folders", "Sort videos into Year / Month folders", checked=True
        )
        self.clean_option = ToggleRow(
            "Clean names", "Remove tags like _vert or _music from file names"
        )
        self.copy_option = ToggleRow(
            "Copy instead of move", "Leave the originals in the source folder"
        )
        self.date_option.setToolTip(
            "Videos go to e.g. VerticalVideos/2024/03 - March, using the recording date "
            "(or the file's modified date)."
        )
        self.clean_option.setToolTip("beach_vert.mp4 becomes beach.mp4")
        self.copy_option.setToolTip("Safer for a first try; uses more disk space.")
        for row in self._option_rows():
            card.body.addWidget(row)
        card.body.addStretch(1)
        card.body.addWidget(self._safety_note())
        return card

    def _option_rows(self) -> tuple[ToggleRow, ...]:
        return (self.video_option, self.date_option, self.clean_option, self.copy_option)

    @staticmethod
    def _safety_note() -> QFrame:
        note = QFrame()
        note.setObjectName("chip")
        row = QHBoxLayout(note)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        badge = QLabel()
        badge.setPixmap(icons.icon("check", theme.SUCCESS).pixmap(18, 18))
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        text = QLabel(
            "Nothing moves until you confirm the preview. Files are never overwritten, "
            "and every run is journaled so it can be undone."
        )
        text.setObjectName("hint")
        text.setWordWrap(True)
        row.addWidget(text, 1)
        return note

    def _build_chart_card(self) -> Card:
        card = Card(
            "Monthly distribution",
            "Files per month in the output library. Click a point to open that month's folder.",
        )
        self.chart = MonthlyChart()
        self.chart.setToolTip("Use Left/Right to pick a month and Enter to open it")
        card.body.addWidget(self.chart, 1)
        return card

    def _build_action_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        self.organize_button = QPushButton(icons.icon("play", "#FFFFFF"), "Preview && Organize…")
        self.organize_button.setObjectName("primary")
        self.organize_button.setToolTip(_ORGANIZE_TIP)
        self.review_button = QPushButton(icons.icon("review", "#1F1300"), "Review files…")
        self.review_button.setObjectName("accentAmber")
        self.review_button.setToolTip(
            "File videos with unknown orientation and unrecognised files by hand (Ctrl+R)"
        )
        self.undo_button = QPushButton(icons.icon("undo"), "Undo last run")
        self.undo_button.setToolTip("Put the files from the most recent run back (Ctrl+Z)")
        self.open_output_button = QPushButton(icons.icon("open"), "Open output folder")
        self.open_output_button.setToolTip("Show the output folder in your file manager")
        row.addStretch(1)
        for button in (
            self.organize_button,
            self.review_button,
            self.undo_button,
            self.open_output_button,
        ):
            button.setMinimumHeight(44)
            row.addWidget(button)
        row.addStretch(1)
        return row

    def _build_menu(self) -> None:
        bar = self.menuBar()
        assert bar is not None
        file_menu = bar.addMenu("&File")
        run_menu = bar.addMenu("&Run")
        help_menu = bar.addMenu("&Help")
        assert file_menu is not None and run_menu is not None and help_menu is not None
        self._add_action(file_menu, "&Open Output Folder", self.open_output_folder, "Ctrl+Shift+O")
        self._add_action(file_menu, "Open &Config Folder", self.open_config_folder)
        file_menu.addSeparator()
        self._add_action(file_menu, "&Quit", self.close, QKeySequence.StandardKey.Quit)

        self._add_action(run_menu, "&Preview && Organize…", self.start_organize, "Ctrl+Return")
        self._add_action(run_menu, "&Review Files…", self.open_review, "Ctrl+R")
        self._add_action(run_menu, "&Undo Last Run", self.confirm_undo, "Ctrl+Z")
        self._add_action(run_menu, "Re&fresh Library", self.refresh_library, "F5")
        self._add_action(run_menu, "&Cancel", self.cancel_current, "Esc")

        self._add_action(help_menu, "Install &FFmpeg…", self.install_ffmpeg)
        self._add_action(help_menu, "Open &Log Folder", self.open_log_folder)
        help_menu.addSeparator()
        self._add_action(help_menu, f"&About {theme.APP_DISPLAY_NAME}", self.show_about)

    def _add_action(
        self,
        menu: QMenu,
        text: str,
        slot: Callable[[], object],
        shortcut: str | QKeySequence.StandardKey | None = None,
    ) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False: slot())
        menu.addAction(action)
        return action

    def _connect_signals(self) -> None:
        self.source_field.pathChanged.connect(self._on_paths_changed)
        self.output_field.pathChanged.connect(self._on_paths_changed)
        for row in self._option_rows():
            row.switch.toggled.connect(self._save_options)
        self.organize_button.clicked.connect(self.start_organize)
        self.review_button.clicked.connect(self.open_review)
        self.undo_button.clicked.connect(self.confirm_undo)
        self.open_output_button.clicked.connect(self.open_output_folder)
        self.library.refresh_button.clicked.connect(self.refresh_library)
        self.activity.cancelRequested.connect(self.cancel_current)
        self.activity.reviewRequested.connect(self.open_review)
        self.chart.monthClicked.connect(self.open_month)
        self.banner.installRequested.connect(self.install_ffmpeg)
        self.banner.dismissed.connect(self._dismiss_banner)

    # =============================================================== settings

    def _restore_settings(self) -> None:
        s = self.settings
        self.source_field.set_text(str(s.value("paths/source", "", type=str)))
        self.output_field.set_text(str(s.value("paths/output", "", type=str)))
        self._video_preference = bool(s.value("options/video", True, type=bool))
        self.video_option.setChecked(self._video_preference)
        self.date_option.setChecked(bool(s.value("options/dateFolders", True, type=bool)))
        self.clean_option.setChecked(bool(s.value("options/cleanNames", False, type=bool)))
        self.copy_option.setChecked(bool(s.value("options/copy", False, type=bool)))
        geometry = s.value("window/geometry", QByteArray(), type=QByteArray)
        if not isinstance(geometry, QByteArray) or not self.restoreGeometry(geometry):
            self._apply_default_geometry()

    def _apply_default_geometry(self) -> None:
        screen = self.screen()
        if screen is None:
            self.resize(1440, 900)
            return
        area = screen.availableGeometry()
        self.resize(
            max(MIN_WIDTH, min(1480, area.width() - 80)),
            max(MIN_HEIGHT, min(940, area.height() - 80)),
        )
        frame = self.frameGeometry()
        frame.moveCenter(area.center())
        self.move(frame.topLeft())

    def _save_options(self) -> None:
        if self.video_option.isEnabled():  # a disabled (no ffprobe) switch is not a choice
            self._video_preference = self.video_option.isChecked()
        s = self.settings
        s.setValue("options/video", self._video_preference)
        s.setValue("options/dateFolders", self.date_option.isChecked())
        s.setValue("options/cleanNames", self.clean_option.isChecked())
        s.setValue("options/copy", self.copy_option.isChecked())

    def _save_paths(self) -> None:
        self.settings.setValue("paths/source", self.source_field.text())
        self.settings.setValue("paths/output", self.output_field.text())

    # ================================================================ options

    def options(self) -> Options:
        """The current toggles as core :class:`Options`."""
        return Options(
            date_folders=self.date_option.isChecked(),
            clean_names=self.clean_option.isChecked(),
            probe=self.ffprobe is not None and self.video_option.isChecked(),
        )

    def mode(self) -> Mode:
        return Mode.COPY if self.copy_option.isChecked() else Mode.MOVE

    def source_path(self) -> Path:
        return Path(self.source_field.text()).expanduser()

    def output_path(self) -> Path:
        return Path(self.output_field.text()).expanduser()

    # ============================================================ validation

    def validation(self) -> FolderValidation:
        return validate_folders(self.source_field.text(), self.output_field.text())

    def _on_paths_changed(self, *_args: object) -> None:
        result = self.validation()
        source_message = result.source.message
        if result.source.kind == "ok" and self._inbox_count is not None:
            text, count = self._inbox_count
            if text == self.source_field.text():
                source_message = f"Ready · {plural(count, 'file')} to sort."
        self.source_field.set_status(result.source.kind, source_message)
        self.output_field.set_status(result.output.kind, result.output.message)
        self._save_paths()
        self._update_actions()
        self._debounce.start()

    def _update_actions(self) -> None:
        busy = self.is_busy
        validation = self.validation()
        output_exists = validation.output.usable and self.output_path().is_dir()
        self.organize_button.setEnabled(not busy and validation.ready)
        self.organize_button.setToolTip(
            _ORGANIZE_TIP if validation.ready else "Choose a valid source and output folder first"
        )
        self.review_button.setEnabled(not busy and output_exists)
        self.undo_button.setEnabled(not busy and output_exists and self._has_journal())
        self.open_output_button.setEnabled(output_exists)
        self.library.refresh_button.setEnabled(output_exists)
        for widget in (self.source_field, self.output_field, *self._option_rows()[1:]):
            widget.setEnabled(not busy)
        self.video_option.setEnabled(not busy and self.ffprobe is not None)

    def _has_journal(self) -> bool:
        try:
            return bool(list_journals(self.output_path()))
        except OSError:
            return False

    # ======================================================== task plumbing

    def _launch(self, task: Task, *, busy: bool = False) -> None:
        self._tasks.add(task)
        task.done.connect(lambda t=task: self._task_done(t))
        if busy:
            self._busy_task = task
            self.activity.set_busy(True)
            self._update_actions()
        thread = start_task(task, self)
        self._threads.add(thread)
        thread.finished.connect(lambda th=thread: self._threads.discard(th))

    def _task_done(self, task: Task) -> None:
        self._tasks.discard(task)
        if task is self._busy_task:
            self._busy_task = None
            self.activity.set_busy(False)
            self._update_actions()

    @property
    def is_busy(self) -> bool:
        return self._busy_task is not None

    def cancel_current(self) -> None:
        task = self._busy_task
        if task is not None and not task.is_cancelled:
            task.cancel()
            self.activity.show_cancelling()

    def shutdown(self, timeout_ms: int = 10_000) -> None:
        """Cancel every background task and wait for its thread (used on close)."""
        self._debounce.stop()
        for task in list(self._tasks):
            task.cancel()
        for thread in list(self._threads):
            try:
                thread.quit()
                thread.wait(timeout_ms)
            except RuntimeError:  # already deleted by deleteLater
                pass
        self._threads.clear()

    def _show_error(self, title: str, message: str) -> None:
        self.activity.set_status(title, message, "error")
        QMessageBox.critical(self, title, message)

    def _status_message(self, text: str, timeout: int = 6000) -> None:
        statusbar = self.statusBar()
        if statusbar is not None:
            statusbar.showMessage(text, timeout)

    # =============================================================== organize

    def start_organize(self) -> None:
        """Step 1: build a dry-run plan in the background, then show the preview."""
        if self.is_busy:
            return
        if not self.validation().ready:
            self._on_paths_changed()
            return
        try:
            source, output = check_paths(self.source_path(), self.output_path())
        except PlanError as exc:
            self._show_error("Can't organize", str(exc))
            return
        self._run_mode = self.mode()
        options = self.options()
        prober = self.prober if options.probe else None
        task = PlanTask(source, output, options, self.config, prober)
        task.progressed.connect(self._on_plan_progress)
        task.succeeded.connect(self._on_plan_ready)
        task.failed.connect(lambda message: self._show_error("Preview failed", message))
        analysing = " and analysing videos" if options.probe else ""
        self.activity.set_status(
            "Building preview…", f"Scanning files{analysing}. No files are changed in this step."
        )
        self.activity.set_indeterminate()
        self.activity.set_current("")
        self._launch(task, busy=True)

    def _on_plan_progress(self, done: int, total: int, path: str) -> None:
        self.activity.set_progress(done, total)
        self.activity.set_current(f"Checking {Path(path).name}")

    def _on_plan_ready(self, plan: Plan) -> None:
        self.activity.reset_progress()
        self.activity.set_current("")
        if plan.cancelled:
            self.activity.set_status("Preview cancelled", "No files were changed.")
            return
        # Open the dialog after the plan task has fully released the busy state.
        QTimer.singleShot(0, lambda: self._show_preview(plan))

    def _show_preview(self, plan: Plan) -> None:
        self.activity.set_status("Waiting for confirmation", "Review the planned moves.")
        dialog = self.create_preview_dialog(plan)
        if dialog.exec() == QDialog.DialogCode.Accepted and plan.moves:
            self.start_execute(plan)
        else:
            self.activity.set_status("Ready", "Preview closed. No files were changed.")

    def create_preview_dialog(self, plan: Plan) -> PreviewDialog:
        return PreviewDialog(plan, self._run_mode, self)

    def start_execute(self, plan: Plan, mode: Mode | None = None) -> ExecuteTask:
        """Step 2: carry out a confirmed plan with progress and cancel."""
        self._run_mode = mode or self._run_mode
        task = ExecuteTask(plan, self._run_mode)
        task.progressed.connect(self._on_execute_progress)
        task.succeeded.connect(self._on_execute_done)
        task.failed.connect(lambda message: self._show_error("Organizing failed", message))
        task.done.connect(self._after_library_change)
        self.activity.set_status(f"{self._verb()}…", f"{plural(len(plan), 'file')} to process.")
        self.activity.set_progress(0, len(plan))
        self._launch(task, busy=True)
        return task

    def _verb(self) -> str:
        return "Copying" if self._run_mode is Mode.COPY else "Organizing"

    def _on_execute_progress(self, event: ProgressEvent) -> None:
        percent = round(event.done / max(1, event.total) * 100)
        self.activity.set_progress(event.done, event.total)
        self.activity.set_status(
            f"{self._verb()}… {percent}%", f"{event.done:,} of {event.total:,} files"
        )
        self.activity.set_current(f"{event.move.src.name}  →  {event.move.category.label}")

    def _on_execute_done(self, result: RunResult) -> None:
        self.last_result = result
        self.activity.set_current("")
        self.activity.show_summary(run_summary(result, self._run_mode))
        self.activity.offer_review(sum(result.stats.per_category[c] for c in REVIEW_CATEGORIES))

    def _after_library_change(self) -> None:
        self._update_actions()
        self.refresh_library()

    # =================================================================== undo

    def confirm_undo(self) -> None:
        if self.is_busy or not self._has_journal():
            return
        header, ops = read_journal(list_journals(self.output_path())[-1])
        action = "deleted" if header.get("mode") == Mode.COPY.value else "moved back"
        started = str(header.get("started", ""))[:19].replace("T", " ")
        answer = QMessageBox.question(
            self,
            "Undo last run",
            f"Undo the run from {started}?\n\n"
            f"{plural(len(ops), 'file')} will be {action}. Nothing is overwritten.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.start_undo()

    def start_undo(self) -> UndoTask:
        task = UndoTask(self.output_path())
        task.progressed.connect(self.activity.set_progress)
        task.succeeded.connect(self._on_undo_done)
        task.nothing_to_undo.connect(lambda msg: self.activity.set_status("Nothing to undo", msg))
        task.failed.connect(lambda message: self._show_error("Undo failed", message))
        task.done.connect(self._after_library_change)
        self.activity.set_status("Undoing last run…")
        self.activity.set_indeterminate()
        self._launch(task, busy=True)
        return task

    def _on_undo_done(self, result: UndoResult) -> None:
        self.activity.reset_progress(100 if result.ok else 0)
        self.activity.show_summary(undo_summary(result))

    # ================================================================= review

    def open_review(self) -> None:
        if self.is_busy:
            return
        output = self.output_path()
        if not output.is_dir():
            QMessageBox.information(self, "Review files", "Choose an existing output folder first.")
            return
        dialog = ReviewDialog(output, self.config, self)
        dialog.exec()
        if dialog.moved_count:
            self.activity.offer_review(0)
            self._status_message(f"Filed {plural(dialog.moved_count, 'file')}.")
            self._after_library_change()

    # ============================================================== dashboard

    def _refresh_background_stats(self) -> None:
        self._refresh_inbox_count()
        self.refresh_library()

    def _refresh_inbox_count(self) -> None:
        if self._inbox_task is not None:
            self._inbox_task.cancel()
            self._inbox_task = None
        if self.validation().source.kind != "ok":
            return
        text = self.source_field.text()
        task = StatsTask(self.source_path(), self.config)
        task.succeeded.connect(lambda stats, t=text: self._on_inbox_stats(t, stats))
        self._inbox_task = task
        self._launch(task)

    def _on_inbox_stats(self, text: str, stats: LibraryStats) -> None:
        if stats.cancelled:
            return
        self._inbox_count = (text, stats.total)
        if text == self.source_field.text():
            self._on_paths_changed()
            self._debounce.stop()

    def refresh_library(self) -> None:
        """Rescan the output folder in the background and redraw the dashboard."""
        if self._library_task is not None:
            self._library_task.cancel()
            self._library_task = None
        output = self.output_path()
        if not self.validation().output.usable or not output.is_dir():
            self._clear_dashboard()
            return
        self.library.show_scanning(output.name or str(output))
        task = StatsTask(output, self.config)
        task.succeeded.connect(self._apply_stats)
        task.failed.connect(lambda message: self.library.clear(f"Scan failed: {message}"))
        self._library_task = task
        self._launch(task)

    def _clear_dashboard(self) -> None:
        self.stats = None
        self.library.clear()
        self.chart.set_series([], "Organized files will appear here by month.")

    def _apply_stats(self, stats: LibraryStats) -> None:
        if stats.cancelled:
            return
        self.stats = stats
        self.library.show_stats(stats)
        self.chart.set_series(
            stats.month_series(), "This folder is empty. Organized files will appear by month."
        )

    def folders_for_month(self, year: int, month: int) -> list[Path]:
        if self.stats is None:
            return []
        return list(self.stats.month_folders.get((year, month), []))

    def open_month(self, year: int, month: int) -> None:
        """Open the clicked month's folder; offer a picker when several categories have one."""
        folders = self.folders_for_month(year, month)
        if not folders:
            self._status_message(
                f"No date folders for {month_label((year, month))}: these files are counted by "
                "their modified date. Turn on Date folders to file videos by month.",
                8000,
            )
        elif len(folders) == 1:
            self._open_path(folders[0])
        else:
            self._month_menu(folders).popup(QCursor.pos())

    def _month_menu(self, folders: list[Path]) -> QMenu:
        menu = QMenu(self)
        root = self.stats.root if self.stats else None
        for folder in folders:
            label = str(folder.relative_to(root)) if root else str(folder)
            action = QAction(icons.icon("folder"), label, menu)
            action.triggered.connect(lambda _=False, f=folder: self._open_path(f))
            menu.addAction(action)
        menu.addSeparator()
        open_all = QAction("Open all", menu)
        open_all.triggered.connect(lambda: [self._open_path(f) for f in folders])
        menu.addAction(open_all)
        return menu

    # =============================================================== open/help

    def _open_path(self, path: Path) -> bool:
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if not ok:
            QMessageBox.warning(self, "Could not open", f"Could not open:\n{path}")
        return ok

    def open_output_folder(self) -> None:
        if self.output_path().is_dir():
            self._open_path(self.output_path())

    def open_log_folder(self) -> None:
        folder = logging_setup.log_file_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        self._open_path(folder)

    def open_config_folder(self) -> None:
        folder = config_module.default_config_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        self._open_path(folder)

    def show_about(self) -> None:
        ffprobe = str(self.ffprobe) if self.ffprobe else "not found"
        QMessageBox.about(
            self,
            f"About {theme.APP_DISPLAY_NAME}",
            f"<h3>{theme.APP_DISPLAY_NAME} {__version__}</h3>"
            "<p>Sorts a creator's media inbox into vertical and horizontal videos, audio, "
            "images and projects, with a dry-run preview and undo.</p>"
            f"<p><b>ffprobe:</b> {ffprobe}<br>"
            f"<b>Log file:</b> {logging_setup.log_file_path()}</p>"
            "<p>MIT License.</p>",
        )

    # ================================================================= ffmpeg

    def check_ffmpeg(self) -> None:
        self.ffprobe = self._locate_ffprobe()
        self._apply_ffprobe_state()

    def _apply_ffprobe_state(self) -> None:
        available = self.ffprobe is not None
        self.video_option.setEnabled(available and not self.is_busy)
        self.video_option.setChecked(available and self._video_preference)
        self.video_option.setToolTip(_VIDEO_TIP_ON if available else _VIDEO_TIP_OFF)
        dismissed = bool(self.settings.value("ffmpeg/bannerDismissed", False, type=bool))
        self.banner.setVisible(not available and not dismissed)

    def _dismiss_banner(self) -> None:
        self.settings.setValue("ffmpeg/bannerDismissed", True)
        self.banner.hide()

    def install_ffmpeg(self) -> None:
        if self.ffprobe is not None:
            QMessageBox.information(self, "FFmpeg", f"FFmpeg is already available:\n{self.ffprobe}")
        elif sys.platform != "win32":
            QMessageBox.information(self, "Install FFmpeg", manual_install_hint())
        elif not any(isinstance(t, FfmpegInstallTask) for t in self._tasks):
            self.start_ffmpeg_install()

    def start_ffmpeg_install(self, **install_kwargs: object) -> FfmpegInstallTask:
        """Download FFmpeg in a worker with a real progress dialog and a working Cancel."""
        task = FfmpegInstallTask(**install_kwargs)
        dialog = FfmpegInstallDialog(self)
        dialog.canceled.connect(task.cancel)
        task.progressed.connect(dialog.show_progress)
        task.succeeded.connect(self._on_install_ok)
        task.cancelled.connect(lambda: self._status_message("FFmpeg download cancelled."))
        task.unsupported.connect(lambda msg: QMessageBox.information(self, "Install FFmpeg", msg))
        task.failed.connect(lambda msg: QMessageBox.critical(self, "FFmpeg install failed", msg))
        task.done.connect(dialog.close)
        task.done.connect(dialog.deleteLater)
        dialog.show()
        self._launch(task)
        return task

    def _on_install_ok(self, path: Path) -> None:
        self.ffprobe = self._locate_ffprobe() or path
        self._apply_ffprobe_state()
        QMessageBox.information(
            self, "FFmpeg installed", f"Video analysis is now available.\n\nffprobe: {self.ffprobe}"
        )

    # ================================================================== close

    def confirm_quit_during_run(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Quit while running?",
            "A run is in progress. Stop after the current file and quit?\n"
            "Files already processed stay where they are and can be undone.",
        )
        return answer == QMessageBox.StandardButton.Yes

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if self.is_busy and not self.confirm_quit_during_run():
            if event is not None:
                event.ignore()
            return
        self.settings.setValue("window/geometry", self.saveGeometry())
        self._save_paths()
        self._save_options()
        self.settings.sync()
        self.shutdown()
        super().closeEvent(event)
