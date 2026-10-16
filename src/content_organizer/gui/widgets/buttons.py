"""Themed push buttons."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from content_organizer.gui import icons


def button(
    text: str,
    icon: str = "",
    *,
    variant: str = "",
    size: str = "",
    tooltip: str = "",
    icon_token: str = "",
) -> QPushButton:
    """A themed push button. ``variant``: primary, ghost, danger, link or "" (secondary)."""
    widget = QPushButton(text)
    if variant:
        widget.setProperty("variant", variant)
    if size:
        widget.setProperty("size", size)
    if tooltip:
        widget.setToolTip(tooltip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon:
        token = icon_token or {"primary": "on_accent", "danger": "danger"}.get(variant, "text")
        icons.themed(widget, icon, token, 16)
    return widget
