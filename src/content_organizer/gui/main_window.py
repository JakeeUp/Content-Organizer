"""Main window: a sidebar and four pages (Organize, Library, Review, Settings).

All file work is delegated to the Qt-free core through :mod:`.workers`; pages share
state through :class:`.context.AppContext`, so this module only builds the shell and
wires menus and shortcuts.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence, QResizeEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from content_organizer import __version__
from content_organizer.config import (
    Config,
    ConfigError,
    build_config,
    load_config,
    load_defaults_dict,
)
from content_organizer.gui import icons, theme
from content_organizer.gui.context import AppContext
from content_organizer.gui.ffmpeg_setup import FfmpegSetup
from content_organizer.gui.pages import LibraryPage, OrganizePage, ReviewPage, SettingsPage
from content_organizer.gui.presenters import plural
from content_organizer.gui.widgets import Sidebar
from content_organizer.probe import Prober, find_ffprobe

log = logging.getLogger(__name__)

MIN_WIDTH, MIN_HEIGHT = 960, 640
COLLAPSE_BELOW = 1180  # window width at which the sidebar shrinks to icons
ORGANIZE, LIBRARY, REVIEW, SETTINGS = range(4)
_PAGES = (
    ("Organize", "sort"),
    ("Library", "library"),
    ("Review", "review"),
    ("Settings", "settings"),
)


class MainWindow(QMainWindow):
    """The application shell. Dependencies are injectable for tests."""

    def __init__(
        self,
        settings: QSettings | None = None,
        config: Config | None = None,
        prober: Prober | None = None,
        ffprobe_locator: Callable[[], Path | None] = find_ffprobe,
    ) -> None:
        super().__init__()
        self._config_error: str | None = None
        settings = settings if settings is not None else QSettings()
        config = config if config is not None else self._load_config()
        self.context = AppContext(settings, config, prober, ffprobe_locator, self)
        self.context.check_ffprobe()  # fast: a PATH lookup plus a few stat calls
        self.ffmpeg = FfmpegSetup(self.context, self)

        self.setWindowTitle(theme.APP_DISPLAY_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self._build_ui()
        self._build_menu()
        self._connect_signals()
        self._restore_geometry()
        self._show_ffprobe_status()
        self.show_page(int(settings.value("window/page", ORGANIZE, type=int)))
        if self._config_error:
            QTimer.singleShot(0, self._warn_config_error)

    @property
    def settings(self) -> QSettings:
        return self.context.settings

    @property
    def config(self) -> Config:
        return self.context.config

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
        shell = QWidget()
        shell.setObjectName("shell")
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.sidebar = Sidebar(__version__)
        for i, (text, icon) in enumerate(_PAGES):
            self.sidebar.add_item(text, icon, f"Ctrl+{i + 1}")
        row.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        # Organize first: it restores the folders every other page reads.
        self.organize = OrganizePage(self.context)
        self.library = LibraryPage(self.context)
        self.review = ReviewPage(self.context)
        self.settings_page = SettingsPage(self.context)
        for page in (self.organize, self.library, self.review, self.settings_page):
            self.pages.addWidget(page)
        row.addWidget(self.pages, 1)
        self.setCentralWidget(shell)
        status = self.statusBar()
        if status is not None:
            status.setSizeGripEnabled(False)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        assert bar is not None
        file_menu = bar.addMenu("&File")
        run_menu = bar.addMenu("&Run")
        view_menu = bar.addMenu("&View")
        help_menu = bar.addMenu("&Help")
        assert file_menu and run_menu and view_menu and help_menu
        self._add_action(
            file_menu, "&Open Output Folder", self.library.open_output_folder, "Ctrl+Shift+O"
        )
        file_menu.addSeparator()
        self._add_action(file_menu, "&Quit", self.close, QKeySequence.StandardKey.Quit)

        self._add_action(run_menu, "&Preview && Organize…", self.start_organize, "Ctrl+Return")
        self._add_action(run_menu, "&Review Files", self.open_review, "Ctrl+R")
        self._add_action(run_menu, "&Undo Last Run", self.organize.confirm_undo, "Ctrl+Z")
        self._add_action(run_menu, "Re&fresh Library", self.library.refresh, "F5")
        self._add_action(run_menu, "&Cancel", self.organize.cancel_current, "Esc")

        for i, (text, _icon) in enumerate(_PAGES):
            self._add_action(view_menu, f"&{text}", partial(self.show_page, i), f"Ctrl+{i + 1}")

        self._add_action(help_menu, "Install &FFmpeg…", self.ffmpeg.install)
        help_menu.addSeparator()
        self._add_action(
            help_menu, f"&About {theme.APP_DISPLAY_NAME}", lambda: self.show_page(SETTINGS)
        )

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
        ctx = self.context
        self.sidebar.pageRequested.connect(self.show_page)
        self.sidebar.statusClicked.connect(lambda: self.show_page(SETTINGS))
        ctx.reviewCountChanged.connect(self.sidebar.items[REVIEW].set_badge)
        ctx.ffprobeChanged.connect(self._show_ffprobe_status)
        self.organize.reviewRequested.connect(self.open_review)
        self.organize.installFfmpegRequested.connect(self.ffmpeg.install)
        self.settings_page.installFfmpegRequested.connect(self.ffmpeg.install)
        self.library.organizeRequested.connect(lambda: self.show_page(ORGANIZE))
        self.review.organizeRequested.connect(lambda: self.show_page(ORGANIZE))
        self.library.statusMessage.connect(self._status_message)
        self.review.fileMoved.connect(
            lambda _dest, _cat: self._status_message(
                f"Filed {plural(self.review.moved_count, 'file')}."
            )
        )

    def _restore_geometry(self) -> None:
        geometry = self.settings.value("window/geometry", QByteArray(), type=QByteArray)
        if not isinstance(geometry, QByteArray) or not self.restoreGeometry(geometry):
            self._apply_default_geometry()

    def _apply_default_geometry(self) -> None:
        screen = self.screen()
        if screen is None:
            self.resize(1360, 860)
            return
        area = screen.availableGeometry()
        self.resize(
            max(MIN_WIDTH, min(1440, area.width() - 80)),
            max(MIN_HEIGHT, min(920, area.height() - 80)),
        )
        frame = self.frameGeometry()
        frame.moveCenter(area.center())
        self.move(frame.topLeft())

    # ================================================================ pages

    def show_page(self, index: int) -> None:
        if not 0 <= index < self.pages.count():
            index = ORGANIZE
        self.pages.setCurrentIndex(index)
        self.sidebar.set_current(index)

    def current_page(self) -> int:
        return self.pages.currentIndex()

    def start_organize(self) -> None:
        self.show_page(ORGANIZE)
        self.organize.start_organize()

    def open_review(self) -> None:
        self.show_page(REVIEW)

    def _show_ffprobe_status(self) -> None:
        path = self.context.ffprobe
        if path is None:
            self.sidebar.set_status(
                "warn", "FFmpeg missing", "Video orientation can't be detected. Click to set up."
            )
        else:
            self.sidebar.set_status("ok", "Video analysis on", f"ffprobe: {path}")

    def _status_message(self, text: str, timeout: int = 6000) -> None:
        statusbar = self.statusBar()
        if statusbar is not None:
            statusbar.showMessage(text, timeout)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)
        self.sidebar.set_collapsed(self.width() < COLLAPSE_BELOW)

    # ================================================================== close

    @property
    def is_busy(self) -> bool:
        return self.context.is_busy

    def shutdown(self, timeout_ms: int = 10_000) -> None:
        """Cancel every background task and wait for its thread (used on close)."""
        self.organize.shutdown()
        self.library.shutdown()
        self.context.shutdown(timeout_ms)

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
        self.settings.setValue("window/page", self.current_page())
        self.settings.sync()
        self.shutdown()
        super().closeEvent(event)
