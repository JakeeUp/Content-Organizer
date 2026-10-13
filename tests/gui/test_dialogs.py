"""Preview and review dialogs."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from content_organizer.categories import Category
from content_organizer.executor import Mode, list_journals, undo_last_run
from content_organizer.gui.preview_dialog import PreviewDialog
from content_organizer.gui.review_dialog import CATEGORY_KEYS, ReviewDialog
from content_organizer.planner import Options, Plan, PlannedMove


def fake_plan(root: Path) -> Plan:
    src, out = root / "inbox", root / "out"
    moves = [
        PlannedMove(src / "a.png", out / "Images" / "a.png", Category.IMAGES, "image"),
        PlannedMove(
            src / "sub" / "clip.mp4",
            out / "VerticalVideos" / "2024" / "03 - March" / "clip.mp4",
            Category.VERTICAL,
            "1080x1920 -> vertical",
        ),
        PlannedMove(src / "x.bin", out / "Other" / "x.bin", Category.OTHER, "unknown type"),
        PlannedMove(
            src / "b.png",
            out / "Images" / "b.png",
            Category.IMAGES,
            "image",
            possible_duplicate=True,
        ),
    ]
    return Plan(source=src, output=out, options=Options(), moves=moves, probe_available=True)


def cell(dialog: PreviewDialog, row: int, column: int) -> str:
    return dialog.proxy.data(dialog.proxy.index(row, column))


def test_preview_lists_planned_moves(qtbot, tmp_path):
    plan = fake_plan(tmp_path)
    dialog = PreviewDialog(plan, Mode.MOVE)
    qtbot.addWidget(dialog)

    assert dialog.visible_rows() == 4
    assert [dialog.model.headerData(c, Qt.Orientation.Horizontal) for c in range(4)] == [
        "Category",
        "Source",
        "Destination",
        "Reason",
    ]
    assert cell(dialog, 1, 0) == "Vertical Videos"
    assert Path(cell(dialog, 1, 1)) == Path("sub/clip.mp4")  # relative to the source
    assert Path(cell(dialog, 1, 2)) == Path("VerticalVideos/2024/03 - March/clip.mp4")
    assert "review" in cell(dialog, 2, 3)
    assert "possible duplicate" in cell(dialog, 3, 3)
    assert dialog.confirm_button.text() == "Organize 4 files"
    assert dialog.confirm_button.isEnabled()


def test_preview_filters(qtbot, tmp_path):
    dialog = PreviewDialog(fake_plan(tmp_path), Mode.COPY)
    qtbot.addWidget(dialog)
    assert dialog.confirm_button.text() == "Copy 4 files"

    index = dialog.category_filter.findData(Category.IMAGES.value)
    dialog.category_filter.setCurrentIndex(index)
    assert dialog.visible_rows() == 2
    dialog.search.setText("b.png")
    assert dialog.visible_rows() == 1
    dialog.category_filter.setCurrentIndex(0)
    dialog.search.clear()
    assert dialog.visible_rows() == 4


def test_preview_warns_when_ffprobe_missing_and_empty_plan(qtbot, tmp_path):
    plan = Plan(source=tmp_path / "in", output=tmp_path / "out", options=Options(probe=True))
    dialog = PreviewDialog(plan, Mode.MOVE)
    qtbot.addWidget(dialog)
    assert not dialog.confirm_button.isEnabled()
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert dialog.visible_rows() == 0
    assert "FFmpeg" in texts
    assert "Nothing to organize" in texts


def test_preview_accept_and_reject(qtbot, tmp_path):
    dialog = PreviewDialog(fake_plan(tmp_path), Mode.MOVE)
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.accepted):
        dialog.confirm_button.click()


# ---------------------------------------------------------------------- review


def test_review_empty_state(qtbot, tmp_path, config):
    out = tmp_path / "out"
    (out / "Images").mkdir(parents=True)
    (out / "Images" / "a.png").write_text("x")
    dialog = ReviewDialog(out, config)
    qtbot.addWidget(dialog)
    assert dialog.files == []
    assert dialog.stack.currentWidget() is dialog.empty_page
    assert dialog.empty_title.text() == "Nothing to review"
    assert "Videos" in dialog.empty_text.text() and "Other" in dialog.empty_text.text()


def test_review_steps_and_moves_through_core(qtbot, tmp_path, config):
    out = tmp_path / "out"
    dated = out / "Videos" / "2024" / "03 - March"
    dated.mkdir(parents=True)
    (dated / "clip.mp4").write_text("video")
    (out / "Other").mkdir()
    (out / "Other" / "notes.txt").write_text("text")

    dialog = ReviewDialog(out, config)
    qtbot.addWidget(dialog)
    assert dialog.stack.currentWidget() is dialog.review_page
    assert [p.name for p in dialog.files] == ["notes.txt", "clip.mp4"]
    assert dialog.position_label.text() == "File 1 of 2"
    # The file's own category is not offered; everything else is.
    assert not dialog.category_buttons[Category.OTHER].isEnabled()
    assert dialog.category_buttons[Category.IMAGES].isEnabled()
    assert len(dialog.category_buttons) == len(Category) == len(CATEGORY_KEYS)

    dialog.skip()
    assert dialog.current is not None and dialog.current.name == "clip.mp4"
    dialog.previous()
    assert dialog.current.name == "notes.txt"
    dialog.skip()

    with qtbot.waitSignal(dialog.fileMoved) as signal:
        dialog.categorize(Category.FINALIZED)
    moved = Path(signal.args[0])
    # Date sub-folders are kept when the target category uses them too.
    assert moved == out.resolve() / "FinalizedVideos" / "2024" / "03 - March" / "clip.mp4"
    assert moved.is_file()
    assert dialog.moved_count == 1
    assert list_journals(out), "review moves are journaled"
    assert [p.name for p in dialog.files] == ["notes.txt"]

    dialog.categorize(Category.PROJECTS)  # Other -> PremiereProjects
    assert (out / "PremiereProjects" / "notes.txt").is_file()
    assert dialog.stack.currentWidget() is dialog.empty_page
    assert dialog.empty_title.text() == "All done"

    undo_last_run(out)  # the most recent review move can be undone
    assert (out / "Other" / "notes.txt").is_file()


def test_review_keyboard_shortcut(qtbot, tmp_path, config):
    out = tmp_path / "out"
    (out / "Other").mkdir(parents=True)
    (out / "Other" / "song.xyz").write_text("x")
    dialog = ReviewDialog(out, config)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.activateWindow()
    qtbot.waitUntil(dialog.isActiveWindow)
    key = CATEGORY_KEYS[list(Category).index(Category.MUSIC)]
    qtbot.keyClick(dialog, key)
    assert (out / "Music" / "song.xyz").is_file()


def test_review_refuses_to_overwrite_identical_file(qtbot, tmp_path, config):
    out = tmp_path / "out"
    (out / "Other").mkdir(parents=True)
    (out / "Images").mkdir()
    (out / "Other" / "pic.dat").write_text("same")
    (out / "Images" / "pic.dat").write_text("same")
    dialog = ReviewDialog(out, config)
    qtbot.addWidget(dialog)
    dialog.categorize(Category.IMAGES)
    assert dialog.moved_count == 0
    assert "identical" in dialog.status_label.text()
    assert (out / "Other" / "pic.dat").is_file()
