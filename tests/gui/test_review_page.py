"""The Review page: steps through review folders and files moves through the core."""

from __future__ import annotations

from pathlib import Path

from content_organizer.categories import Category
from content_organizer.executor import list_journals, undo_last_run
from content_organizer.gui.main_window import REVIEW
from content_organizer.gui.pages.review import CATEGORY_KEYS


def open_review(window, out: Path):
    window.organize.output_field.set_text(str(out))
    window.show_page(REVIEW)
    return window.review


def test_review_without_output_points_to_organize(window):
    page = window.review
    assert page.stack.currentWidget() is page.empty
    assert page.empty.title_label.text() == "No output folder"
    page.empty.action_button.click()
    assert window.current_page() == 0


def test_review_empty_state(window, tmp_path):
    out = tmp_path / "out"
    (out / "Images").mkdir(parents=True)
    (out / "Images" / "a.png").write_text("x")
    page = open_review(window, out)
    assert page.files == []
    assert page.stack.currentWidget() is page.empty
    assert page.empty.title_label.text() == "Nothing to review"
    text = page.empty.text_label.text()
    assert "Videos" in text and "Other" in text


def test_review_steps_and_moves_through_core(qtbot, window, tmp_path):
    out = tmp_path / "out"
    dated = out / "Videos" / "2024" / "03 - March"
    dated.mkdir(parents=True)
    (dated / "clip.mp4").write_text("video")
    (out / "Other").mkdir()
    (out / "Other" / "notes.txt").write_text("text")

    page = open_review(window, out)
    assert page.stack.currentWidget() is page.review_view
    assert [p.name for p in page.files] == ["notes.txt", "clip.mp4"]
    assert page.position_label.text() == "File 1 of 2"
    assert page.preview.mode == "tile"
    # The file's own category is not offered; everything else is.
    assert not page.category_buttons[Category.OTHER].isEnabled()
    assert page.category_buttons[Category.IMAGES].isEnabled()
    assert len(page.category_buttons) == len(Category) == len(CATEGORY_KEYS)

    page.skip()
    assert page.current is not None and page.current.name == "clip.mp4"
    page.previous()
    assert page.current.name == "notes.txt"
    page.skip()

    with qtbot.waitSignal(page.fileMoved) as signal:
        page.categorize(Category.FINALIZED)
    moved = Path(signal.args[0])
    # Date sub-folders are kept when the target category uses them too.
    assert moved == out.resolve() / "FinalizedVideos" / "2024" / "03 - March" / "clip.mp4"
    assert moved.is_file()
    assert page.moved_count == 1
    assert list_journals(out), "review moves are journaled"
    assert [p.name for p in page.files] == ["notes.txt"]

    page.categorize(Category.PROJECTS)  # Other -> PremiereProjects
    assert (out / "PremiereProjects" / "notes.txt").is_file()
    assert page.stack.currentWidget() is page.empty
    assert page.empty.title_label.text() == "All done"
    qtbot.waitUntil(lambda: window.sidebar.items[REVIEW].badge == 0, timeout=5_000)

    undo_last_run(out)  # the most recent review move can be undone
    assert (out / "Other" / "notes.txt").is_file()


def test_review_keyboard_shortcut(qtbot, window, tmp_path):
    out = tmp_path / "out"
    (out / "Other").mkdir(parents=True)
    (out / "Other" / "song.xyz").write_text("x")
    window.show()
    page = open_review(window, out)
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    page.setFocus()
    key = CATEGORY_KEYS[list(Category).index(Category.MUSIC)]
    qtbot.keyClick(page, key)
    assert (out / "Music" / "song.xyz").is_file()


def test_review_refuses_to_overwrite_identical_file(window, tmp_path):
    out = tmp_path / "out"
    (out / "Other").mkdir(parents=True)
    (out / "Images").mkdir()
    (out / "Other" / "pic.dat").write_text("same")
    (out / "Images" / "pic.dat").write_text("same")
    page = open_review(window, out)
    page.categorize(Category.IMAGES)
    assert page.moved_count == 0
    assert "identical" in page.status_label.text()
    assert (out / "Other" / "pic.dat").is_file()
