"""State shared by the pages: settings, config, ffprobe, options, output folder, tasks.

Pages talk to each other only through these signals, so the window stays wiring-only.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QThread, pyqtSignal

from content_organizer.config import Config
from content_organizer.executor import Mode, list_journals
from content_organizer.gui.presenters import validate_output
from content_organizer.gui.workers import ReviewScanTask, Task, start_task
from content_organizer.planner import Options
from content_organizer.probe import Prober

#: Option keys (``options/<key>`` in QSettings) and their defaults.
OPTION_DEFAULTS: dict[str, bool] = {
    "video": True,
    "dateFolders": True,
    "cleanNames": False,
    "copy": False,
}


class AppContext(QObject):
    ffprobeChanged = pyqtSignal()
    outputChanged = pyqtSignal()
    optionsChanged = pyqtSignal()
    libraryChanged = pyqtSignal()  # files were moved, copied or restored
    busyChanged = pyqtSignal(bool)
    reviewCountChanged = pyqtSignal(int)

    def __init__(
        self,
        settings: QSettings,
        config: Config,
        prober: Prober | None,
        ffprobe_locator: Callable[[], Path | None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.config = config
        self.prober = prober
        self._locate_ffprobe = ffprobe_locator
        self.ffprobe: Path | None = None
        self.source_text = ""
        self.output_text = ""
        self.review_count = 0
        self._options = {
            key: bool(settings.value(f"options/{key}", default, type=bool))
            for key, default in OPTION_DEFAULTS.items()
        }
        self._tasks: set[Task] = set()
        self._threads: set[QThread] = set()
        self._busy_task: Task | None = None
        self._review_task: ReviewScanTask | None = None
        self.libraryChanged.connect(self.refresh_review_count)
        self.outputChanged.connect(self.refresh_review_count)

    # ---------------------------------------------------------------- ffprobe

    def check_ffprobe(self) -> None:
        self.ffprobe = self._locate_ffprobe()
        self.ffprobeChanged.emit()

    def set_ffprobe(self, path: Path | None) -> None:
        self.ffprobe = path
        self.ffprobeChanged.emit()

    # ---------------------------------------------------------------- folders

    def set_folders(self, source: str, output: str) -> None:
        self.source_text = source
        self.settings.setValue("paths/source", source)
        self.settings.setValue("paths/output", output)
        if output != self.output_text:
            self.output_text = output
            self.outputChanged.emit()

    def output_dir(self) -> Path | None:
        """The output folder when it is valid and exists, else ``None``."""
        if not self.output_text or not validate_output(self.output_text, self.source_text).usable:
            return None
        path = Path(self.output_text).expanduser()
        return path if path.is_dir() else None

    def has_journal(self) -> bool:
        output = self.output_dir()
        try:
            return output is not None and bool(list_journals(output))
        except OSError:
            return False

    # ---------------------------------------------------------------- options

    def option(self, key: str) -> bool:
        return self._options[key]

    def set_option(self, key: str, value: bool) -> None:
        if self._options.get(key) == value:
            return
        self._options[key] = value
        self.settings.setValue(f"options/{key}", value)
        self.optionsChanged.emit()

    def options(self) -> Options:
        return Options(
            date_folders=self._options["dateFolders"],
            clean_names=self._options["cleanNames"],
            probe=self.ffprobe is not None and self._options["video"],
        )

    def mode(self) -> Mode:
        return Mode.COPY if self._options["copy"] else Mode.MOVE

    # ------------------------------------------------------------------ tasks

    def launch(self, task: Task, *, busy: bool = False) -> None:
        """Run ``task`` on a worker thread; ``busy`` tasks block other file operations."""
        self._tasks.add(task)
        task.done.connect(lambda t=task: self._task_done(t))
        if busy:
            self._busy_task = task
            self.busyChanged.emit(True)
        thread = start_task(task, self)
        self._threads.add(thread)
        thread.finished.connect(lambda th=thread: self._threads.discard(th))

    def _task_done(self, task: Task) -> None:
        self._tasks.discard(task)
        if task is self._busy_task:
            self._busy_task = None
            self.busyChanged.emit(False)

    @property
    def is_busy(self) -> bool:
        return self._busy_task is not None

    @property
    def busy_task(self) -> Task | None:
        return self._busy_task

    def running(self, kind: type[Task]) -> bool:
        return any(isinstance(task, kind) for task in self._tasks)

    def cancel_busy(self) -> bool:
        task = self._busy_task
        if task is None or task.is_cancelled:
            return False
        task.cancel()
        return True

    def shutdown(self, timeout_ms: int = 10_000) -> None:
        """Cancel every background task and wait for its thread."""
        for task in list(self._tasks):
            task.cancel()
        for thread in list(self._threads):
            try:
                thread.quit()
                thread.wait(timeout_ms)
            except RuntimeError:  # already deleted by deleteLater
                pass
        self._threads.clear()

    # ----------------------------------------------------------------- review

    def refresh_review_count(self) -> None:
        if self._review_task is not None:
            self._review_task.cancel()
            self._review_task = None
        output = self.output_dir()
        if output is None:
            self._set_review_count(0)
            return
        task = ReviewScanTask(output, self.config)
        task.succeeded.connect(lambda files, t=task: self._on_review_scan(t, files))
        self._review_task = task
        self.launch(task)

    def _on_review_scan(self, task: ReviewScanTask, files: list[Path]) -> None:
        if task is self._review_task:
            self._review_task = None
            self._set_review_count(len(files))

    def _set_review_count(self, count: int) -> None:
        self.review_count = count
        self.reviewCountChanged.emit(count)
