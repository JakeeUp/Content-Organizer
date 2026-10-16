"""Main window and pages: navigation, options, validation, organize/undo flow, library."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt

from content_organizer.categories import Category
from content_organizer.executor import Mode, list_journals
from content_organizer.gui import theme
from content_organizer.gui.main_window import (
    COLLAPSE_BELOW,
    LIBRARY,
    MIN_HEIGHT,
    MIN_WIDTH,
    ORGANIZE,
    REVIEW,
    SETTINGS,
)
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


def set_folders(window, source: Path | str, output: Path | str) -> None:
    window.organize.source_field.set_text(str(source))
    window.organize.output_field.set_text(str(output))


# ---------------------------------------------------------------- construction


def test_window_constructs_with_neutral_branding(window):
    assert window.windowTitle() == "Content Organizer"
    assert "Jacob" not in window.windowTitle()
    assert window.minimumWidth() == MIN_WIDTH and window.minimumHeight() == MIN_HEIGHT
    assert MIN_WIDTH <= 1100 and MIN_HEIGHT <= 720
    assert [item.text() for item in window.sidebar.items] == [
        "Organize",
        "Library",
        "Review",
        "Settings",
    ]
    button = window.organize.organize_button
    assert button.text().strip() and not button.icon().isNull() and button.toolTip()
    assert window.current_page() == ORGANIZE
    assert not window.is_busy


def test_sidebar_and_shortcuts_switch_pages(qtbot, window, settings):
    window.show()
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    window.sidebar.items[LIBRARY].click()
    assert window.current_page() == LIBRARY
    qtbot.keyClick(window, Qt.Key.Key_4, Qt.KeyboardModifier.ControlModifier)
    assert window.current_page() == SETTINGS
    assert window.sidebar.current() == SETTINGS
    window.sidebar.statusClicked.emit()
    assert window.current_page() == SETTINGS
    window.close()
    assert settings.value("window/page", type=int) == SETTINGS


def test_last_page_is_restored(make_window, settings):
    settings.setValue("window/page", LIBRARY)
    assert make_window().current_page() == LIBRARY
    settings.setValue("window/page", 99)
    assert make_window().current_page() == ORGANIZE


def test_sidebar_collapses_on_narrow_windows(qtbot, window):
    window.show()
    window.resize(COLLAPSE_BELOW + 100, 800)
    assert not window.sidebar.collapsed
    window.resize(MIN_WIDTH, 800)
    assert window.sidebar.collapsed


def test_toggles_map_to_options_and_persist(window, settings):
    rows = window.organize.option_rows
    ctx = window.context
    rows["video"].setChecked(False)
    rows["dateFolders"].setChecked(False)
    rows["cleanNames"].setChecked(True)
    rows["copy"].setChecked(True)
    assert ctx.options() == Options(date_folders=False, clean_names=True, probe=False)
    assert ctx.mode() is Mode.COPY

    rows["video"].setChecked(True)
    rows["copy"].setChecked(False)
    assert ctx.options().probe is True
    assert ctx.mode() is Mode.MOVE
    assert settings.value("options/cleanNames", type=bool) is True
    assert settings.value("options/dateFolders", type=bool) is False


def test_toggle_row_label_click_toggles_and_space_works(qtbot, window):
    window.show()
    row = window.organize.option_rows["cleanNames"]
    before = row.isChecked()
    qtbot.mouseClick(row.title_label, Qt.MouseButton.LeftButton)
    assert row.isChecked() is not before
    row.switch.setFocus()
    qtbot.keyClick(row.switch, Qt.Key.Key_Space)
    assert row.isChecked() is before


def test_settings_restore_folders_and_options(make_window, settings, tmp_path):
    settings.setValue("paths/source", str(tmp_path))
    settings.setValue("options/cleanNames", True)
    window = make_window()
    assert window.organize.source_field.text() == str(tmp_path)
    assert window.organize.option_rows["cleanNames"].isChecked()


def test_video_toggle_disabled_without_ffprobe(make_window, settings):
    window = make_window(ffprobe=None)
    video = window.organize.option_rows["video"]
    notice = window.organize.ffmpeg_notice
    assert not video.isEnabled()
    assert window.context.options().probe is False
    assert "FFmpeg" in video.toolTip()
    assert notice.isVisibleTo(window)
    assert window.sidebar.status.dot.tone == "warn"

    window.organize.dismiss_button.click()
    assert not notice.isVisibleTo(window)
    assert settings.value("ffmpeg/bannerDismissed", type=bool) is True
    # Remembered: the next launch does not nag again.
    again = make_window(ffprobe=None)
    assert not again.organize.ffmpeg_notice.isVisibleTo(again)


def test_video_preference_survives_missing_ffprobe(make_window, settings):
    settings.setValue("options/video", True)
    window = make_window(ffprobe=None)
    window.organize.option_rows["video"].setChecked(False)
    assert settings.value("options/video", type=bool) is True


def test_appearance_choice_applies_and_persists(window, settings):
    window.settings_page.set_appearance("light")
    assert theme.manager().mode is theme.Appearance.LIGHT
    assert theme.current() is theme.LIGHT
    assert settings.value(theme.SETTINGS_KEY) == "light"
    window.settings_page.set_appearance("dark")
    assert theme.current() is theme.DARK
    window.settings_page.set_appearance("system")


# ------------------------------------------------------------------ validation


def test_organize_disabled_until_folders_are_valid(window, make_tree, tmp_path):
    page = window.organize
    src = make_tree(["a.png"])
    assert not page.organize_button.isEnabled()

    page.source_field.set_text(str(src))
    assert not page.organize_button.isEnabled()

    page.output_field.set_text(str(src))
    assert not page.organize_button.isEnabled()
    assert page.output_field.tone() == "error"
    assert "different" in page.output_field.status.text()

    page.output_field.set_text(str(tmp_path / "new-output"))
    assert page.organize_button.isEnabled()
    assert "created" in page.output_field.status.text()

    page.source_field.set_text(str(tmp_path / "missing"))
    assert not page.organize_button.isEnabled()
    assert page.source_field.tone() == "error"


def test_output_inside_source_warns_but_is_allowed(window, make_tree):
    src = make_tree(["a.png"])
    set_folders(window, src, src / "sorted")
    assert window.organize.organize_button.isEnabled()
    assert window.organize.output_field.tone() == "warn"


def test_relative_paths_are_rejected(window):
    window.organize.source_field.set_text("relative/inbox")
    assert window.organize.source_field.tone() == "error"
    assert not window.organize.organize_button.isEnabled()


# --------------------------------------------------------------------- flows


def test_preview_then_organize_then_undo(qtbot, window, make_tree, tmp_path, monkeypatch):
    page = window.organize
    src = make_tree(["a.png", "b_music.mp3", "clip_vert.mp4", "notes.txt"])
    out = tmp_path / "out"
    page.option_rows["dateFolders"].setChecked(False)
    set_folders(window, src, out)

    shown = []

    class AcceptingDialog:
        def __init__(self, plan):
            shown.append(plan)

        def exec(self):
            return 1  # QDialog.DialogCode.Accepted

    monkeypatch.setattr(page, "create_preview_dialog", AcceptingDialog)
    window.start_organize()
    qtbot.waitUntil(lambda: page.last_result is not None, timeout=10_000)
    wait_idle(qtbot, window)

    assert len(shown[0]) == 4
    assert files_under(src) == []
    assert files_under(out) == [
        "Images/a.png",
        "Music/b_music.mp3",
        "Other/notes.txt",
        "VerticalVideos/clip_vert.mp4",
    ]
    assert page.activity.status_title.text() == "Complete"
    assert page.activity.review_link.isVisibleTo(window)  # notes.txt landed in Other
    qtbot.waitUntil(lambda: window.sidebar.items[REVIEW].badge == 1, timeout=5_000)
    assert len(page.recent.records) == 1 and page.recent.undo_link.isVisibleTo(window)
    qtbot.waitUntil(
        lambda: window.library.stats is not None and window.library.stats.total == 4,
        timeout=5_000,
    )

    page.activity.review_link.click()
    assert window.current_page() == REVIEW

    page.confirm_undo()  # the confirmation box is auto-answered "Yes" in tests
    wait_idle(qtbot, window)
    assert files_under(src) == ["a.png", "b_music.mp3", "clip_vert.mp4", "notes.txt"]
    assert page.activity.status_title.text() == "Undo complete"
    qtbot.waitUntil(lambda: not page.recent.records, timeout=5_000)
    qtbot.waitUntil(lambda: window.sidebar.items[REVIEW].badge == 0, timeout=5_000)


def test_closing_the_preview_changes_nothing(qtbot, window, make_tree, tmp_path, monkeypatch):
    page = window.organize
    src = make_tree(["a.png"])
    set_folders(window, src, tmp_path / "out")

    class RejectingDialog:
        def __init__(self, plan):
            pass

        def exec(self):
            return 0

    monkeypatch.setattr(page, "create_preview_dialog", RejectingDialog)
    page.start_organize()
    qtbot.waitUntil(lambda: "No files were changed" in page.activity.detail.text(), timeout=5_000)
    assert files_under(src) == ["a.png"]
    assert not (tmp_path / "out").exists()


def test_run_reports_progress_and_can_be_cancelled(qtbot, window, make_tree, tmp_path, config):
    page = window.organize
    src = make_tree([f"img_{i:02}.png" for i in range(25)])
    out = tmp_path / "out"
    page.output_field.set_text(str(out))
    plan = build_plan(src, out, NO_PROBE, config=config)

    task = page.start_execute(plan, Mode.MOVE)
    assert window.is_busy and page.activity.cancel_button.isVisibleTo(window)
    assert not page.organize_button.isEnabled()
    # Cancel synchronously on the worker thread after the first file, deterministically.
    task.progressed.connect(lambda _event: task.cancel(), Qt.ConnectionType.DirectConnection)
    wait_idle(qtbot, window)

    result = page.last_result
    assert result is not None and result.stats.cancelled
    assert 1 <= result.stats.moved < 25
    assert page.activity.status_title.text() == "Cancelled"
    assert "not processed" in page.activity.detail.text()
    assert not page.activity.cancel_button.isVisibleTo(window)
    assert len(files_under(out)) == result.stats.moved
    assert list_journals(out), "the partial run must still be undoable"


def test_completion_shows_errors_and_duplicates(qtbot, window, make_tree, tmp_path, config):
    activity = window.organize.activity
    src = make_tree({"a.png": "same", "b.png": "other"})
    out = tmp_path / "out"
    (out / "Images").mkdir(parents=True)
    (out / "Images" / "a.png").write_text("same")
    window.organize.output_field.set_text(str(out))
    plan = build_plan(src, out, NO_PROBE, config=config)
    window.organize.start_execute(plan, Mode.MOVE)
    wait_idle(qtbot, window)
    assert "1 duplicate skipped" in activity.detail.text()
    assert activity.details_button.isVisibleTo(window)
    activity.details_button.click()
    assert activity.details.isVisibleTo(window)
    assert "a.png" in activity.details.toPlainText()


# --------------------------------------------------------------------- library


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


def test_library_shows_empty_state_without_output(window):
    library = window.library
    assert library.stack.currentWidget() is library.empty
    assert not library.refresh_button.isEnabled()
    library.empty.action_button.click()
    assert window.current_page() == ORGANIZE


def test_library_loads_stats_in_background(qtbot, window, tmp_path):
    library = window.library
    out = make_library(tmp_path / "lib")
    window.organize.output_field.set_text(str(out))
    library.refresh()
    qtbot.waitUntil(lambda: library.stats is not None, timeout=5_000)
    assert library.stack.currentIndex() == 1
    assert library.total_tile.value() == "4"
    assert library.breakdown.count(Category.VERTICAL) == 2
    assert library.breakdown.rows() == [
        Category.VERTICAL,
        Category.HORIZONTAL,
        Category.IMAGES,
    ]
    keys = [key for key, _ in library.chart.series]
    assert keys[:2] == [(2023, 12), (2024, 1)]  # chronological, years kept apart


def test_chart_click_opens_the_right_month_folders(qtbot, window, tmp_path, monkeypatch):
    library = window.library
    out = make_library(tmp_path / "lib")
    window.organize.output_field.set_text(str(out))
    library.refresh()
    qtbot.waitUntil(lambda: library.stats is not None, timeout=5_000)

    opened: list[Path] = []
    monkeypatch.setattr(library, "open_path", lambda p: opened.append(p) or True)
    library.open_month(2023, 12)
    assert opened == [out.resolve() / "VerticalVideos" / "2023" / "12 - December"]

    january = library.folders_for_month(2024, 1)
    assert {p.parts[-3] for p in january} == {"VerticalVideos", "HorizontalVideos"}
    menu = library._month_menu(january)
    labels = [a.text() for a in menu.actions() if a.text()]
    assert "Open all" in labels and len(labels) == 3

    opened.clear()
    with qtbot.waitSignal(library.statusMessage):
        library.open_month(1999, 1)  # no folder for that month: a status message, no crash
    assert opened == []
