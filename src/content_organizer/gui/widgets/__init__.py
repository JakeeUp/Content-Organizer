"""Reusable, logic-free widgets."""

from content_organizer.gui.widgets.buttons import button
from content_organizer.gui.widgets.card import Card, MetricTile, divider, label
from content_organizer.gui.widgets.category_breakdown import CategoryBreakdown
from content_organizer.gui.widgets.elided_label import ElidedLabel
from content_organizer.gui.widgets.file_preview import FilePreview
from content_organizer.gui.widgets.flow_layout import FlowLayout
from content_organizer.gui.widgets.folder_field import FolderField
from content_organizer.gui.widgets.monthly_chart import MonthlyChart
from content_organizer.gui.widgets.notice import EmptyState, Notice
from content_organizer.gui.widgets.page_header import PageHeader
from content_organizer.gui.widgets.recent_runs import RecentRuns
from content_organizer.gui.widgets.segmented import SegmentedControl
from content_organizer.gui.widgets.sidebar import NavButton, Sidebar
from content_organizer.gui.widgets.toggle import ToggleRow, ToggleSwitch

__all__ = [
    "Card",
    "CategoryBreakdown",
    "ElidedLabel",
    "EmptyState",
    "FilePreview",
    "FlowLayout",
    "FolderField",
    "MetricTile",
    "MonthlyChart",
    "NavButton",
    "Notice",
    "PageHeader",
    "RecentRuns",
    "SegmentedControl",
    "Sidebar",
    "ToggleRow",
    "ToggleSwitch",
    "button",
    "divider",
    "label",
]
