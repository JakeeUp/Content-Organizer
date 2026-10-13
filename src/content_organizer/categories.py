"""Category and media-type vocabulary shared by every module.

Design decisions:

* A file's **extension decides its media type first**; naming tags can only refine the
  category *within* that media type (``intro_music.mp4`` is still a video).
* Untagged audio goes to ``Audio`` (it used to be dumped in ``Uncategorized``).
* ``FinalizedVideos`` is reached with the ``final`` tag or via the GUI review dialog.
* Square videos are filed as ``HorizontalVideos`` (they are not vertical/Shorts-ready);
  see :mod:`content_organizer.rules`.
* ``Other`` and ``Videos`` (orientation unknown) are the categories the rules could not
  place confidently. They are exposed as :data:`REVIEW_CATEGORIES` so the GUI can offer
  them for manual review - the old ``Uncategorized`` folder no longer exists.
"""

from __future__ import annotations

from enum import StrEnum


class MediaType(StrEnum):
    """Coarse file type, decided purely by extension."""

    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    PROJECT = "project"
    OTHER = "other"


class Category(StrEnum):
    """Output category. The value is the default folder name."""

    VERTICAL = "VerticalVideos"
    HORIZONTAL = "HorizontalVideos"
    VIDEOS = "Videos"
    GREENSCREEN = "GreenscreenEffects"
    FINALIZED = "FinalizedVideos"
    IMAGES = "Images"
    MUSIC = "Music"
    SOUND_EFFECTS = "SoundEffects"
    AUDIO = "Audio"
    PROJECTS = "PremiereProjects"
    OTHER = "Other"

    @property
    def media_type(self) -> MediaType:
        """The media type a file must have to land in this category."""
        return CATEGORY_MEDIA[self]

    @property
    def label(self) -> str:
        """Human-friendly label, e.g. ``"Vertical Videos"``."""
        return CATEGORY_LABELS[self]


CATEGORY_MEDIA: dict[Category, MediaType] = {
    Category.VERTICAL: MediaType.VIDEO,
    Category.HORIZONTAL: MediaType.VIDEO,
    Category.VIDEOS: MediaType.VIDEO,
    Category.GREENSCREEN: MediaType.VIDEO,
    Category.FINALIZED: MediaType.VIDEO,
    Category.IMAGES: MediaType.IMAGE,
    Category.MUSIC: MediaType.AUDIO,
    Category.SOUND_EFFECTS: MediaType.AUDIO,
    Category.AUDIO: MediaType.AUDIO,
    Category.PROJECTS: MediaType.PROJECT,
    Category.OTHER: MediaType.OTHER,
}

CATEGORY_LABELS: dict[Category, str] = {
    Category.VERTICAL: "Vertical Videos",
    Category.HORIZONTAL: "Horizontal Videos",
    Category.VIDEOS: "Videos (unknown orientation)",
    Category.GREENSCREEN: "Greenscreen Effects",
    Category.FINALIZED: "Finalized Videos",
    Category.IMAGES: "Images",
    Category.MUSIC: "Music",
    Category.SOUND_EFFECTS: "Sound Effects",
    Category.AUDIO: "Audio",
    Category.PROJECTS: "Premiere Projects",
    Category.OTHER: "Other",
}

#: Categories whose files the rules could not place confidently.
REVIEW_CATEGORIES: frozenset[Category] = frozenset({Category.VIDEOS, Category.OTHER})
