"""Custom widgets: chart, breakdown, toggle, folder field, sidebar, segmented, preview."""

from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QDropEvent, QImage

from content_organizer.categories import Category, MediaType
from content_organizer.gui.presenters import RunRecord
from content_organizer.gui.widgets import (
    CategoryBreakdown,
    FilePreview,
    FolderField,
    MonthlyChart,
    RecentRuns,
    SegmentedControl,
    Sidebar,
    ToggleSwitch,
)

SERIES = [((2024, 1), 5), ((2023, 12), 3), ((2024, 2), 7)]  # deliberately unsorted


def shown_chart(qtbot) -> MonthlyChart:
    chart = MonthlyChart()
    qtbot.addWidget(chart)
    chart.resize(600, 260)
    chart.set_series(SERIES)
    chart.show()
    qtbot.waitExposed(chart)
    return chart


def test_chart_orders_months_chronologically_across_years(qtbot):
    chart = shown_chart(qtbot)
    assert [key for key, _ in chart.series] == [(2023, 12), (2024, 1), (2024, 2)]
    xs = [p.x() for p in chart.bar_centers()]
    assert xs == sorted(xs)


def test_chart_click_emits_year_and_month(qtbot):
    chart = shown_chart(qtbot)
    point = chart.bar_centers()[1]
    with qtbot.waitSignal(chart.monthClicked) as signal:
        qtbot.mouseClick(chart, Qt.MouseButton.LeftButton, pos=point.toPoint())
    assert signal.args == [2024, 1]


def test_chart_click_outside_the_plot_does_nothing(qtbot):
    chart = MonthlyChart()
    qtbot.addWidget(chart)
    chart.resize(600, 260)
    chart.set_series([((2024, 5), 1)])
    with qtbot.assertNotEmitted(chart.monthClicked):
        qtbot.mouseClick(chart, Qt.MouseButton.LeftButton, pos=QPointF(5, 5).toPoint())


def test_chart_keyboard_navigation(qtbot):
    chart = shown_chart(qtbot)
    chart.setFocus()
    qtbot.keyClick(chart, Qt.Key.Key_Right)
    qtbot.keyClick(chart, Qt.Key.Key_Right)
    assert chart.hover_index == 1
    with qtbot.waitSignal(chart.monthClicked) as signal:
        qtbot.keyClick(chart, Qt.Key.Key_Return)
    assert signal.args == [2024, 1]


def test_chart_empty_state_and_render(qtbot):
    chart = MonthlyChart()
    qtbot.addWidget(chart)
    chart.resize(400, 220)
    chart.set_series([], "Nothing here")
    assert chart.bar_rects() == []
    assert chart.index_at(100) == -1
    assert not chart.grab().isNull()
    chart.set_series([((2020 + i // 12, i % 12 + 1), i) for i in range(60)])  # dense data
    assert not chart.grab().isNull()


def test_toggle_switch_emits_and_is_keyboard_accessible(qtbot):
    switch = ToggleSwitch(checked=False)
    qtbot.addWidget(switch)
    switch.show()
    with qtbot.waitSignal(switch.toggled) as signal:
        switch.setChecked(True)
    assert signal.args == [True]
    switch.setFocus()
    qtbot.keyClick(switch, Qt.Key.Key_Space)
    assert not switch.isChecked()
    qtbot.mouseClick(switch, Qt.MouseButton.RightButton)
    assert not switch.isChecked(), "right-click must not toggle"
    qtbot.mouseClick(switch, Qt.MouseButton.LeftButton)
    assert switch.isChecked()


def test_category_breakdown_lists_non_empty_categories(qtbot):
    breakdown = CategoryBreakdown()
    qtbot.addWidget(breakdown)
    breakdown.set_counts(Counter({Category.OTHER: 1, Category.VERTICAL: 3, Category.MUSIC: 0}))
    assert breakdown.rows() == [Category.VERTICAL, Category.OTHER]  # Category order
    assert breakdown.total == 4 and breakdown.count(Category.MUSIC) == 0
    assert "Vertical Videos: 3" in breakdown.toolTip()
    breakdown.resize(400, breakdown.sizeHint().height())
    assert not breakdown.grab().isNull()
    breakdown.set_counts({})
    assert breakdown.rows() == [] and not breakdown.grab().isNull()


def test_folder_field_accepts_dropped_folder(qtbot, tmp_path):
    field = FolderField("Source folder", "hint", "Pick")
    qtbot.addWidget(field)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path))])
    event = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    with qtbot.waitSignal(field.pathChanged):
        field.edit.dropEvent(event)
    assert field.text() == str(tmp_path)


