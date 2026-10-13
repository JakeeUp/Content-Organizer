"""Fast library statistics for an organised (or not-yet-organised) folder.

Used by the GUI dashboard and ``content-organizer stats``. No ffprobe calls: a file under
a category folder (``<root>/<CategoryFolder>/...``) counts for that category; anything
else is categorised by extension only (so unsorted videos count as ``Videos``).

The month of a file comes from the ``YYYY/MM - MonthName`` layout when present (legacy
``YYYY/MonthName`` is recognised too), otherwise from its modification time.
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from content_organizer.categories import Category
from content_organizer.config import Config, load_config
from content_organizer.rules import categorize, parse_date_folder
from content_organizer.scanner import scan

YearMonth = tuple[int, int]


@dataclass
class LibraryStats:
    root: Path
    total: int = 0
    by_category: Counter[Category] = field(default_factory=Counter)
    by_month: dict[YearMonth, int] = field(default_factory=dict)
    """(year, month) -> file count, sorted chronologically."""
    month_folders: dict[YearMonth, list[Path]] = field(default_factory=dict)
    """(year, month) -> existing ``.../YYYY/MM - Name`` folders (for "open folder")."""
    cancelled: bool = False

    def month_series(self) -> list[tuple[YearMonth, int]]:
        """Chronological (year, month) -> count pairs."""
        return sorted(self.by_month.items())


def library_stats(
    folder: Path,
    config: Config | None = None,
    cancel: threading.Event | None = None,
) -> LibraryStats:
    """Count files per category and per (year, month) under ``folder``."""
    config = config or load_config()
    root = Path(folder).resolve()
    result = LibraryStats(root=root)
    months: Counter[YearMonth] = Counter()
    month_dirs: dict[YearMonth, set[Path]] = {}

    for path in scan(root, config):
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break
        parts = path.relative_to(root).parts
        folder_category = config.category_for_folder(parts[0]) if len(parts) > 1 else None
        category = folder_category or categorize(path.name, config).category
        result.total += 1
        result.by_category[category] += 1

        key: YearMonth | None = None
        if folder_category is not None and len(parts) >= 4:
            key = parse_date_folder(parts[1], parts[2])
            if key is not None:
                month_dirs.setdefault(key, set()).add(root / parts[0] / parts[1] / parts[2])
        if key is None:
            try:
                when = datetime.fromtimestamp(path.stat().st_mtime)
            except (OverflowError, OSError, ValueError):
                continue
            key = (when.year, when.month)
        months[key] += 1

    result.by_month = dict(sorted(months.items()))
    result.month_folders = {k: sorted(v) for k, v in sorted(month_dirs.items())}
    return result
