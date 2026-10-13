"""Custom widgets: monthly chart, ring chart, toggle switch, category bars, folder field."""

from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QColor, QDropEvent

from content_organizer.categories import Category
from content_organizer.gui.widgets import (
    CategoryBars,
    FolderField,
    MonthlyChart,
    RingChart,
    Segment,
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
    xs = [p.x() for p in chart.point_positions()]
    assert xs == sorted(xs)


def test_chart_click_emits_year_and_month(qtbot):
    chart = shown_chart(qtbot)
    point = chart.point_positions()[1]
    with qtbot.waitSignal(chart.monthClicked) as signal:
        qtbot.mouseClick(chart, Qt.MouseButton.LeftButton, pos=point.toPoint())
    assert signal.args == [2024, 1]


def test_chart_click_far_from_points_does_nothing(qtbot):
    chart = MonthlyChart()
    qtbot.addWidget(chart)
    chart.resize(600, 260)
    chart.set_series([((2024, 5), 1)])  # a single centred point
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
    assert chart.point_positions() == []
    assert chart.index_at(100) == -1
    assert not chart.grab().isNull()
    chart.set_series([((2020 + i // 12, i % 12 + 1), i) for i in range(60)])  # dense data
    assert not chart.grab().isNull()


def test_ring_replaces_segments(qtbot):
    ring = RingChart()
    qtbot.addWidget(ring)
    ring.set_segments([Segment("A", 3, QColor("red")), Segment("B", 0, QColor("blue"))])
    assert ring.total == 3 and len(ring.segments) == 1
    ring.set_segments([Segment("C", 10, QColor("green"))])
    assert ring.total == 10 and [s.label for s in ring.segments] == ["C"]
    ring.clear()
    assert ring.total == 0
    assert not ring.grab().isNull()


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


def test_category_bars_show_every_category(qtbot):
    bars = CategoryBars()
    qtbot.addWidget(bars)
    bars.set_counts(Counter({Category.VERTICAL: 3, Category.OTHER: 1}))
    assert bars.count_text(Category.VERTICAL) == "3"
    assert bars.count_text(Category.MUSIC) == "0"
    assert bars._bars[Category.VERTICAL].value() == 750  # share of the grand total


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
