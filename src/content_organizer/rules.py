"""Pure categorisation rules - no I/O.

Order of decisions for a file name:

1. The **extension** decides the media type (video, image, audio, project, other).
2. A **naming tag** may refine the category, but only to a category of the same media
   type. Tags are whole tokens of the stem split on ``_ - . <space>`` and compared
   case-insensitively, so ``beach_vert.mp4`` matches ``vert`` but ``vertigo.mp4`` and
   ``holiday_greenland.mp4`` do not match anything.
3. Untagged videos use ffprobe orientation: vertical -> ``VerticalVideos``, horizontal
   or square -> ``HorizontalVideos``, unknown -> ``Videos``.
4. Untagged audio -> ``Audio``; images -> ``Images``; projects -> ``PremiereProjects``;
   anything else -> ``Other``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath

from content_organizer.categories import Category, MediaType
from content_organizer.config import Config
from content_organizer.probe import Orientation, VideoInfo

_SPLIT = re.compile(r"([_\-\s.]+)")

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_UNTAGGED: dict[MediaType, Category] = {
    MediaType.IMAGE: Category.IMAGES,
    MediaType.AUDIO: Category.AUDIO,
    MediaType.PROJECT: Category.PROJECTS,
    MediaType.OTHER: Category.OTHER,
}


@dataclass(frozen=True)
class Decision:
    """Where a file goes and a short human-readable reason why."""

    category: Category
    reason: str


def split_name(name: str) -> tuple[str, str]:
    """Split ``name`` into (stem, suffix); dotfiles have no suffix."""
    path = PurePath(name)
    return path.stem, path.suffix


def tokenize(stem: str) -> list[str]:
    """Lower-case tokens of a file stem, split on ``_ - . <space>``."""
    return [t for t in _SPLIT.split(stem.lower())[::2] if t]


def media_type_for(name: str, config: Config) -> MediaType:
    """Media type of a file name, decided by extension only."""
    return config.extensions.get(split_name(name)[1].lower(), MediaType.OTHER)


def match_tag(name: str, media: MediaType, config: Config) -> tuple[Category, str] | None:
    """First (category, tag) whose tag is a token of ``name`` and fits ``media``."""
    tokens = set(tokenize(split_name(name)[0]))
    for category, tags in config.tags:
        if category.media_type is not media:
            continue
        for tag in tags:
            if tag in tokens:
                return category, tag
    return None


def categorize(name: str, config: Config, info: VideoInfo | None = None) -> Decision:
    """Decide the category for a file name, optionally using probed video info."""
    media = media_type_for(name, config)
    tagged = match_tag(name, media, config)
    if tagged is not None:
        category, tag = tagged
        return Decision(category, f"tag '{tag}'")

    if media is MediaType.VIDEO:
        if info is None:
            return Decision(Category.VIDEOS, "orientation unknown (not probed)")
        orientation = info.orientation
        if orientation is Orientation.VERTICAL:
            return Decision(Category.VERTICAL, info.describe())
        if orientation in (Orientation.HORIZONTAL, Orientation.SQUARE):
            return Decision(Category.HORIZONTAL, info.describe())
        return Decision(Category.VIDEOS, "orientation unknown (no dimensions)")

    ext = split_name(name)[1].lower() or "no extension"
    return Decision(_UNTAGGED[media], f"extension {ext}")


def clean_filename(name: str, config: Config) -> str:
    """Remove whole tag tokens (for the file's media type) from the stem.

    ``Beach_VERT-take2.mp4`` -> ``Beach-take2.mp4``. Words that merely contain a tag
    (``projection``, ``soundtrack``) are untouched and other separators are kept. If
    removing tags would leave an empty stem, the original name is returned.
    """
    stem, suffix = split_name(name)
    media = media_type_for(name, config)
    all_tags = {tag for cat, tags in config.tags if cat.media_type is media for tag in tags}
    parts = _SPLIT.split(stem)  # [token, sep, token, sep, ..., token]
    kept: list[tuple[str, str]] = []  # (separator before token, token)
    removed = False
    separator = ""
    for index, part in enumerate(parts):
        if index % 2:  # separator
            separator = part
            continue
        if part.lower() in all_tags:
            removed = True
            continue
        if part:
            kept.append((separator, part))
    if not removed or not kept:
        return name
    cleaned = kept[0][1] + "".join(sep + token for sep, token in kept[1:])
    return cleaned + suffix


def date_folder(when: datetime) -> PurePath:
    """Sortable, locale-independent date subfolder: ``2024/03 - March``."""
    return PurePath(f"{when.year:04d}", f"{when.month:02d} - {MONTH_NAMES[when.month - 1]}")


def parse_date_folder(year: str, month: str) -> tuple[int, int] | None:
    """Recognise ``("2024", "03 - March")`` (or legacy ``("2024", "March")``)."""
    if not (len(year) == 4 and year.isdigit()):
        return None
    head = month.split(" ", 1)[0].strip()
    if head.isdigit() and 1 <= int(head) <= 12:
        return int(year), int(head)
    lowered = month.strip().lower()
    for index, month_name in enumerate(MONTH_NAMES, start=1):
        if lowered == month_name.lower():
            return int(year), index
    return None
