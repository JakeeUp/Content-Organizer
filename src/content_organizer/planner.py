"""Build a :class:`Plan` of moves without touching any file.

The only side effects are ``stat`` calls and (optionally) ffprobe via the injected
:data:`~content_organizer.probe.Prober`. The plan powers dry-run output, the GUI preview,
and :mod:`content_organizer.executor`.

* Date subfolders (``YYYY/MM - MonthName``) use the video's ffprobe ``creation_time``,
  falling back to the file's modification time, and apply only to ``layout.date_categories``.
* Destination collisions are resolved inside the plan (``name_1.ext``, ``name_2.ext`` ...),
  including collisions between two planned files. If a file of the **same size** already
  exists at the destination the plan keeps that name and flags ``possible_duplicate``;
  the executor then compares hashes and either skips the duplicate or renames.
"""

from __future__ import annotations

import logging
import os
import stat
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from content_organizer.categories import REVIEW_CATEGORIES, Category, MediaType
from content_organizer.config import Config, load_config
from content_organizer.probe import Prober, VideoInfo, find_ffprobe, make_prober
from content_organizer.rules import categorize, clean_filename, date_folder, media_type_for
from content_organizer.scanner import scan

log = logging.getLogger(__name__)

#: ``progress(done, total, path)`` - called after each file is planned.
PlanProgress = Callable[[int, int, Path], None]


class PlanError(ValueError):
    """The requested source/output combination cannot be planned."""


@dataclass(frozen=True)
class Options:
    """User-facing switches for a run."""

    date_folders: bool = True
    clean_names: bool = False
    probe: bool = True
    """Use ffprobe for orientation/creation time (ignored if no prober is available)."""


@dataclass(frozen=True)
class PlannedMove:
    src: Path
    dest: Path
    category: Category
    reason: str
    possible_duplicate: bool = False
    """A same-size file already exists at ``dest``; the executor will hash-compare."""

    @property
    def needs_review(self) -> bool:
        return self.category in REVIEW_CATEGORIES


@dataclass
class Plan:
    source: Path
    output: Path
    options: Options
    moves: list[PlannedMove] = field(default_factory=list)
    probe_available: bool = False
    cancelled: bool = False

    def __len__(self) -> int:
        return len(self.moves)

    def counts(self) -> dict[Category, int]:
        """Number of planned files per category (only non-zero entries)."""
        return dict(Counter(move.category for move in self.moves))


def check_paths(source: Path, output: Path) -> tuple[Path, Path]:
    """Resolve and validate a source/output pair. Raises :class:`PlanError`."""
    src = Path(source).expanduser().resolve()
    out = Path(output).expanduser().resolve()
    if not src.is_dir():
        raise PlanError(f"Source folder does not exist: {src}")
    if out.exists() and not out.is_dir():
        raise PlanError(f"Output path is not a folder: {out}")
    same = os.path.normcase(str(src)) == os.path.normcase(str(out))
    if same or (out.exists() and src.samefile(out)):  # case-insensitive FS, links
        raise PlanError("Source and output must be different folders")
    return src, out


def build_plan(
    source: Path,
    output: Path,
    options: Options | None = None,
    prober: Prober | None = None,
    config: Config | None = None,
    *,
    progress: PlanProgress | None = None,
    cancel: threading.Event | None = None,
) -> Plan:
    """Scan ``source`` and decide a destination for every file.

    If ``prober`` is ``None`` and ``options.probe`` is true, ffprobe is located with
    :func:`~content_organizer.probe.find_ffprobe`; when it is missing, videos land in
    ``Videos``. Setting ``cancel`` stops early and returns a partial plan with
    ``cancelled=True``.
    """
    options = options or Options()
    config = config or load_config()
    src, out = check_paths(source, output)

    if options.probe and prober is None:
        ffprobe = find_ffprobe()
        prober = make_prober(ffprobe) if ffprobe else None
        if prober is None:
            log.warning("ffprobe not found - video orientation will not be detected")
    if not options.probe:
        prober = None

    plan = Plan(source=src, output=out, options=options, probe_available=prober is not None)
    files = list(scan(src, config, exclude=[out]))
    taken: set[str] = set()
    for index, path in enumerate(files, start=1):
        if cancel is not None and cancel.is_set():
            plan.cancelled = True
            break
        try:
            plan.moves.append(_plan_one(path, out, options, prober, config, taken))
        except OSError as exc:  # vanished or unreadable between scan and stat
            log.warning("Skipping %s: %s", path, exc)
        if progress is not None:
            progress(index, len(files), path)
    return plan


def _plan_one(
    path: Path,
    output: Path,
    options: Options,
    prober: Prober | None,
    config: Config,
    taken: set[str],
) -> PlannedMove:
    info: VideoInfo | None = None
    if prober is not None and media_type_for(path.name, config) is MediaType.VIDEO:
        info = prober(path)
    decision = categorize(path.name, config, info)

    folder = output / config.folder_for(decision.category)
    if options.date_folders and decision.category in config.date_categories:
        when = _local_time(info.creation_time) if info is not None else None
        if when is None:
            when = _mtime(path)
        if when is not None:
            folder = folder / date_folder(when)

    name = clean_filename(path.name, config) if options.clean_names else path.name
    dest, possible_duplicate = _resolve_collision(folder / name, path, taken)
    taken.add(_key(dest))
    return PlannedMove(path, dest, decision.category, decision.reason, possible_duplicate)


def _resolve_collision(dest: Path, src: Path, taken: set[str]) -> tuple[Path, bool]:
    size = src.stat().st_size
    candidate = dest
    counter = 0
    while True:
        if _key(candidate) not in taken:
            try:
                existing = candidate.stat()
            except FileNotFoundError:
                return candidate, False
            except OSError:
                existing = None
            # Only a regular file can be a duplicate; a folder in the way is just taken.
            if existing is not None and stat.S_ISREG(existing.st_mode) and existing.st_size == size:
                return candidate, True
        counter += 1
        candidate = dest.with_name(f"{dest.stem}_{counter}{dest.suffix}")


def unique_path(dest: Path) -> Path:
    """First ``name_N.ext`` variant of ``dest`` that does not exist on disk."""
    candidate = dest
    counter = 0
    while candidate.exists():
        counter += 1
        candidate = dest.with_name(f"{dest.stem}_{counter}{dest.suffix}")
    return candidate


def _local_time(when: datetime | None) -> datetime | None:
    """``when`` in local time, or ``None`` if it cannot be represented (e.g. year 9999)."""
    if when is None:
        return None
    try:
        return when.astimezone()  # bucket by local calendar month
    except (OverflowError, OSError, ValueError):
        return None


def _mtime(path: Path) -> datetime | None:
    """Local modification time; ``None`` for timestamps the platform cannot convert."""
    mtime = path.stat().st_mtime
    try:
        return datetime.fromtimestamp(mtime)
    except (OverflowError, OSError, ValueError):  # e.g. pre-1970 mtimes on Windows
        try:
            return datetime(1970, 1, 1) + timedelta(seconds=mtime)
        except OverflowError:
            return None


def _key(path: Path) -> str:
    """Case-insensitive on every OS: macOS (APFS) and exFAT drives are case-insensitive
    but ``normcase`` only folds case on Windows, so ``Name.PNG``/``name.png`` would
    otherwise be planned onto the same file."""
    return os.path.normcase(str(path)).casefold()
