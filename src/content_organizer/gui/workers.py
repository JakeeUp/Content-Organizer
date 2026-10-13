"""Background tasks: each core call runs in a ``QThread`` and reports through signals.

Pattern: a :class:`Task` is a ``QObject`` moved to its own ``QThread`` by
:func:`start_task`. The core's callbacks run on that worker thread and are re-emitted as
signals (queued to the GUI thread) - widgets are never touched from the worker.
Cancellation sets the ``threading.Event`` the core already polls, so it is safe to call
:meth:`Task.cancel` directly from the GUI thread.

Signal names avoid ``finished``/``started`` (which belong to ``QThread``).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QObject, QThread, pyqtSignal, pyqtSlot

from content_organizer.config import Config
from content_organizer.executor import (
    Mode,
    NothingToUndoError,
    ProgressEvent,
    RunResult,
    UndoResult,
    execute,
    undo_last_run,
)
from content_organizer.ffmpeg_install import (
    InstallCancelled,
    UnsupportedPlatformError,
    install_ffmpeg,
)
from content_organizer.planner import Options, Plan, PlanError, build_plan
from content_organizer.probe import Prober
from content_organizer.stats import LibraryStats, library_stats

log = logging.getLogger(__name__)


class Task(QObject):
    """Base task. Subclasses implement :meth:`work`; exceptions become :attr:`failed`."""

    succeeded = pyqtSignal(object)  # the task's result
    failed = pyqtSignal(str)  # user-facing error message
    done = pyqtSignal()  # always emitted last, success or not

    def __init__(self) -> None:
        super().__init__()
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation (thread-safe; the core checks it between files)."""
        self.cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.work()
        except Exception as exc:  # report everything to the user, never crash the thread
            if not self.handle_error(exc):
                log.exception("%s failed", type(self).__name__)
                self.failed.emit(str(exc) or type(exc).__name__)
        else:
            self.succeeded.emit(result)
        finally:
            # Hand the object back to the GUI thread so it can be dropped safely there.
            app = QCoreApplication.instance()
            if app is not None:
                self.moveToThread(app.thread())
            self.done.emit()

    def work(self) -> object:  # pragma: no cover - abstract
        raise NotImplementedError

    def handle_error(self, exc: Exception) -> bool:
        """Return True if the subclass reported ``exc`` itself."""
        return False


class PlanTask(Task):
    """Builds a dry-run :class:`Plan` (slow step: probes every video)."""

    progressed = pyqtSignal(int, int, str)  # done, total, current path

    def __init__(
        self,
        source: Path,
        output: Path,
        options: Options,
        config: Config,
        prober: Prober | None = None,
    ) -> None:
        super().__init__()
        self.source, self.output, self.options = source, output, options
        self.config, self.prober = config, prober

    def work(self) -> Plan:
        return build_plan(
            self.source,
            self.output,
            self.options,
            prober=self.prober,
            config=self.config,
            progress=lambda done, total, path: self.progressed.emit(done, total, str(path)),
            cancel=self.cancel_event,
        )

    def handle_error(self, exc: Exception) -> bool:
        if isinstance(exc, PlanError):
            self.failed.emit(str(exc))
            return True
        return False


class ExecuteTask(Task):
    """Carries out a confirmed plan; :attr:`progressed` carries a ``ProgressEvent``."""

    progressed = pyqtSignal(object)

    def __init__(self, plan: Plan, mode: Mode) -> None:
        super().__init__()
        self.plan, self.mode = plan, mode

    def work(self) -> RunResult:
        return execute(self.plan, self.mode, progress=self._report, cancel=self.cancel_event)

    def _report(self, event: ProgressEvent) -> None:
        self.progressed.emit(event)


class StatsTask(Task):
    """Library statistics for the dashboard (walks the disk, no ffprobe)."""

    def __init__(self, folder: Path, config: Config) -> None:
        super().__init__()
        self.folder, self.config = folder, config

    def work(self) -> LibraryStats:
        return library_stats(self.folder, self.config, cancel=self.cancel_event)


class UndoTask(Task):
    progressed = pyqtSignal(int, int)
    nothing_to_undo = pyqtSignal(str)

    def __init__(self, output: Path) -> None:
        super().__init__()
        self.output = output

    def work(self) -> UndoResult:
        return undo_last_run(self.output, progress=self.progressed.emit)

    def handle_error(self, exc: Exception) -> bool:
        if isinstance(exc, NothingToUndoError):
            self.nothing_to_undo.emit(str(exc))
            return True
        return False


class FfmpegInstallTask(Task):
    """Downloads and verifies FFmpeg (Windows). ``total`` is -1 when unknown."""

    progressed = pyqtSignal(object, object)  # bytes_done:int, total:int (64-bit safe)
    cancelled = pyqtSignal()
    unsupported = pyqtSignal(str)  # manual install instructions

    def __init__(self, **install_kwargs: object) -> None:
        super().__init__()
        self._install_kwargs = install_kwargs

    def work(self) -> Path:
        return install_ffmpeg(
            progress=self._report,
            cancel=self.cancel_event,
            **self._install_kwargs,  # type: ignore[arg-type]
        )

    def _report(self, done: int, total: int | None) -> None:
        self.progressed.emit(done, -1 if total is None else total)

    def handle_error(self, exc: Exception) -> bool:
        if isinstance(exc, InstallCancelled):
            self.cancelled.emit()
            return True
        if isinstance(exc, UnsupportedPlatformError):
            self.unsupported.emit(str(exc))
            return True
        return False


#: Keeps every running (thread, task) pair alive until the thread has really finished,
#: so a caller dropping its reference can never destroy a running QThread.
_running: set[tuple[QThread, Task]] = set()


def start_task(task: Task, parent: QObject | None = None) -> QThread:
    """Run ``task`` on a fresh ``QThread`` that cleans itself up when the task is done."""
    thread = QThread(parent)
    thread.setObjectName(type(task).__name__)
    task.moveToThread(thread)
    entry = (thread, task)
    _running.add(entry)
    thread.started.connect(task.run)
    task.done.connect(thread.quit)
    thread.finished.connect(lambda: _running.discard(entry))
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


def running_threads() -> list[QThread]:
    return [thread for thread, _task in _running]
