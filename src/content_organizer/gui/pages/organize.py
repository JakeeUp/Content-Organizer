"""Organize: pick folders and options, preview the plan, run it, undo the latest run."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from content_organizer.categories import REVIEW_CATEGORIES
from content_organizer.executor import Mode, ProgressEvent, RunResult, UndoResult
from content_organizer.gui import icons, theme
from content_organizer.gui.context import AppContext
from content_organizer.gui.pages.base import Page
from content_organizer.gui.presenters import (
    FolderValidation,
    RunSummary,
    plural,
    recent_runs,
    run_summary,
    undo_summary,
    validate_folders,
)
from content_organizer.gui.preview_dialog import PreviewDialog
from content_organizer.gui.widgets import (
    Card,
    ElidedLabel,
    FolderField,
    Notice,
    RecentRuns,
    ToggleRow,
    button,
    label,
)
from content_organizer.gui.workers import ExecuteTask, PlanTask, StatsTask, UndoTask
from content_organizer.planner import Plan, PlanError, check_paths
from content_organizer.stats import LibraryStats

_DEBOUNCE_MS = 450
_ORGANIZE_TIP = (
    "Build a dry-run preview of every move; nothing changes until you confirm (Ctrl+Enter)"
)
_VIDEO_TIP_OFF = (
    "FFmpeg (ffprobe) was not found. Install it to detect vertical vs horizontal videos; "
    "until then untagged videos go to 'Videos' for review."
)

#: (option key, title, description, tooltip)
_OPTIONS = (
    (
        "video",
        "Video analysis",
        "Detect vertical / horizontal videos with ffprobe",
        "Reads each video's dimensions and rotation to tell vertical from horizontal.",
    ),
    (
        "dateFolders",
        "Date folders",
        "Sort videos into Year / Month folders",
        "Videos go to e.g. VerticalVideos/2024/03 - March, using the recording date "
        "(or the file's modified date).",
    ),
    (
        "cleanNames",
        "Clean names",
        "Remove tags like _vert or _music from file names",
        "beach_vert.mp4 becomes beach.mp4",
    ),
    (
        "copy",
        "Copy instead of move",
        "Leave the originals in the source folder",
        "Safer for a first try; uses more disk space.",
    ),
)


class ActivityCard(Card):
    """Status, progress, current file, Cancel, and the last run's summary and details."""

    cancelRequested = pyqtSignal()
    reviewRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Activity", parent=parent)
        self.status_title = label("Ready", "h2")
        self.body.addWidget(self.status_title)
        self.detail = label(
            "Choose a source and an output folder, then preview the planned moves.",
            "muted",
            wrap=True,
        )
        self.body.addWidget(self.detail)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setAccessibleName("Progress")
        self.body.addWidget(self.progress_bar)
        self.current_file = ElidedLabel(" ")
        self.current_file.setProperty("role", "caption")
        self.body.addWidget(self.current_file)

        row = QHBoxLayout()
        row.setSpacing(theme.SPACE)
        self.cancel_button = button(
            "Cancel",
            "cancel",
            variant="danger",
            tooltip="Stop after the current file (Esc). Finished files stay done.",
        )
        self.cancel_button.clicked.connect(self.cancelRequested)
        row.addWidget(self.cancel_button)
        self.review_link = button("", variant="link", tooltip="Files that need a decision")
        self.review_link.clicked.connect(self.reviewRequested)
        row.addWidget(self.review_link)
        row.addStretch(1)
        self.details_button = button("Show details", variant="link")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        row.addWidget(self.details_button)
        self.body.addLayout(row)
        for widget in (self.cancel_button, self.review_link, self.details_button):
            widget.hide()

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        self.details.setAccessibleName("Run details")
        self.details.hide()
        self.body.addWidget(self.details)
        self.body.addStretch(1)

    def set_status(self, title: str, detail: str = "", kind: str = "") -> None:
        self.status_title.setText(title)
        self.detail.setText(detail)
        theme.set_props(self.status_title, tone=kind or None)

    def set_busy(self, busy: bool) -> None:
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        if busy:
            self.review_link.hide()
            self.details_button.hide()
            self.details_button.setChecked(False)

    def show_cancelling(self) -> None:
        self.cancel_button.setEnabled(False)
        self.detail.setText("Cancelling after the current file…")

    def set_progress(self, done: int, total: int) -> None:
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(done)

    def set_indeterminate(self) -> None:
        self.progress_bar.setRange(0, 0)

    def reset_progress(self, value: int = 0) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(value)

    def set_current(self, text: str) -> None:
        self.current_file.setText(text or " ")

    def show_summary(self, summary: RunSummary) -> None:
        self.set_status(summary.title, summary.line, summary.kind)
        self.details.setPlainText(summary.details)
        self.details_button.setVisible(bool(summary.details))
        self.details_button.setChecked(summary.kind == "error" and bool(summary.details))

    def offer_review(self, count: int) -> None:
        self.review_link.setText(f"Review {plural(count, 'file')} now")
        self.review_link.setVisible(count > 0)

    def _toggle_details(self, shown: bool) -> None:
        self.details.setVisible(shown)
        self.details_button.setText("Hide details" if shown else "Show details")


