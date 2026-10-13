"""Per-category rows: colour dot, label, count and a share-of-total bar."""

from __future__ import annotations

from collections.abc import Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QLabel, QProgressBar, QWidget

from content_organizer.categories import Category
from content_organizer.gui import theme


class CategoryBars(QWidget):
    """Shows **every** category; bar widths are shares of the grand total (sum = 100%)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(2, 1)
        self._counts: dict[Category, QLabel] = {}
        self._bars: dict[Category, QProgressBar] = {}
        for row, category in enumerate(Category):
            color = theme.CATEGORY_COLORS[category]
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
            label = QLabel(category.label)
            label.setToolTip(f"Folder: {category.value}")
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setMinimumWidth(36)
            bar.setStyleSheet(
                "QProgressBar { min-height: 8px; max-height: 8px; border-radius: 4px; }"
                f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
            )
            count = QLabel("0")
            count.setObjectName("statValue")
            count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            count.setMinimumWidth(36)
            grid.addWidget(dot, row, 0)
            grid.addWidget(label, row, 1)
            grid.addWidget(bar, row, 2)
            grid.addWidget(count, row, 3)
            self._counts[category] = count
            self._bars[category] = bar

    def set_counts(self, counts: Mapping[Category, int]) -> None:
        total = sum(counts.values())
        for category in Category:
            value = counts.get(category, 0)
            self._counts[category].setText(f"{value:,}")
            share = value / total if total else 0.0
            self._bars[category].setValue(round(share * 1000))
            self._bars[category].setToolTip(f"{category.label}: {value:,} ({share:.0%})")

    def count_text(self, category: Category) -> str:
        return self._counts[category].text()
