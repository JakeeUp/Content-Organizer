"""The window's pages. Each one reads and writes shared state through :class:`AppContext`."""

from content_organizer.gui.pages.library import LibraryPage
from content_organizer.gui.pages.organize import OrganizePage
from content_organizer.gui.pages.review import ReviewPage
from content_organizer.gui.pages.settings import SettingsPage

__all__ = ["LibraryPage", "OrganizePage", "ReviewPage", "SettingsPage"]
