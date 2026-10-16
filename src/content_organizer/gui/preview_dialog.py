"""Dry-run preview: every planned move in a filterable table; the user confirms or backs out."""

from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from content_organizer.categories import Category
from content_organizer.executor import Mode
from content_organizer.gui import icons, theme
from content_organizer.gui.presenters import plan_summary, plan_warnings, plural
from content_organizer.gui.widgets import Card, FlowLayout, Notice, button, label
from content_organizer.gui.widgets.plan_table import (
    PlanFilterModel,
    PlanTableModel,
    build_plan_table,
)
from content_organizer.planner import Plan


class PreviewDialog(QDialog):
    """Shows a :class:`Plan`. ``exec()`` returns Accepted when the user confirms."""

    def __init__(self, plan: Plan, mode: Mode, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Preview")  # Qt appends the app display name
        self.setMinimumSize(860, 520)
        self.resize(1100, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(2 * theme.SPACE)
        layout.addLayout(self._build_header(mode))
        for warning in plan_warnings(plan):
            layout.addWidget(Notice(warning))
        layout.addLayout(self._build_filters())

        self.model = PlanTableModel(plan, self)
        self.proxy = PlanFilterModel(self)
        self.proxy.setSourceModel(self.model)
        self.table = build_plan_table(self.proxy)
        table_card = Card(margins=(1, 1, 1, 1))
        table_card.body.addWidget(self.table)
        layout.addWidget(table_card, 1)
        layout.addLayout(self._build_buttons(mode))

    def _build_header(self, mode: Mode) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(label("Preview" if self.plan.moves else "Nothing to organize", "title"))
        action = "copied" if mode is Mode.COPY else "moved"
        if self.plan.moves:
            text = (
                f"{plan_summary(self.plan)}. No files have been changed yet; review the "
                f"list, then confirm. Files will be {action} into {self.plan.output}."
            )
        else:
            text = f"No files were found in {self.plan.source} (hidden and skipped files ignored)."
        column.addWidget(label(text, "muted", wrap=True))
        return column

    def _build_filters(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(theme.SPACE)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by file name or path…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Filter by file name")
        self.search.addAction(
            QAction(icons.icon("search", theme.current().text_faint), "", self.search),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search.textChanged.connect(lambda text: self.proxy.set_text(text.strip()))
        column.addWidget(self.search)

        chips = QWidget()
        flow = FlowLayout(chips)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_buttons: dict[str | None, QPushButton] = {}
        counts = self.plan.counts()
        entries: list[tuple[str | None, str]] = [(None, f"All  {len(self.plan):,}")]
        entries += [(c.value, f"{c.label}  {counts[c]:,}") for c in Category if counts.get(c)]
        for value, text in entries:
            chip = QPushButton(text)
            chip.setProperty("chip", True)
            chip.setCheckable(True)
            chip.clicked.connect(lambda _=False, v=value: self.set_category_filter(v))
            self.filter_group.addButton(chip)
            self.filter_buttons[value] = chip
            flow.addWidget(chip)
        self.filter_buttons[None].setChecked(True)
        column.addWidget(chips)
        return column

    def _build_buttons(self, mode: Mode) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE)
        self.count_label = label("", "caption")
        row.addWidget(self.count_label, 1)
        self.back_button = button(
            "Back", variant="ghost", tooltip="Close the preview without changing any files"
        )
        self.back_button.clicked.connect(self.reject)
        row.addWidget(self.back_button)
        verb = "Copy" if mode is Mode.COPY else "Organize"
        self.confirm_button = button(
            f"{verb} {plural(len(self.plan), 'file')}", "play", variant="primary", size="lg"
        )
        self.confirm_button.setEnabled(len(self.plan) > 0)
        self.confirm_button.setDefault(len(self.plan) > 0)
        self.confirm_button.clicked.connect(self.accept)
        row.addWidget(self.confirm_button)
        self.proxy.rowsInserted.connect(self._update_count)
        self.proxy.rowsRemoved.connect(self._update_count)
        self.proxy.modelReset.connect(self._update_count)
        self.proxy.layoutChanged.connect(self._update_count)
        self._update_count()
        return row

    def set_category_filter(self, value: str | None) -> None:
        self.proxy.set_category(value)
        self.filter_buttons[value].setChecked(True)
        self._update_count()

    def _update_count(self) -> None:
        shown = self.proxy.rowCount()
        total = len(self.plan)
        if shown == total:
            self.count_label.setText(f"Showing {plural(total, 'file')}")
        else:
            self.count_label.setText(f"Showing {shown:,} of {total:,}")

    def visible_rows(self) -> int:
        return self.proxy.rowCount()
