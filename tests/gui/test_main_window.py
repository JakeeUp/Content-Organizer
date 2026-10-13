"""Main window: construction, options mapping, validation, organize/undo flow, dashboard."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt

from content_organizer.categories import Category
from content_organizer.executor import Mode, list_journals
from content_organizer.gui.main_window import MIN_HEIGHT, MIN_WIDTH
from content_organizer.planner import Options, build_plan

NO_PROBE = Options(probe=False, date_folders=False)


def files_under(root: Path) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".content-organizer" not in p.parts
    )


def wait_idle(qtbot, window, timeout=10_000) -> None:
    qtbot.waitUntil(lambda: not window.is_busy, timeout=timeout)


# ---------------------------------------------------------------- construction


def test_window_constructs_with_neutral_branding(window):
    assert window.windowTitle() == "Content Organizer"
    assert "Jacob" not in window.windowTitle()
    assert window.minimumWidth() == MIN_WIDTH and window.minimumHeight() == MIN_HEIGHT
    assert MIN_WIDTH <= 1100 and MIN_HEIGHT <= 720
    for button in (
        window.organize_button,
        window.review_button,
        window.undo_button,
        window.open_output_button,
    ):
        assert button.text().strip(), "buttons need readable text, not just an icon"
        assert not button.icon().isNull()
        assert button.toolTip()
    assert not window.is_busy


def test_toggles_map_to_options_and_persist(window, settings):
    window.video_option.setChecked(False)
    window.date_option.setChecked(False)
    window.clean_option.setChecked(True)
    window.copy_option.setChecked(True)
    assert window.options() == Options(date_folders=False, clean_names=True, probe=False)
    assert window.mode() is Mode.COPY

    window.video_option.setChecked(True)
    window.copy_option.setChecked(False)
    assert window.options().probe is True
    assert window.mode() is Mode.MOVE
    assert settings.value("options/cleanNames", type=bool) is True
    assert settings.value("options/dateFolders", type=bool) is False


def test_toggle_row_label_click_toggles_and_space_works(qtbot, window):
    window.show()
    before = window.clean_option.isChecked()
    qtbot.mouseClick(window.clean_option.title_label, Qt.MouseButton.LeftButton)
    assert window.clean_option.isChecked() is not before
    window.clean_option.switch.setFocus()
    qtbot.keyClick(window.clean_option.switch, Qt.Key.Key_Space)
    assert window.clean_option.isChecked() is before


def test_settings_restore_folders_and_options(make_window, settings, tmp_path):
    settings.setValue("paths/source", str(tmp_path))
    settings.setValue("options/cleanNames", True)
    window = make_window()
    assert window.source_field.text() == str(tmp_path)
    assert window.clean_option.isChecked()


def test_video_toggle_disabled_without_ffprobe(make_window, settings):
    window = make_window(ffprobe=None)
    assert not window.video_option.isEnabled()
    assert window.options().probe is False
    assert "FFmpeg" in window.video_option.toolTip()
    assert window.banner.isVisibleTo(window)

    window.banner.dismiss_button.click()
    assert not window.banner.isVisibleTo(window)
    assert settings.value("ffmpeg/bannerDismissed", type=bool) is True
    # Remembered: the next launch does not nag again.
    assert not make_window(ffprobe=None).banner.isVisibleTo(window)


def test_video_preference_survives_missing_ffprobe(make_window, settings):
    settings.setValue("options/video", True)
    make_window(ffprobe=None)
    assert settings.value("options/video", type=bool) is True


# ------------------------------------------------------------------ validation


def test_organize_disabled_until_folders_are_valid(window, make_tree, tmp_path):
    src = make_tree(["a.png"])
    assert not window.organize_button.isEnabled()

    window.source_field.set_text(str(src))
    assert not window.organize_button.isEnabled()

    window.output_field.set_text(str(src))
    assert not window.organize_button.isEnabled()
    assert window.output_field.status.objectName() == "statusError"
    assert "different" in window.output_field.status.text()

    window.output_field.set_text(str(tmp_path / "new-output"))
    assert window.organize_button.isEnabled()
    assert "created" in window.output_field.status.text()

    window.source_field.set_text(str(tmp_path / "missing"))
    assert not window.organize_button.isEnabled()
    assert window.source_field.status.objectName() == "statusError"


def test_output_inside_source_warns_but_is_allowed(window, make_tree):
    src = make_tree(["a.png"])
    window.source_field.set_text(str(src))
    window.output_field.set_text(str(src / "sorted"))
    assert window.organize_button.isEnabled()
    assert window.output_field.status.objectName() == "statusWarn"


def test_relative_paths_are_rejected(window):
    window.source_field.set_text("relative/inbox")
    assert window.source_field.status.objectName() == "statusError"
    assert not window.organize_button.isEnabled()


# --------------------------------------------------------------------- flows


def test_preview_then_organize_then_undo(qtbot, window, make_tree, tmp_path, monkeypatch):
    src = make_tree(["a.png", "b_music.mp3", "clip_vert.mp4", "notes.txt"])
    out = tmp_path / "out"
    window.date_option.setChecked(False)
    window.source_field.set_text(str(src))
    window.output_field.set_text(str(out))

    shown = []

    class AcceptingDialog:
        def __init__(self, plan):
            shown.append(plan)

        def exec(self):
            return 1  # QDialog.DialogCode.Accepted

    monkeypatch.setattr(window, "create_preview_dialog", AcceptingDialog)
    window.start_organize()
    qtbot.waitUntil(lambda: window.last_result is not None, timeout=10_000)
    wait_idle(qtbot, window)

    assert len(shown[0]) == 4
    assert files_under(src) == []
    assert files_under(out) == [
        "Images/a.png",
        "Music/b_music.mp3",
        "Other/notes.txt",
        "VerticalVideos/clip_vert.mp4",
    ]
    assert window.activity.title.text() == "Complete"
    assert window.activity.review_link.isVisibleTo(window)  # notes.txt landed in Other
    qtbot.waitUntil(lambda: window.undo_button.isEnabled(), timeout=5_000)
    qtbot.waitUntil(lambda: window.stats is not None and window.stats.total == 4, timeout=5_000)

    window.confirm_undo()  # the confirmation box is auto-answered "Yes" in tests
    wait_idle(qtbot, window)
    assert files_under(src) == ["a.png", "b_music.mp3", "clip_vert.mp4", "notes.txt"]
    assert window.activity.title.text() == "Undo complete"
    qtbot.waitUntil(lambda: not window.undo_button.isEnabled(), timeout=5_000)


def test_closing_the_preview_changes_nothing(qtbot, window, make_tree, tmp_path, monkeypatch):
    src = make_tree(["a.png"])
    window.source_field.set_text(str(src))
    window.output_field.set_text(str(tmp_path / "out"))

    class RejectingDialog:
        def __init__(self, plan):
            pass

        def exec(self):
            return 0

    monkeypatch.setattr(window, "create_preview_dialog", RejectingDialog)
    window.start_organize()
    qtbot.waitUntil(lambda: "No files were changed" in window.activity.detail.text(), timeout=5_000)
    assert files_under(src) == ["a.png"]
    assert not (tmp_path / "out").exists()


def test_run_reports_progress_and_can_be_cancelled(qtbot, window, make_tree, tmp_path, config):
    src = make_tree([f"img_{i:02}.png" for i in range(25)])
    out = tmp_path / "out"
    window.output_field.set_text(str(out))
    plan = build_plan(src, out, NO_PROBE, config=config)

    task = window.start_execute(plan, Mode.MOVE)
    assert window.is_busy and window.activity.cancel_button.isVisibleTo(window)
    assert not window.organize_button.isEnabled()
    # Cancel synchronously on the worker thread after the first file, deterministically.
    task.progressed.connect(lambda _event: task.cancel(), Qt.ConnectionType.DirectConnection)
    wait_idle(qtbot, window)

    result = window.last_result
    assert result is not None and result.stats.cancelled
    assert 1 <= result.stats.moved < 25
    assert window.activity.title.text() == "Cancelled"
    assert "not processed" in window.activity.detail.text()
    assert not window.activity.cancel_button.isVisibleTo(window)
    assert len(files_under(out)) == result.stats.moved
    assert list_journals(out), "the partial run must still be undoable"


def test_completion_shows_errors_and_duplicates(qtbot, window, make_tree, tmp_path, config):
    src = make_tree({"a.png": "same", "b.png": "other"})
    out = tmp_path / "out"
    (out / "Images").mkdir(parents=True)
    (out / "Images" / "a.png").write_text("same")
    window.output_field.set_text(str(out))
    plan = build_plan(src, out, NO_PROBE, config=config)
    window.start_execute(plan, Mode.MOVE)
    wait_idle(qtbot, window)
    assert "1 duplicate skipped" in window.activity.detail.text()
    assert window.activity.details_button.isVisibleTo(window)
    window.activity.details_button.click()
    assert window.activity.details.isVisibleTo(window)
    assert "a.png" in window.activity.details.toPlainText()


# ------------------------------------------------------------------- dashboard


def make_library(root: Path) -> Path:
    for rel in (
        "VerticalVideos/2023/12 - December/a.mp4",
        "VerticalVideos/2024/01 - January/b.mp4",
        "HorizontalVideos/2024/01 - January/c.mp4",
        "Images/x.png",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel)
    return root


def test_dashboard_loads_stats_in_background(qtbot, window, tmp_path):
    out = make_library(tmp_path / "lib")
    window.output_field.set_text(str(out))
    window.refresh_library()
    qtbot.waitUntil(lambda: window.stats is not None, timeout=5_000)
    assert window.library.ring.total == 4
    assert window.library.category_bars.count_text(Category.VERTICAL) == "2"
    keys = [key for key, _ in window.chart.series]
    assert keys[:2] == [(2023, 12), (2024, 1)]  # chronological, years kept apart


def test_chart_click_opens_the_right_month_folders(qtbot, window, tmp_path, monkeypatch):
    out = make_library(tmp_path / "lib")
    window.output_field.set_text(str(out))
    window.refresh_library()
    qtbot.waitUntil(lambda: window.stats is not None, timeout=5_000)

    opened: list[Path] = []
    monkeypatch.setattr(window, "_open_path", lambda p: opened.append(p) or True)
    window.open_month(2023, 12)
    assert opened == [out.resolve() / "VerticalVideos" / "2023" / "12 - December"]

    january = window.folders_for_month(2024, 1)
    assert {p.parts[-3] for p in january} == {"VerticalVideos", "HorizontalVideos"}
    menu = window._month_menu(january)
    labels = [a.text() for a in menu.actions() if a.text()]
    assert "Open all" in labels and len(labels) == 3

    opened.clear()
    window.open_month(1999, 1)  # no folder for that month: a status message, no crash
    assert opened == []
