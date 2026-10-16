"""GUI entry point: ``content-organizer-gui`` or ``python -m content_organizer.gui.app``."""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence

from PyQt6.QtCore import QCoreApplication, QSettings, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from content_organizer import __version__
from content_organizer.gui import icons, theme
from content_organizer.logging_setup import configure_logging

log = logging.getLogger(__name__)


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create (or reuse) the ``QApplication`` with names, high-DPI policy and theme."""
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        app = existing
    else:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(list(argv if argv is not None else sys.argv))
    # Organisation/application names decide where QSettings stores preferences.
    QCoreApplication.setOrganizationName(theme.ORG_NAME)
    QCoreApplication.setApplicationName(theme.APP_DISPLAY_NAME)
    QCoreApplication.setApplicationVersion(__version__)
    QGuiApplication.setApplicationDisplayName(theme.APP_DISPLAY_NAME)
    QGuiApplication.setDesktopFileName("content-organizer")
    app.setWindowIcon(icons.app_icon())
    theme.apply_theme(app, str(QSettings().value(theme.SETTINGS_KEY, theme.Appearance.SYSTEM)))
    return app


def main(argv: Sequence[str] | None = None) -> int:
    log_path = configure_logging(console=sys.stderr is not None)
    log.info("Starting %s %s (log: %s)", theme.APP_DISPLAY_NAME, __version__, log_path)
    app = create_application(argv)

    from content_organizer.gui.main_window import MainWindow  # after QApplication exists

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
