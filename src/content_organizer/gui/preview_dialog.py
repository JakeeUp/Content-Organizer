"""Dry-run preview: every planned move in a filterable table; the user confirms or backs out."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from content_organizer.categories import Category
from content_organizer.executor import Mode
from content_organizer.gui import icons, theme
from content_organizer.gui.presenters import plan_summary, plan_warnings
from content_organizer.gui.widgets.flow_layout import FlowLayout
from content_organizer.planner import Plan, PlannedMove

_Index = QModelIndex | QPersistentModelIndex
CATEGORY_ROLE = Qt.ItemDataRole.UserRole + 1


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


class PlanTableModel(QAbstractTableModel):
    """Read-only table over ``plan.moves``."""

    HEADERS = ("Category", "Source", "Destination", "Reason")

    def __init__(self, plan: Plan, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plan = plan
        self._moves: list[PlannedMove] = list(plan.moves)

    def rowCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._moves)

    def columnCount(self, parent: _Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def move_at(self, row: int) -> PlannedMove:
        return self._moves[row]

    def data(self, index: _Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        move = self._moves[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(move, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{move.src}\n→ {move.dest}\n{move.reason}"
        if role == Qt.ItemDataRole.ForegroundRole and column == 0:
            return QColor(theme.CATEGORY_COLORS[move.category])
        if role == Qt.ItemDataRole.ForegroundRole and column == 3 and move.needs_review:
            return QColor(theme.AMBER)
        if role == CATEGORY_ROLE:
            return move.category.value
        return None

    def _display(self, move: PlannedMove, column: int) -> str:
        if column == 0:
            return move.category.label
        if column == 1:
            return _relative(move.src, self._plan.source)
        if column == 2:
            return _relative(move.dest, self._plan.output)
        notes = [move.reason]
        if move.needs_review:
            notes.append("review")
        if move.possible_duplicate:
            notes.append("possible duplicate")
        return " · ".join(notes)


class PlanFilterModel(QSortFilterProxyModel):
    """Filters by category (combo) and free text over source/destination."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._category: str | None = None
        self._needle = ""

    def set_category(self, value: str | None) -> None:
        self._category = value
        self.invalidateFilter()

    def set_text(self, text: str) -> None:
        self._needle = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        if self._category is not None:
            index = model.index(source_row, 0, source_parent)
            if model.data(index, CATEGORY_ROLE) != self._category:
                return False
        if not self._needle:
            return True
        text = " ".join(str(model.data(model.index(source_row, c, source_parent))) for c in (1, 2))
        return self._needle in text.lower()


def _chip(category: Category, count: int) -> QFrame:
    chip = QFrame()
    chip.setObjectName("chip")
    row = QHBoxLayout(chip)
    row.setContentsMargins(10, 6, 12, 6)
    row.setSpacing(8)
    dot = QLabel()
    dot.setFixedSize(9, 9)
    dot.setStyleSheet(f"background-color: {theme.CATEGORY_COLORS[category]}; border-radius: 4px;")
    row.addWidget(dot)
    text = QLabel(f"{category.label}  <b>{count:,}</b>")
    row.addWidget(text)
    return chip


class PreviewDialog(QDialog):
    """Shows a :class:`Plan`. ``exec()`` returns Accepted when the user confirms."""

    def __init__(self, plan: Plan, mode: Mode, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Preview")  # Qt appends the app display name
        self.setMinimumSize(860, 520)
        self.resize(1100, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(self._build_header(mode))
        layout.addWidget(self._build_chips())
        for warning in plan_warnings(plan):
            layout.addWidget(self._warning(warning))
        layout.addLayout(self._build_filters())

        self.model = PlanTableModel(plan, self)
        self.proxy = PlanFilterModel(self)
        self.proxy.setSourceModel(self.model)
        self.table = self._build_table()
        layout.addWidget(self.table, 1)

        self.buttons = QDialogButtonBox()
        verb = "Copy" if mode is Mode.COPY else "Organize"
        self.confirm_button = self.buttons.addButton(
            f"{verb} {len(plan):,} file{'s' if len(plan) != 1 else ''}",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        assert self.confirm_button is not None
        self.confirm_button.setObjectName("primary")
        self.confirm_button.setIcon(icons.icon("play", "#FFFFFF"))
        self.confirm_button.setEnabled(len(plan) > 0)
        self.confirm_button.setDefault(len(plan) > 0)
        back = self.buttons.addButton("Back", QDialogButtonBox.ButtonRole.RejectRole)
        assert back is not None
        back.setToolTip("Close the preview without changing any files")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _build_header(self, mode: Mode) -> QWidget:
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        title = QLabel("Preview" if self.plan.moves else "Nothing to organize")
        title.setObjectName("statusTitle")
        column.addWidget(title)
        action = "copied" if mode is Mode.COPY else "moved"
        if self.plan.moves:
            text = (
                f"{plan_summary(self.plan)}. No files have been changed yet; review the "
                f"list, then confirm. Files will be {action} into {self.plan.output}."
            )
        else:
            text = f"No files were found in {self.plan.source} (hidden and skipped files ignored)."
        summary = QLabel(text)
        summary.setObjectName("cardSubtitle")
        summary.setWordWrap(True)
        column.addWidget(summary)
        return box

    def _build_chips(self) -> QWidget:
        box = QWidget()
        flow = FlowLayout(box)
        counts = self.plan.counts()
        for category in Category:
            if counts.get(category):
                flow.addWidget(_chip(category, counts[category]))
        return box

    def _warning(self, text: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("banner")
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 8, 12, 8)
        icon = QLabel()
        icon.setPixmap(icons.icon("warning", theme.AMBER).pixmap(18, 18))
        row.addWidget(icon)
        label = QLabel(text)
        label.setObjectName("bannerText")
        label.setWordWrap(True)
        row.addWidget(label, 1)
        return frame

    def _build_filters(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.category_filter = QComboBox()
        self.category_filter.setAccessibleName("Filter by category")
        self.category_filter.addItem("All categories", None)
        counts = self.plan.counts()
        for category in Category:
            if counts.get(category):
                self.category_filter.addItem(
                    f"{category.label} ({counts[category]})", category.value
                )
        self.category_filter.currentIndexChanged.connect(self._category_changed)
        row.addWidget(self.category_filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by file name or path…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Filter by file name")
        self.search.textChanged.connect(self._search_changed)
        row.addWidget(self.search, 1)
        return row

    def _build_table(self) -> QTableView:
        table = QTableView()
        table.setModel(self.proxy)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(True)
        table.setWordWrap(False)
        table.setShowGrid(False)
        table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        table.setToolTip("Hover a row for full paths; click a header to sort")
        vertical = table.verticalHeader()
        if vertical is not None:
            vertical.setVisible(False)
            vertical.setDefaultSectionSize(28)
        header = table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)  # keep plan order until clicked
        return table

    def _category_changed(self, _index: int) -> None:
        self.proxy.set_category(self.category_filter.currentData())

    def _search_changed(self, text: str) -> None:
        self.proxy.set_text(text.strip())

    def visible_rows(self) -> int:
        return self.proxy.rowCount()
