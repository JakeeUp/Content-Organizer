"""Apply a :class:`~content_organizer.planner.Plan`, journal every operation, and undo.

Safety rules:

* Never overwrite. If the destination exists and has the same size and SHA-256 as the
  source, the file is a **duplicate**: it is skipped (in move mode the source stays where
  it is) and reported in :attr:`RunResult.skipped_duplicates`. Otherwise a free
  ``name_N.ext`` is chosen at execution time.
* Moves use ``os.rename`` on the same device. Across devices the file is copied to a
  temporary name next to the destination, its size is verified, it is renamed into place,
  and only then is the source deleted.
* Each completed operation is appended (and flushed) to a JSON-lines journal at
  ``<output>/.content-organizer/journal-<timestamp>.jsonl`` so an interrupted run can still
  be undone. See :func:`undo_last_run`.
* ``cancel`` (a :class:`threading.Event`) is checked before every file; finished files
  stay finished and journalled.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import logging
import shutil
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, Any

from content_organizer.categories import Category
from content_organizer.planner import Plan, PlannedMove, unique_path
from content_organizer.scanner import JOURNAL_DIR_NAME

log = logging.getLogger(__name__)

JOURNAL_VERSION = 1
_PARTIAL_SUFFIX = ".co-partial"
_CHUNK = 1024 * 1024
_WINDOWS_NOT_SAME_DEVICE = 17


class Mode(StrEnum):
    MOVE = "move"
    COPY = "copy"


class Outcome(StrEnum):
    MOVED = "moved"
    COPIED = "copied"
    DUPLICATE = "duplicate"
    FAILED = "failed"


@dataclass(frozen=True)
class ProgressEvent:
    """Sent to the progress callback after each file (success or not)."""

    done: int
    total: int
    move: PlannedMove
    outcome: Outcome
    dest: Path | None
    """Actual destination (may differ from ``move.dest`` after a late rename)."""
    error: str | None = None


ProgressCallback = Callable[[ProgressEvent], None]


@dataclass(frozen=True)
class FileError:
    src: Path
    message: str


@dataclass
class RunStats:
    total: int = 0
    moved: int = 0
    copied: int = 0
    duplicates: int = 0
    failed: int = 0
    cancelled: bool = False
    per_category: Counter[Category] = field(default_factory=Counter)

    @property
    def processed(self) -> int:
        """Files that were moved or copied."""
        return self.moved + self.copied


@dataclass
class RunResult:
    stats: RunStats
    errors: list[FileError] = field(default_factory=list)
    skipped_duplicates: list[PlannedMove] = field(default_factory=list)
    journal_path: Path | None = None

    @property
    def ok(self) -> bool:
        return not self.errors and not self.stats.cancelled


@dataclass
class UndoResult:
    journal_path: Path
    restored: int = 0
    """Moved files put back at their original location."""
    removed: int = 0
    """Copies deleted."""
    errors: list[FileError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class NothingToUndoError(LookupError):
    """No journal with undoable operations exists in the output folder."""


# --------------------------------------------------------------------------- execute


def execute(
    plan: Plan,
    mode: Mode | str = Mode.MOVE,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> RunResult:
    """Carry out ``plan``. Per-file errors are collected, never raised."""
    mode = Mode(mode)
    result = RunResult(stats=RunStats(total=len(plan.moves)))
    journal: _Journal | None = None
    try:
        for index, move in enumerate(plan.moves, start=1):
            if cancel is not None and cancel.is_set():
                result.stats.cancelled = True
                break
            if journal is None:
                # Created *before* the first file is touched: if the journal cannot be
                # written, nothing moves (an unjournalled move could never be undone).
                journal = _Journal.create(plan, mode)
            outcome, dest, error = _execute_one(move, mode)
            if outcome in (Outcome.MOVED, Outcome.COPIED):
                assert dest is not None
                journal.record(mode, move, dest)
                result.journal_path = journal.path
                result.stats.per_category[move.category] += 1
                if outcome is Outcome.MOVED:
                    result.stats.moved += 1
                else:
                    result.stats.copied += 1
            elif outcome is Outcome.DUPLICATE:
                result.stats.duplicates += 1
                result.skipped_duplicates.append(move)
            else:
                result.stats.failed += 1
                result.errors.append(FileError(move.src, error or "unknown error"))
            if progress is not None:
                progress(ProgressEvent(index, len(plan.moves), move, outcome, dest, error))
    finally:
        if journal is not None:
            journal.close()
            if not journal.ops:  # a run that changed nothing leaves no journal
                journal.path.unlink(missing_ok=True)
    log.info(
        "Run finished: %d moved, %d copied, %d duplicates, %d failed%s",
        result.stats.moved,
        result.stats.copied,
        result.stats.duplicates,
        result.stats.failed,
        " (cancelled)" if result.stats.cancelled else "",
    )
    return result


def _execute_one(move: PlannedMove, mode: Mode) -> tuple[Outcome, Path | None, str | None]:
    try:
        dest = move.dest
        if dest.exists():
            if dest.is_file() and files_identical(move.src, dest):
                log.info("Duplicate skipped: %s == %s", move.src, dest)
                return Outcome.DUPLICATE, dest, None
            dest = unique_path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if mode is Mode.MOVE:
            move_file(move.src, dest)
            return Outcome.MOVED, dest, None
        copy_file(move.src, dest)
        return Outcome.COPIED, dest, None
    except OSError as exc:
        log.error("Failed %s %s -> %s: %s", mode.value, move.src, move.dest, exc)
        return Outcome.FAILED, None, f"{exc.strerror or exc}"


def files_identical(a: Path, b: Path) -> bool:
    """Same size and same SHA-256."""
    if a.stat().st_size != b.stat().st_size:
        return False
    return sha256_file(a) == sha256_file(b)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def move_file(src: Path, dest: Path) -> None:
    """Move without overwriting; cross-device moves copy, verify, then delete."""
    if dest.exists():
        raise FileExistsError(errno.EEXIST, "Destination exists", str(dest))
    try:
        src.rename(dest)  # atomic on one device; Windows refuses to overwrite
        return
    except OSError as exc:
        cross_device = exc.errno == errno.EXDEV or (
            getattr(exc, "winerror", None) == _WINDOWS_NOT_SAME_DEVICE
        )
        if not cross_device:
            raise
    copy_file(src, dest)
    try:
        src.unlink()
    except OSError:
        # The source is still there (e.g. read-only or locked): remove our verified copy
        # so the output holds no untracked duplicate, then report the failure.
        dest.unlink(missing_ok=True)
        raise


def copy_file(src: Path, dest: Path) -> None:
    """Copy via a temporary file, verify the size, then rename into place."""
    tmp = unique_path(dest.with_name(dest.name + _PARTIAL_SUFFIX))  # never clobber
    try:
        shutil.copy2(src, tmp)
        if tmp.stat().st_size != src.stat().st_size:
            raise OSError(errno.EIO, "Size mismatch after copy", str(dest))
        if dest.exists():
            raise FileExistsError(errno.EEXIST, "Destination exists", str(dest))
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink()


# --------------------------------------------------------------------------- journal


def journal_dir(output: Path) -> Path:
    return Path(output) / JOURNAL_DIR_NAME


def list_journals(output: Path) -> list[Path]:
    """Journals that can still be undone, oldest first."""
    directory = journal_dir(output)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("journal-*.jsonl"))


class _Journal:
    def __init__(self, path: Path, handle: IO[str]) -> None:
        self.path = path
        self._handle = handle
        self.ops = 0

    @classmethod
    def create(cls, plan: Plan, mode: Mode) -> _Journal:
        directory = journal_dir(plan.output)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = directory / f"journal-{stamp}.jsonl"
        handle = open(path, "x", encoding="utf-8")  # noqa: SIM115 - closed by close()
        journal = cls(path, handle)
        journal._write(
            {
                "type": "run",
                "version": JOURNAL_VERSION,
                "mode": mode.value,
                "source": str(plan.source),
                "output": str(plan.output),
                "started": _now(),
            }
        )
        return journal

    def record(self, mode: Mode, move: PlannedMove, dest: Path) -> None:
        entry: dict[str, Any] = {
            "type": "op",
            "op": mode.value,
            "src": str(move.src),
            "dest": str(dest),
            "category": move.category.value,
        }
        with contextlib.suppress(OSError):  # never lose the journal line over a failed stat
            entry["size"] = dest.stat().st_size
        entry["ts"] = _now()
        self._write(entry)
        self.ops += 1

    def _write(self, entry: dict[str, Any]) -> None:
        self._handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def read_journal(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (header, operations). Malformed lines (e.g. a torn last line) are skipped."""
    header: dict[str, Any] = {}
    ops: list[dict[str, Any]] = []
    for line in _lines(path):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            log.warning("Ignoring malformed journal line in %s", path.name)
            continue
        if not isinstance(entry, dict):
            log.warning("Ignoring malformed journal line in %s", path.name)
            continue
        if entry.get("type") == "run":
            header = entry
        elif entry.get("type") == "op":
            ops.append(entry)
    return header, ops


