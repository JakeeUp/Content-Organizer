"""Settings: appearance, FFmpeg, where config and logs live, and version info."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from content_organizer import __version__, logging_setup
from content_organizer import config as config_module
from content_organizer.gui import theme
from content_organizer.gui.context import AppContext
from content_organizer.gui.pages.base import Page
from content_organizer.gui.widgets import Card, ElidedLabel, SegmentedControl, button, label

REPO_URL = "https://github.com/JakeeUp/Content-Organizer"
_APPEARANCE = (
    (theme.Appearance.SYSTEM.value, "System", "monitor"),
    (theme.Appearance.LIGHT.value, "Light", "sun"),
    (theme.Appearance.DARK.value, "Dark", "moon"),
)


def _setting_row(title: str, description: str, *actions: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(12)
    texts = QVBoxLayout()
    texts.setSpacing(1)
    texts.addWidget(label(title, "strong"))
    texts.addWidget(label(description, "caption", wrap=True))
    row.addLayout(texts, 1)
    for action in actions:
        row.addWidget(action)
    return row


class SettingsPage(Page):
    installFfmpegRequested = pyqtSignal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__("Settings", "Preferences are saved as soon as you change them.", parent)
        self.context = context
        self.body.addWidget(self._build_appearance())
        self.body.addWidget(self._build_ffmpeg())
        self.body.addWidget(self._build_files())
        self.body.addWidget(self._build_about())
        self.body.addStretch(1)
        context.ffprobeChanged.connect(self._show_ffprobe)
        self._show_ffprobe()

    def _build_appearance(self) -> Card:
        card = Card("Appearance")
        self.appearance = SegmentedControl(_APPEARANCE)
        self.appearance.set_value(theme.manager().mode.value)
        self.appearance.changed.connect(self.set_appearance)
        card.body.addLayout(
            _setting_row("Theme", "System follows your operating system.", self.appearance)
        )
        return card

    def _build_ffmpeg(self) -> Card:
        card = Card("Video analysis", "FFmpeg's ffprobe tells vertical from horizontal videos.")
        self.ffprobe_label = ElidedLabel("")
        self.ffprobe_label.setProperty("role", "caption")
        self.install_button = button("Install FFmpeg", "download")
        self.install_button.clicked.connect(self.installFfmpegRequested)
        self.recheck_button = button(
            "Check again", "refresh", variant="ghost", tooltip="Look for ffprobe again"
        )
        self.recheck_button.clicked.connect(self.context.check_ffprobe)
        row = QHBoxLayout()
        row.setSpacing(12)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        self.ffprobe_title = label("", "strong")
        texts.addWidget(self.ffprobe_title)
        texts.addWidget(self.ffprobe_label)
        row.addLayout(texts, 1)
        row.addWidget(self.recheck_button)
        row.addWidget(self.install_button)
        card.body.addLayout(row)
        return card

    def _build_files(self) -> Card:
        card = Card("Files")
        config_path = config_module.default_config_path()
        log_path = logging_setup.log_file_path()
        self.config_button = self._open_button(config_path.parent)
        self.log_button = self._open_button(log_path.parent)
        card.body.addLayout(_setting_row("Configuration", str(config_path), self.config_button))
        card.body.addLayout(_setting_row("Log file", str(log_path), self.log_button))
        return card

    def _build_about(self) -> Card:
        card = Card("About")
        source = button("Source code", "github", variant="ghost", tooltip=REPO_URL)
        source.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        card.body.addLayout(
            _setting_row(
                f"{theme.APP_DISPLAY_NAME} {__version__}",
                "Sorts a creator's media inbox into vertical and horizontal videos, audio, "
                "images and projects, with a dry-run preview and undo. MIT License.",
                source,
            )
        )
        return card

    @staticmethod
    def _open_button(folder: Path) -> QPushButton:
        widget = button("Open folder", "open", tooltip=str(folder))

        def _open() -> None:
            folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

        widget.clicked.connect(_open)
        return widget

    def set_appearance(self, mode: str) -> None:
        theme.manager().set_mode(mode)
        self.context.settings.setValue(theme.SETTINGS_KEY, mode)
        self.appearance.set_value(mode)

    def _show_ffprobe(self) -> None:
        path = self.context.ffprobe
        if path is None:
            self.ffprobe_title.setText("FFmpeg not found")
            self.ffprobe_label.setText(
                "Untagged videos go to 'Videos' for review until FFmpeg is installed."
            )
        else:
            self.ffprobe_title.setText("FFmpeg is available")
            self.ffprobe_label.setText(str(path))
        self.install_button.setVisible(path is None)
