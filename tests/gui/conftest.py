"""GUI test setup: headless Qt, themed app, isolated QSettings and a ready window."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QMessageBox

from content_organizer.gui import theme
from content_organizer.gui.main_window import MainWindow

FAKE_FFPROBE = Path("/fake/bin/ffprobe")


@pytest.fixture(autouse=True)
def _themed_app(qapp: QApplication) -> None:
    theme.apply_theme(qapp)


@pytest.fixture(autouse=True)
def _no_modal_boxes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Message boxes would block a headless test run; record them instead."""
    shown: list[tuple[str, str]] = []

    def record(kind: str, answer: object):
        def _box(_parent, title, text, *args, **kwargs):
            shown.append((kind, f"{title}: {text}"))
            return answer

        return _box

    yes = QMessageBox.StandardButton.Yes
    ok = QMessageBox.StandardButton.Ok
    monkeypatch.setattr(QMessageBox, "information", record("information", ok))
    monkeypatch.setattr(QMessageBox, "warning", record("warning", ok))
    monkeypatch.setattr(QMessageBox, "critical", record("critical", ok))
    monkeypatch.setattr(QMessageBox, "question", record("question", yes))
    monkeypatch.setattr(QMessageBox, "about", record("about", None))
    return shown


@pytest.fixture
def message_boxes(_no_modal_boxes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return _no_modal_boxes


@pytest.fixture
def settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def make_window(qtbot, settings, config, fake_prober) -> Iterator:
    windows: list[MainWindow] = []

    def _make(ffprobe: Path | None = FAKE_FFPROBE, prober=None) -> MainWindow:
        window = MainWindow(
            settings=settings,
            config=config,
            prober=prober if prober is not None else fake_prober(),
            ffprobe_locator=lambda: ffprobe,
        )
        qtbot.addWidget(window)
        windows.append(window)
        return window

    yield _make
    for window in windows:
        window.shutdown()


@pytest.fixture
def window(make_window) -> MainWindow:
    return make_window()