def _lines(path: Path) -> Iterator[str]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield line


# --------------------------------------------------------------------------- undo


def undo_last_run(
    output: Path,
    progress: Callable[[int, int], None] | None = None,
) -> UndoResult:
    """Reverse the most recent journal in ``output``.

    Moves are moved back (refusing to overwrite anything now at the original path);
    copies are deleted (only if their size still matches). On full success the journal is
    renamed to ``*.jsonl.undone``; on partial success it is rewritten with the operations
    that remain so the undo can be retried. Raises :class:`NothingToUndoError`.
    """
    journals = list_journals(output)
    if not journals:
        raise NothingToUndoError(f"No organizer runs to undo in {output}")
    path = journals[-1]
    header, ops = read_journal(path)
    result = UndoResult(journal_path=path)
    remaining: list[dict[str, Any]] = []
    out_root = Path(output).resolve()

    for index, op in enumerate(reversed(ops), start=1):
        error = _undo_one(op, out_root)
        if error is None:
            if op.get("op") == Mode.COPY.value:
                result.removed += 1
            else:
                result.restored += 1
        else:
            result.errors.append(FileError(Path(str(op.get("src", "?"))), error))
            remaining.append(op)
        if progress is not None:
            progress(index, len(ops))

    if remaining:
        _rewrite_journal(path, header, list(reversed(remaining)))
    else:
        path.replace(path.with_name(path.name + ".undone"))
    return result


def _undo_one(op: dict[str, Any], out_root: Path) -> str | None:
    try:
        src = Path(op["src"])
        dest = Path(op["dest"])
    except (KeyError, TypeError):
        return "malformed journal entry"
    if not dest.exists():
        return f"{dest} no longer exists"
    try:
        if op.get("op") == Mode.COPY.value:
            if "size" in op and dest.stat().st_size != op["size"]:
                return f"{dest} changed since it was copied; not deleting"
            if not src.is_file():
                return f"original {src} no longer exists; keeping the copy"
            dest.unlink()
        else:
            if src.exists():
                return f"{src} already exists; not overwriting"
            src.parent.mkdir(parents=True, exist_ok=True)
            move_file(dest, src)
    except OSError as exc:
        return f"{exc.strerror or exc}"
    _prune_empty_dirs(dest.parent, out_root)
    return None


def _prune_empty_dirs(directory: Path, stop: Path) -> None:
    """Remove now-empty folders from ``directory`` up to (not including) ``stop``."""
    current = directory.resolve()
    while current != stop and current.is_relative_to(stop):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _rewrite_journal(path: Path, header: dict[str, Any], ops: list[dict[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for entry in [header, *ops] if header else ops:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
