"""Library: what the output folder holds, by month and by category."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QCursor, QDesktopServices
from PyQt6.QtWidgets import QHBoxLayout, QMenu, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from content_organizer.gui import icons, theme
from content_organizer.gui.context import AppContext
from content_organizer.gui.pages.base import Page
from content_organizer.gui.presenters import plural
from content_organizer.gui.widgets import (
    Card,
    CategoryBreakdown,
    EmptyState,
    MetricTile,
    MonthlyChart,
    button,
)
from content_organizer.gui.widgets.monthly_chart import month_label
from content_organizer.gui.workers import StatsTask
from content_organizer.stats import LibraryStats

_DEBOUNCE_MS = 450


class LibraryPage(Page):
    statusMessage = pyqtSignal(str, int)  # text, timeout ms
    organizeRequested = pyqtSignal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__("Library", "Choose an output folder to see its contents.", parent)
        self.context = context
        self.stats: LibraryStats | None = None
        self._task: StatsTask | None = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.refresh)

        self.refresh_button = button("Refresh", "refresh", tooltip="Rescan the output folder (F5)")
        self.open_button = button(
            "Open folder", "open", tooltip="Show the output folder in your file manager"
        )
        self.header.add_action(self.refresh_button)
        self.header.add_action(self.open_button)

        self.stack = QStackedWidget()
        self.empty = EmptyState(
            "library",
            "No library yet",
            "Choose an output folder on the Organize page. Its contents appear here.",
            "Go to Organize",
        )
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self._build_content())
        self.body.addWidget(self.stack, 1)

        self.refresh_button.clicked.connect(self.refresh)
        self.open_button.clicked.connect(self.open_output_folder)
        self.empty.actionTriggered.connect(self.organizeRequested)
        self.chart.monthClicked.connect(self.open_month)
        context.outputChanged.connect(self._debounce.start)
        context.libraryChanged.connect(self.refresh)
        context.reviewCountChanged.connect(self._show_review_count)
        self.refresh()

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("page")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2 * theme.SPACE)
        tiles = QHBoxLayout()
        tiles.setSpacing(2 * theme.SPACE)
        self.total_tile = MetricTile("Files")
        self.months_tile = MetricTile("Months")
        self.categories_tile = MetricTile("Categories")
        self.review_tile = MetricTile("Needs review")
        for tile in (self.total_tile, self.months_tile, self.categories_tile, self.review_tile):
            tiles.addWidget(tile)
        column.addLayout(tiles)

        chart_card = Card(
            "Monthly distribution",
            "Files per month. Click a bar to open that month's folder.",
        )
        self.chart = MonthlyChart()
        self.chart.setToolTip("Use Left/Right to pick a month and Enter to open it")
        chart_card.body.addWidget(self.chart, 1)
        column.addWidget(chart_card, 1)

        breakdown_card = Card("Categories", "Share of the library per category.")
        self.breakdown = CategoryBreakdown()
        breakdown_card.body.addWidget(self.breakdown)
        column.addWidget(breakdown_card)
        return content

    # ---------------------------------------------------------------- refresh

    def refresh(self) -> None:
        """Rescan the output folder in the background and redraw."""
        self._debounce.stop()
        if self._task is not None:
            self._task.cancel()
            self._task = None
        output = self.context.output_dir()
        self.refresh_button.setEnabled(output is not None)
        self.open_button.setEnabled(output is not None)
        if output is None:
            self.clear()
            return
        self.header.set_subtitle(f"Scanning {output.name or output}…", str(output))
        task = StatsTask(output, self.context.config)
        task.succeeded.connect(self._apply_stats)
        task.failed.connect(lambda message: self.clear(f"Scan failed: {message}"))
        self._task = task
        self.context.launch(task)

    def clear(self, message: str = "Choose an output folder to see its contents.") -> None:
        self.stats = None
        self.header.set_subtitle(message)
        self.stack.setCurrentWidget(self.empty)

    def _apply_stats(self, stats: LibraryStats) -> None:
        if stats.cancelled:
            return
        self._task = None
        self.stats = stats
        name = stats.root.name or str(stats.root)
        self.header.set_subtitle(
            f"{name} · {plural(stats.total, 'file')} across {plural(len(stats.by_month), 'month')}",
            str(stats.root),
        )
        self.total_tile.set_value(f"{stats.total:,}")
        self.months_tile.set_value(f"{len(stats.by_month):,}")
        self.categories_tile.set_value(str(sum(1 for n in stats.by_category.values() if n)))
        self._show_review_count(self.context.review_count)
        self.chart.set_series(
            stats.month_series(), "This folder is empty. Organized files will appear by month."
        )
        self.breakdown.set_counts(stats.by_category)
        self.stack.setCurrentIndex(1)

    def _show_review_count(self, count: int) -> None:
        self.review_tile.set_value(f"{count:,}", "warn" if count else "")

    # ------------------------------------------------------------------ months

    def folders_for_month(self, year: int, month: int) -> list[Path]:
        if self.stats is None:
            return []
        return list(self.stats.month_folders.get((year, month), []))

    def open_month(self, year: int, month: int) -> None:
        """Open the clicked month's folder; offer a picker when several categories have one."""
        folders = self.folders_for_month(year, month)
        if not folders:
            self.statusMessage.emit(
                f"No date folders for {month_label((year, month))}: these files are counted by "
                "their modified date. Turn on Date folders to file videos by month.",
                8000,
            )
        elif len(folders) == 1:
            self.open_path(folders[0])
        else:
            self._month_menu(folders).popup(QCursor.pos())

    def _month_menu(self, folders: list[Path]) -> QMenu:
        menu = QMenu(self)
        root = self.stats.root if self.stats else None
        for folder in folders:
            text = str(folder.relative_to(root)) if root else str(folder)
            action = QAction(icons.icon("folder"), text, menu)
            action.triggered.connect(lambda _=False, f=folder: self.open_path(f))
            menu.addAction(action)
        menu.addSeparator()
        open_all = QAction("Open all", menu)
        open_all.triggered.connect(lambda: [self.open_path(f) for f in folders])
        menu.addAction(open_all)
        return menu

    def open_path(self, path: Path) -> bool:
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if not ok:
            QMessageBox.warning(self, "Could not open", f"Could not open:\n{path}")
        return ok

    def open_output_folder(self) -> None:
        output = self.context.output_dir()
        if output is not None:
            self.open_path(output)

    def shutdown(self) -> None:
        self._debounce.stop()
