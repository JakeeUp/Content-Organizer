"""Safe, deterministic directory walk.

Skipped: the output folder (and any other excluded folder) when nested in the source,
hidden files and directories (dot-prefixed, or the Windows hidden/system attribute),
symlinks, the app's own ``.content-organizer`` journal dir, and the ``skip_files`` /
``skip_dirs`` glob patterns from the config (system files, partial downloads, caches).
Unreadable directories are logged and skipped. Results are sorted for reproducible plans.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import stat
from collections.abc import Iterable, Iterator
from pathlib import Path

from content_organizer.config import Config

log = logging.getLogger(__name__)

JOURNAL_DIR_NAME = ".content-organizer"
_HIDDEN_ATTRS = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0x2) | getattr(
    stat, "FILE_ATTRIBUTE_SYSTEM", 0x4
)


def is_hidden(entry: os.DirEntry[str]) -> bool:
    """Dotfiles, plus files with the Windows hidden/system attribute."""
    if entry.name.startswith("."):
        return True
    try:
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & _HIDDEN_ATTRS)


def matches_any(name: str, patterns: Iterable[str]) -> bool:
    """Case-insensitive glob match of ``name`` against ``patterns`` (already lower-case)."""
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern) for pattern in patterns)


def scan(source: Path, config: Config, exclude: Iterable[Path] = ()) -> Iterator[Path]:
    """Yield organisable files under ``source`` in sorted order.

    ``exclude`` directories (typically the output folder) are pruned wherever they appear
    inside the tree; paths are compared after ``resolve()``.
    """
    excluded = _Excluded(exclude)
    root = Path(source)
    if excluded.matches(root):
        return
    yield from _walk(root, config, excluded)


class _Excluded:
    """Excluded folders, matched by normalised path *or* by file identity.

    The identity check (``st_dev``/``st_ino``) catches spellings that ``normcase`` cannot,
    such as a different letter case on macOS's case-insensitive file system.
    """

    def __init__(self, paths: Iterable[Path]) -> None:
        self.names: set[str] = set()
        self.ids: set[tuple[int, int]] = set()
        for path in paths:
            self.names.add(_norm(Path(path)))
            identity = _identity(Path(path))
            if identity is not None:
                self.ids.add(identity)

    def matches(self, path: Path) -> bool:
        if _norm(path) in self.names:
            return True
        return bool(self.ids) and _identity(path) in self.ids


def _identity(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()  # follows links; DirEntry.stat() has no inode on Windows
    except OSError:
        return None
    return (st.st_dev, st.st_ino) if st.st_ino else None


def _walk(directory: Path, config: Config, excluded: _Excluded) -> Iterator[Path]:
    try:
        with os.scandir(directory) as it:
            entries = sorted(it, key=lambda e: e.name.lower())
    except OSError as exc:
        log.warning("Cannot read directory %s: %s", directory, exc)
        return

    subdirs: list[Path] = []
    for entry in entries:
        if entry.is_symlink() or is_hidden(entry):
            continue
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
        except OSError:
            continue
        if is_dir:
            if entry.name == JOURNAL_DIR_NAME or matches_any(entry.name, config.skip_dirs):
                continue
            path = Path(entry.path)
            if not excluded.matches(path):
                subdirs.append(path)
        elif is_file and not matches_any(entry.name, config.skip_files):
            yield Path(entry.path)

    for subdir in subdirs:
        yield from _walk(subdir, config, excluded)


def _norm(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))