class OrganizePage(Page):
    reviewRequested = pyqtSignal()
    installFfmpegRequested = pyqtSignal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(
            "Organize",
            "Sort a messy media inbox into tidy folders. Preview every move, undo any run.",
            parent,
        )
        self.context = context
        self.last_result: RunResult | None = None
        self._run_mode = Mode.MOVE
        self._inbox_task: StatsTask | None = None
        self._inbox_count: tuple[str, int] | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._refresh_inbox_count)

        self.ffmpeg_notice = self._build_notice()
        self.body.addWidget(self.ffmpeg_notice)
        columns = QHBoxLayout()
        columns.setSpacing(2 * theme.SPACE)
        columns.addLayout(self._build_setup_column(), 1)
        columns.addLayout(self._build_status_column(), 1)
        self.body.addLayout(columns)
        self.body.addStretch(1)
        self.outer.addWidget(self._build_footer())

        settings = context.settings
        self.source_field.set_text(str(settings.value("paths/source", "", type=str)))
        self.output_field.set_text(str(settings.value("paths/output", "", type=str)))
        self._connect()
        self._on_paths_changed()
        self._debounce.stop()
        self._refresh_inbox_count()
        self._apply_ffprobe_state()
        self.refresh_recent_runs()

    # ------------------------------------------------------------------ build

    def _build_notice(self) -> Notice:
        notice = Notice(
            "FFmpeg is not installed, so video orientation can't be detected. "
            "Untagged videos will be filed under 'Videos' for review."
        )
        self.install_button = button("Install FFmpeg", "download")
        self.install_button.clicked.connect(self.installFfmpegRequested)
        notice.add_button(self.install_button)
        self.dismiss_button = button(
            "Not now",
            variant="ghost",
            tooltip="Hide this message. You can install FFmpeg later from Settings.",
        )
        self.dismiss_button.clicked.connect(self._dismiss_notice)
        notice.add_button(self.dismiss_button)
        notice.hide()
        return notice

    def _build_setup_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(2 * theme.SPACE)
        self.source_field = FolderField(
            "Source folder", "Your messy inbox", "Choose the folder to organize", step=1
        )
        self.output_field = FolderField(
            "Output folder", "Organized destination", "Choose where organized files go", step=2
        )
        column.addWidget(self.source_field)
        column.addWidget(self.output_field)

        card = Card("Options", "Saved automatically.")
        self.option_rows: dict[str, ToggleRow] = {}
        for key, title, description, tooltip in _OPTIONS:
            row = ToggleRow(title, description, checked=self.context.option(key))
            row.setToolTip(tooltip)
            card.body.addWidget(row)
            self.option_rows[key] = row
        column.addWidget(card)
        column.addStretch(1)
        return column

    def _build_status_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(2 * theme.SPACE)
        self.activity = ActivityCard()
        column.addWidget(self.activity)
        self.recent = RecentRuns()
        column.addWidget(self.recent, 1)
        return column

    def _build_footer(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("footerBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 12, 12, 12)
        row.setSpacing(theme.SPACE)
        shield = label()
        icons.themed(shield, "check-circle", "success", 18)
        row.addWidget(shield, 0, Qt.AlignmentFlag.AlignVCenter)
        self.safety_label = label(
            "Nothing moves until you confirm the preview. Files are never overwritten, "
            "and every run can be undone.",
            "muted",
            wrap=True,
        )
        row.addWidget(self.safety_label, 1)
        self.organize_button = button(
            "Preview && organize…", "play", variant="primary", size="lg", tooltip=_ORGANIZE_TIP
        )
        row.addWidget(self.organize_button)
        return bar

    def _connect(self) -> None:
        self.source_field.pathChanged.connect(self._on_paths_changed)
        self.output_field.pathChanged.connect(self._on_paths_changed)
        for key, row in self.option_rows.items():
            row.switch.toggled.connect(lambda on, k=key: self._on_option_toggled(k, on))
        self.organize_button.clicked.connect(self.start_organize)
        self.activity.cancelRequested.connect(self.cancel_current)
        self.activity.reviewRequested.connect(self.reviewRequested)
        self.recent.undoRequested.connect(self.confirm_undo)
        self.context.busyChanged.connect(self._on_busy_changed)
        self.context.ffprobeChanged.connect(self._apply_ffprobe_state)
        self.context.libraryChanged.connect(self.refresh_recent_runs)
        self.context.outputChanged.connect(self.refresh_recent_runs)

    # -------------------------------------------------------------- folders

    def validation(self) -> FolderValidation:
        return validate_folders(self.source_field.text(), self.output_field.text())

    def source_path(self) -> Path:
        return Path(self.source_field.text()).expanduser()

    def output_path(self) -> Path:
        return Path(self.output_field.text()).expanduser()

    def _on_paths_changed(self, *_args: object) -> None:
        result = self.validation()
        source_message = result.source.message
        if result.source.kind == "ok" and self._inbox_count is not None:
            text, count = self._inbox_count
            if text == self.source_field.text():
                source_message = f"Ready · {plural(count, 'file')} to sort."
        self.source_field.set_status(result.source.kind, source_message)
        self.output_field.set_status(result.output.kind, result.output.message)
        self.context.set_folders(self.source_field.text(), self.output_field.text())
        self.update_actions()
        self._debounce.start()

    def update_actions(self) -> None:
        busy = self.context.is_busy
        ready = self.validation().ready
        self.organize_button.setEnabled(not busy and ready)
        self.organize_button.setToolTip(
            _ORGANIZE_TIP if ready else "Choose a valid source and output folder first"
        )
        self.recent.undo_link.setEnabled(not busy)
        for widget in (self.source_field, self.output_field):
            widget.setEnabled(not busy)
        for key, row in self.option_rows.items():
            row.setEnabled(not busy and (key != "video" or self.context.ffprobe is not None))

    def _on_busy_changed(self, busy: bool) -> None:
        self.activity.set_busy(busy)
        self.update_actions()

    # ---------------------------------------------------------------- options

    def _on_option_toggled(self, key: str, on: bool) -> None:
        # A disabled video switch (no ffprobe) shows "off" but is not the user's choice.
        if key != "video" or self.context.ffprobe is not None:
            self.context.set_option(key, on)

    def _apply_ffprobe_state(self) -> None:
        available = self.context.ffprobe is not None
        video = self.option_rows["video"]
        video.setChecked(available and self.context.option("video"))
        video.setToolTip(_OPTIONS[0][3] if available else _VIDEO_TIP_OFF)
        dismissed = bool(self.context.settings.value("ffmpeg/bannerDismissed", False, type=bool))
        self.ffmpeg_notice.setVisible(not available and not dismissed)
        self.update_actions()

    def _dismiss_notice(self) -> None:
        self.context.settings.setValue("ffmpeg/bannerDismissed", True)
        self.ffmpeg_notice.hide()

    # ------------------------------------------------------------ inbox count

    def _refresh_inbox_count(self) -> None:
        if self._inbox_task is not None:
            self._inbox_task.cancel()
            self._inbox_task = None
        if self.validation().source.kind != "ok":
            return
        text = self.source_field.text()
        task = StatsTask(self.source_path(), self.context.config)
        task.succeeded.connect(lambda stats, t=text: self._on_inbox_stats(t, stats))
        self._inbox_task = task
        self.context.launch(task)

    def _on_inbox_stats(self, text: str, stats: LibraryStats) -> None:
        if stats.cancelled:
            return
        self._inbox_count = (text, stats.total)
        if text == self.source_field.text():
            self._on_paths_changed()
            self._debounce.stop()

    # --------------------------------------------------------------- organize

    def _show_error(self, title: str, message: str) -> None:
        self.activity.set_status(title, message, "error")
        QMessageBox.critical(self, title, message)

    def start_organize(self) -> None:
        """Step 1: build a dry-run plan in the background, then show the preview."""
        if self.context.is_busy:
            return
        if not self.validation().ready:
            self._on_paths_changed()
            return
        try:
            source, output = check_paths(self.source_path(), self.output_path())
        except PlanError as exc:
            self._show_error("Can't organize", str(exc))
            return
        self._run_mode = self.context.mode()
        options = self.context.options()
        prober = self.context.prober if options.probe else None
        task = PlanTask(source, output, options, self.context.config, prober)
        task.progressed.connect(self._on_plan_progress)
        task.succeeded.connect(self._on_plan_ready)
        task.failed.connect(lambda message: self._show_error("Preview failed", message))
        analysing = " and analysing videos" if options.probe else ""
        self.activity.set_status(
            "Building preview…", f"Scanning files{analysing}. No files are changed in this step."
        )
        self.activity.set_indeterminate()
        self.activity.set_current("")
        self.context.launch(task, busy=True)

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
        task.done.connect(self.context.libraryChanged)
        self.activity.set_status(f"{self._verb()}…", f"{plural(len(plan), 'file')} to process.")
        self.activity.set_progress(0, len(plan))
        self.context.launch(task, busy=True)
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

    def cancel_current(self) -> None:
        if self.context.cancel_busy():
            self.activity.show_cancelling()

    # ------------------------------------------------------------------- undo

    def refresh_recent_runs(self) -> None:
        output = self.context.output_dir()
        if output is None:
            self.recent.set_records([], "Choose an output folder to see its runs.")
        else:
            self.recent.set_records(recent_runs(output))

    def confirm_undo(self) -> None:
        if self.context.is_busy or not self.context.has_journal():
            return
        records = recent_runs(self.output_path(), limit=1)
        if not records:
            return
        latest = records[0]
        action = "deleted" if latest.mode == Mode.COPY.value else "moved back"
        when = latest.started.strftime("%Y-%m-%d %H:%M") if latest.started else "the last run"
        answer = QMessageBox.question(
            self,
            "Undo last run",
            f"Undo the run from {when}?\n\n"
            f"{plural(latest.files, 'file')} will be {action}. Nothing is overwritten.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.start_undo()

    def start_undo(self) -> UndoTask:
        task = UndoTask(self.output_path())
        task.progressed.connect(self.activity.set_progress)
        task.succeeded.connect(self._on_undo_done)
        task.nothing_to_undo.connect(lambda msg: self.activity.set_status("Nothing to undo", msg))
        task.failed.connect(lambda message: self._show_error("Undo failed", message))
        task.done.connect(self.context.libraryChanged)
        self.activity.set_status("Undoing last run…")
        self.activity.set_indeterminate()
        self.context.launch(task, busy=True)
        return task

    def _on_undo_done(self, result: UndoResult) -> None:
        self.activity.reset_progress(100 if result.ok else 0)
        self.activity.show_summary(undo_summary(result))
        self.activity.offer_review(0)

    def shutdown(self) -> None:
        self._debounce.stop()