def test_folder_field_status_drives_tone_and_step(qtbot):
    field = FolderField("Output folder", "hint", "Pick", step=2)
    qtbot.addWidget(field)
    assert field.property("dropzone") == "empty"
    field.set_status("error", "Folder not found.")
    assert field.tone() == "error" and field.edit.property("validity") == "error"
    assert field.step_label.property("done") == "false"
    field.set_status("ok", "Ready.")
    assert field.step_label.property("done") == "true"
    field.set_text("C:/somewhere")
    assert field.property("dropzone") == "set"


def test_sidebar_items_badges_and_collapse(qtbot):
    sidebar = Sidebar("1.0")
    qtbot.addWidget(sidebar)
    items = [sidebar.add_item(name, "folder", f"Ctrl+{i}") for i, name in enumerate("ABC")]
    with qtbot.waitSignal(sidebar.pageRequested) as signal:
        items[2].click()
    assert signal.args == [2] and sidebar.current() == 2
    items[1].set_badge(1234)
    assert items[1].badge == 1234 and "1234 waiting" in items[1].accessibleDescription()
    sidebar.set_collapsed(True)
    assert all(item.collapsed for item in items)
    assert not sidebar.brand_label.isVisibleTo(sidebar)
    assert not sidebar.grab().isNull()


def test_segmented_control_keyboard_and_value(qtbot):
    control = SegmentedControl([("a", "A", "sun"), ("b", "B", "moon"), ("c", "C", "monitor")])
    qtbot.addWidget(control)
    control.show()
    control.set_value("b")
    assert control.value() == "b"
    control.setFocus()
    with qtbot.waitSignal(control.changed) as signal:
        qtbot.keyClick(control, Qt.Key.Key_Right)
    assert signal.args == ["c"]
    qtbot.keyClick(control, Qt.Key.Key_Right)  # clamps at the end
    assert control.value() == "c"


def test_file_preview_image_and_tile(qtbot, tmp_path):
    preview = FilePreview()
    qtbot.addWidget(preview)
    preview.resize(300, 240)
    image = QImage(40, 20, QImage.Format.Format_RGB32)
    image.fill(0x336699)
    path = tmp_path / "pic.png"
    image.save(str(path))
    preview.show_file(path, MediaType.IMAGE)
    assert preview.mode == "image"
    assert not preview.grab().isNull()
    preview.show_file(tmp_path / "clip.mp4", MediaType.VIDEO)
    assert preview.mode == "tile" and "video" in preview.toolTip()
    assert not preview.grab().isNull()


def test_recent_runs_lists_newest_with_undo(qtbot, tmp_path):
    runs = RecentRuns()
    qtbot.addWidget(runs)
    runs.show()
    assert not runs.undo_link.isVisibleTo(runs) and runs.empty_label.isVisibleTo(runs)
    record = RunRecord(tmp_path / "j.jsonl", None, "move", 3, str(tmp_path))
    runs.set_records([record, record])
    assert runs.records == [record, record]
    assert runs.undo_link.isVisibleTo(runs) and not runs.empty_label.isVisibleTo(runs)
    assert record.title == "Moved 3 files"
