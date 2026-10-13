"""Composite dashboard panels. They only display state; the window decides what to show."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QWidget,
)

from content_organizer.categories import Category
from content_organizer.gui import icons, theme
from content_organizer.gui.presenters import RunSummary, plural
from content_organizer.gui.widgets import Card, CategoryBars, ElidedLabel, RingChart, Segment
from content_organizer.stats import LibraryStats

_KIND_COLORS = {"ok": theme.SUCCESS, "warn": theme.AMBER, "error": theme.DANGER}


class ActivityPanel(Card):
    """Status title, progress bar, current file, Cancel, completion summary + details."""

    cancelRequested = pyqtSignal()
    reviewRequested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.title = QLabel("Ready")
        self.title.setObjectName("statusTitle")
        self.body.addWidget(self.title)
        self.detail = QLabel(
            "Choose a source and an output folder, then preview the planned moves."
        )
        self.detail.setObjectName("cardSubtitle")
        self.detail.setWordWrap(True)
        self.body.addWidget(self.detail)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setAccessibleName("Progress")
        self.body.addWidget(self.progress_bar)
        self.current_file = ElidedLabel(" ")
        self.current_file.setObjectName("currentFile")
        self.body.addWidget(self.current_file)
        self.body.addLayout(self._build_button_row())

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        self.details.setAccessibleName("Run details")
        self.details.hide()
        self.body.addWidget(self.details)

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.cancel_button = QPushButton(icons.icon("cancel", "#FDA4AF"), "Cancel")
        self.cancel_button.setObjectName("danger")
        self.cancel_button.setToolTip(
            "Stop after the current file (Esc). Finished files stay done."
        )
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancelRequested)
        row.addWidget(self.cancel_button)
        self.review_link = self._link_button()
        self.review_link.setToolTip("These files could not be placed confidently")
        self.review_link.clicked.connect(self.reviewRequested)
        row.addWidget(self.review_link)
        row.addStretch(1)
        self.details_button = self._link_button("Show details")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        row.addWidget(self.details_button)
        return row

    @staticmethod
    def _link_button(text: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("link")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.hide()
        return button

    # ----------------------------------------------------------------- state

    def set_status(self, title: str, detail: str = "", kind: str = "") -> None:
        self.title.setText(title)
        self.detail.setText(detail)
        color = _KIND_COLORS.get(kind)
        self.title.setStyleSheet(f"color: {color};" if color else "")

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


class LibraryPanel(Card):
    """Total ring and per-category bars for the output library."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Library", "Choose an output folder to see its contents.", parent)
        self.refresh_button = QPushButton(icons.icon("refresh"), "Refresh")
        self.refresh_button.setToolTip("Rescan the output folder (F5)")
        self.add_header_widget(self.refresh_button)
        self.ring = RingChart()
        self.body.addWidget(self.ring, 1)
        self.category_bars = CategoryBars()
        self.body.addWidget(self.category_bars)

    def show_stats(self, stats: LibraryStats) -> None:
        name = stats.root.name or str(stats.root)
        self.set_subtitle(f"{name} · {plural(len(stats.by_month), 'month')} of files")
        self.subtitle_label.setToolTip(str(stats.root))
        self.ring.set_segments(
            [
                Segment(c.label, stats.by_category.get(c, 0), theme.category_color(c))
                for c in Category
            ],
            "files in library",
        )
        self.category_bars.set_counts(stats.by_category)

    def show_scanning(self, name: str) -> None:
        self.set_subtitle(f"Scanning {name}…")

    def clear(self, message: str = "Choose an output folder to see its contents.") -> None:
        self.set_subtitle(message)
        self.subtitle_label.setToolTip("")
        self.ring.clear()
        self.category_bars.set_counts({})


class FfmpegBanner(QFrame):
    """Non-blocking notice shown when ffprobe is missing."""

    installRequested = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("banner")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(icons.icon("warning", theme.AMBER).pixmap(20, 20))
        row.addWidget(icon)
        text = QLabel(
            "FFmpeg is not installed, so video orientation can't be detected. "
            "Untagged videos will be filed under 'Videos' for review."
        )
        text.setObjectName("bannerText")
        text.setWordWrap(True)
        row.addWidget(text, 1)
        windows = sys.platform == "win32"
        self.install_button = QPushButton(
            icons.icon("download"), "Install FFmpeg" if windows else "How to install"
        )
        self.install_button.setToolTip(
            "Download FFmpeg from gyan.dev, verify its checksum and install it for this user"
            if windows
            else "Show installation instructions for your system"
        )
        self.install_button.clicked.connect(self.installRequested)
        row.addWidget(self.install_button)
        self.dismiss_button = QPushButton("Not now")
        self.dismiss_button.setToolTip(
            "Hide this message. You can install FFmpeg later from the Help menu."
        )
        self.dismiss_button.clicked.connect(self.dismissed)
        row.addWidget(self.dismiss_button)
        self.hide()


class FfmpegInstallDialog(QProgressDialog):
    """Real download progress (bytes) with a working Cancel; never auto-closes."""

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
