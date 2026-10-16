"""FFmpeg download flow: worker task + a real progress dialog with Cancel."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QWidget

from content_organizer.ffmpeg_install import manual_install_hint
from content_organizer.gui.context import AppContext
from content_organizer.gui.workers import FfmpegInstallTask


class FfmpegInstallDialog(QProgressDialog):
    """Download progress in bytes with a working Cancel; never auto-closes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Connecting to gyan.dev…", "Cancel", 0, 0, parent)
        self.setWindowTitle("Installing FFmpeg")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.setMinimumDuration(0)
        self.setMinimumWidth(440)
        self.canceled.connect(lambda: self.setLabelText("Cancelling…"))

    def show_progress(self, done: int, total: int) -> None:
        """``total`` is -1 when the server did not send a size."""
        mb = 1024 * 1024
        if total <= 0:
            self.setRange(0, 0)
            self.setLabelText(f"Downloading FFmpeg… {done / mb:.1f} MB")
        elif done >= total:
            self.setRange(0, 0)
            self.setLabelText("Verifying checksum and extracting…")
        else:
            self.setRange(0, max(1, total // 1024))  # KiB keeps values inside a C int
            self.setValue(done // 1024)
            self.setLabelText(f"Downloading FFmpeg… {done / mb:.1f} of {total / mb:.1f} MB")


class FfmpegSetup(QObject):
    """Starts the install (Windows) or shows manual instructions elsewhere."""

    def __init__(self, context: AppContext, window: QWidget) -> None:
        super().__init__(window)
        self.context = context
        self.window = window

    def install(self) -> None:
        if self.context.ffprobe is not None:
            QMessageBox.information(
                self.window, "FFmpeg", f"FFmpeg is already available:\n{self.context.ffprobe}"
            )
        elif sys.platform != "win32":
            QMessageBox.information(self.window, "Install FFmpeg", manual_install_hint())
        elif not self.context.running(FfmpegInstallTask):
            self.start()

    def start(self, **install_kwargs: object) -> FfmpegInstallTask:
        task = FfmpegInstallTask(**install_kwargs)
        dialog = FfmpegInstallDialog(self.window)
        dialog.canceled.connect(task.cancel)
        task.progressed.connect(dialog.show_progress)
        task.succeeded.connect(self._on_installed)
        task.unsupported.connect(
            lambda msg: QMessageBox.information(self.window, "Install FFmpeg", msg)
        )
        task.failed.connect(
            lambda msg: QMessageBox.critical(self.window, "FFmpeg install failed", msg)
        )
        task.done.connect(dialog.close)
        task.done.connect(dialog.deleteLater)
        dialog.show()
        self.context.launch(task)
        return task

    def _on_installed(self, path: Path) -> None:
        self.context.check_ffprobe()
        if self.context.ffprobe is None:
            self.context.set_ffprobe(path)
        QMessageBox.information(
            self.window,
            "FFmpeg installed",
            f"Video analysis is now available.\n\nffprobe: {self.context.ffprobe}",
        )
