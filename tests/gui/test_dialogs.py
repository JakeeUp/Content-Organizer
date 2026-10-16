"""The dry-run preview dialog."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from content_organizer.categories import Category
from content_organizer.executor import Mode
from content_organizer.gui.preview_dialog import PreviewDialog
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
        "File",
        "Destination",
        "Reason",
    ]
    assert cell(dialog, 1, 0) == "Vertical Videos"
    assert Path(cell(dialog, 1, 1)) == Path("sub/clip.mp4")  # relative to the source
    # The destination is the folder; the name is only repeated when it changes.
    assert Path(cell(dialog, 1, 2)) == Path("VerticalVideos/2024/03 - March")
    assert "needs review" in cell(dialog, 2, 3)
    assert "possible duplicate" in cell(dialog, 3, 3)
    assert dialog.confirm_button.text() == "Organize 4 files"
    assert dialog.confirm_button.isEnabled()


def test_preview_filters(qtbot, tmp_path):
    dialog = PreviewDialog(fake_plan(tmp_path), Mode.COPY)
    qtbot.addWidget(dialog)
    assert dialog.confirm_button.text() == "Copy 4 files"

    assert set(dialog.filter_buttons) == {
        None,
        Category.IMAGES.value,
        Category.VERTICAL.value,
        Category.OTHER.value,
    }
    dialog.filter_buttons[Category.IMAGES.value].click()
    assert dialog.visible_rows() == 2
    assert dialog.count_label.text() == "Showing 2 of 4"
    dialog.search.setText("b.png")
    assert dialog.visible_rows() == 1
    dialog.filter_buttons[None].click()
    dialog.search.clear()
    assert dialog.visible_rows() == 4
    assert dialog.count_label.text() == "Showing 4 files"


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
    with qtbot.waitSignal(dialog.rejected):
        dialog.back_button.click()
