"""Reusable, logic-free widgets for the dashboard."""

from content_organizer.gui.widgets.card import Card
from content_organizer.gui.widgets.category_bars import CategoryBars
from content_organizer.gui.widgets.elided_label import ElidedLabel
from content_organizer.gui.widgets.folder_field import FolderField
from content_organizer.gui.widgets.monthly_chart import MonthlyChart
from content_organizer.gui.widgets.ring_chart import RingChart, Segment
from content_organizer.gui.widgets.toggle import ToggleRow, ToggleSwitch

__all__ = [
    "Card",
    "CategoryBars",
    "ElidedLabel",
    "FolderField",
    "MonthlyChart",
    "RingChart",
    "Segment",
    "ToggleRow",
    "ToggleSwitch",
]
