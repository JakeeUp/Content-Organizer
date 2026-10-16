"""Plan preview table: model, filter proxy and the category pill delegate."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QRectF,
    QSize,
    QSortFilterProxyModel,
    Qt,
)
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from content_organizer.categories import Category
from content_organizer.gui import theme
from content_organizer.planner import Plan, PlannedMove

_Index = QModelIndex | QPersistentModelIndex
CATEGORY_ROLE = Qt.ItemDataRole.UserRole + 1


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def destination_text(move: PlannedMove, output: Path) -> str:
    """The destination folder relative to the output; the name too if it changes."""
    folder = relative(move.dest.parent, output)
    if move.dest.name != move.src.name:
        return str(Path(folder) / move.dest.name)
    return folder


def reason_text(move: PlannedMove) -> str:
    notes = [move.reason]
    if move.needs_review:
        notes.append("needs review")
    if move.possible_duplicate:
        notes.append("possible duplicate")
    return " · ".join(notes)


class PlanTableModel(QAbstractTableModel):
    """Read-only table over ``plan.moves``."""

    HEADERS = ("Category", "File", "Destination", "Reason")

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
        if role == Qt.ItemDataRole.ForegroundRole and column >= 2:
            p = theme.current()
            flagged = column == 3 and (move.needs_review or move.possible_duplicate)
            return QColor(p.warning if flagged else p.text_muted)
        if role == CATEGORY_ROLE:
            return move.category.value
        return None

    def _display(self, move: PlannedMove, column: int) -> str:
        if column == 0:
            return move.category.label
        if column == 1:
            return relative(move.src, self._plan.source)
        if column == 2:
            return destination_text(move, self._plan.output)
        return reason_text(move)


class PlanFilterModel(QSortFilterProxyModel):
    """Filters by category value and free text over file and destination."""

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


class CategoryPillDelegate(QStyledItemDelegate):
    """Paints the category as a soft pill with a coloured dot."""

    def paint(
        self, painter: QPainter | None, option: QStyleOptionViewItem | None, index: QModelIndex
    ) -> None:
        if painter is None or option is None:
            return
        p = theme.current()
        value = index.data(CATEGORY_ROLE)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        try:
            category = Category(value)
        except ValueError:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(rect, QColor(p.accent_soft if selected else p.surface))
        painter.setPen(QColor(p.border))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        font = QFont(option.font)
        font.setPixelSize(theme.FONT_CAPTION)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        width = min(rect.width() - 24, painter.fontMetrics().horizontalAdvance(text) + 26)
        pill = QRectF(rect.left() + 14, rect.center().y() - 11, width, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(p.category(category, 0.16 if p.is_dark else 0.11))
        painter.drawRoundedRect(pill, 11, 11)
        painter.setBrush(p.category(category))
        painter.drawEllipse(QRectF(pill.left() + 9, pill.center().y() - 3, 6, 6))
        painter.setPen(QColor(p.text))
        label = painter.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, round(pill.width() - 24)
        )
        painter.drawText(
            pill.adjusted(20, 0, -6, 0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            label,
        )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem | None, index: QModelIndex) -> QSize:
        if option is None:
            return QSize(196, 38)
        base = super().sizeHint(option, index)
        return QSize(base.width() + 48, 38)


def build_plan_table(proxy: PlanFilterModel) -> QTableView:
    table = QTableView()
    table.setModel(proxy)
    table.setItemDelegateForColumn(0, CategoryPillDelegate(table))
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSortingEnabled(True)
    table.setWordWrap(False)
    table.setShowGrid(False)
    table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    table.setFrameShape(QTableView.Shape.NoFrame)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setAccessibleName("Planned moves")
    vertical = table.verticalHeader()
    if vertical is not None:
        vertical.setVisible(False)
        vertical.setDefaultSectionSize(38)
    header = table.horizontalHeader()
    if header is not None:
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 196)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)  # keep plan order until clicked
    return table
