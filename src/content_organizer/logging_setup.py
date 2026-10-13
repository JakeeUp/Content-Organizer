"""Logging configuration - call :func:`configure_logging` only from entry points.

Library modules just use ``logging.getLogger(__name__)``; importing the package never
touches handlers, stdout or the file system.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from platformdirs import user_log_path

from content_organizer import APP_NAME

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_MARKER = "_content_organizer_handler"


def log_file_path() -> Path:
    """Location of the rotating log file."""
    return user_log_path(APP_NAME, appauthor=False) / f"{APP_NAME}.log"


def configure_logging(verbose: bool = False, console: bool = True) -> Path | None:
    """Attach a rotating file handler (DEBUG) and optionally a console handler.

    The console shows WARNING and above, or DEBUG with ``verbose``. Calling this twice
    replaces the handlers it added before. Returns the log file path, or ``None`` if the
    log directory could not be created (logging then continues on the console only).
    """
    pkg_logger = logging.getLogger("content_organizer")
    pkg_logger.setLevel(logging.DEBUG)
    for handler in list(pkg_logger.handlers):
        if getattr(handler, _MARKER, False):
            pkg_logger.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(_FORMAT)
    path: Path | None = log_file_path()
    try:
        log_path = log_file_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8", errors="replace"
        )
    except OSError:
        path = None
    else:
        file_handler.setLevel(logging.DEBUG)
        _add(pkg_logger, file_handler, formatter)

    stream = sys.stderr
    if console and stream is not None:  # stderr is None in windowed (pythonw) builds
        console_handler = logging.StreamHandler(stream)
        console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
        _add(pkg_logger, console_handler, logging.Formatter("%(levelname)s: %(message)s"))
    return path


def _add(logger: logging.Logger, handler: logging.Handler, formatter: logging.Formatter) -> None:
    handler.setFormatter(formatter)
    setattr(handler, _MARKER, True)
    logger.addHandler(handler)
