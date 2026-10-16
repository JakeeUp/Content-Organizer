"""Qt-free view-model helpers: validation and the text the GUI shows.

Keeping this out of the widgets makes it unit-testable and keeps widgets thin. No file
is ever moved or categorised here - that is the core's job.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from content_organizer.categories import REVIEW_CATEGORIES, Category
from content_organizer.config import Config
from content_organizer.executor import Mode, RunResult, UndoResult, list_journals, read_journal
from content_organizer.planner import Plan
from content_organizer.scanner import scan


@dataclass(frozen=True)
class FieldStatus:
    kind: str  # "ok" | "warn" | "error" | "neutral"
    message: str

    @property
    def usable(self) -> bool:
        return self.kind in ("ok", "warn")


@dataclass(frozen=True)
class FolderValidation:
    source: FieldStatus
    output: FieldStatus

    @property
    def ready(self) -> bool:
        return self.source.usable and self.output.usable


def _norm(path: Path) -> str:
    return os.path.normcase(str(path))


def _is_within(child: Path, parent: Path) -> bool:
    c, p = _norm(child), _norm(parent)
    return c != p and c.startswith(p.rstrip("\\/") + os.sep)


def _resolve(text: str) -> Path | None:
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        return None
    try:
        return path.resolve()
    except OSError:
        return None


def validate_source(text: str) -> FieldStatus:
    if not text:
        return FieldStatus("neutral", "Required: the messy inbox you want sorted.")
    path = _resolve(text)
    if path is None:
        return FieldStatus("error", "Enter a full path, for example C:\\Users\\you\\Inbox.")
    if not path.exists():
        return FieldStatus("error", "Folder not found.")
    if not path.is_dir():
        return FieldStatus("error", "This is a file, not a folder.")
    return FieldStatus("ok", "Ready.")


def validate_output(text: str, source_text: str) -> FieldStatus:
    if not text:
        return FieldStatus("neutral", "Required: where the sorted folders will be created.")
    out = _resolve(text)
    if out is None:
        return FieldStatus("error", "Enter a full path, for example D:\\Organized.")
    if out.exists() and not out.is_dir():
        return FieldStatus("error", "This is a file, not a folder.")
    src = _resolve(source_text)
    if src is not None:
        if _norm(src) == _norm(out):
            return FieldStatus("error", "Must be different from the source folder.")
        if _is_within(out, src):
            return FieldStatus(
                "warn", "Inside the source folder: it will be skipped when scanning."
            )
        if _is_within(src, out):
            return FieldStatus("warn", "Contains the source folder: files are sorted in place.")
    if not out.exists():
        if not Path(out.anchor).exists():
            return FieldStatus("error", "That drive is not available.")
        return FieldStatus("ok", "Will be created when you organize.")
    return FieldStatus("ok", "Ready.")


def validate_folders(source_text: str, output_text: str) -> FolderValidation:
    source_text, output_text = source_text.strip(), output_text.strip()
    return FolderValidation(validate_source(source_text), validate_output(output_text, source_text))


# ------------------------------------------------------------------ formatting


def format_bytes(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def plural(count: int, word: str) -> str:
    return f"{count:,} {word}{'' if count == 1 else 's'}"


def plan_summary(plan: Plan) -> str:
    review = sum(1 for move in plan.moves if move.needs_review)
    duplicates = sum(1 for move in plan.moves if move.possible_duplicate)
    parts = [f"{plural(len(plan), 'file')} planned"]
    if review:
        parts.append(f"{review:,} need review")
    if duplicates:
        parts.append(f"{plural(duplicates, 'possible duplicate')}")
    return " · ".join(parts)


def plan_warnings(plan: Plan) -> list[str]:
    warnings = []
    if plan.options.probe and not plan.probe_available:
        warnings.append(
            "FFmpeg (ffprobe) was not found, so video orientation cannot be detected. "
            "Untagged videos go to 'Videos' for review."
        )
    if _is_within(plan.output, plan.source):
        warnings.append("The output folder is inside the source; it is skipped while scanning.")
    return warnings


@dataclass(frozen=True)
class RunSummary:
    title: str
    line: str
    details: str
    kind: str  # "ok" | "warn" | "error"


def run_summary(result: RunResult, mode: Mode) -> RunSummary:
    stats = result.stats
    verb = "copied" if mode is Mode.COPY else "moved"
    parts = [f"{stats.processed:,} {verb}"]
    if stats.duplicates:
        parts.append(f"{plural(stats.duplicates, 'duplicate')} skipped")
    if stats.failed:
        parts.append(f"{stats.failed:,} failed")
    if stats.cancelled:
        remaining = stats.total - stats.processed - stats.duplicates - stats.failed
        parts.append(f"{remaining:,} not processed")
    if stats.cancelled:
        title, kind = "Cancelled", "warn"
    elif result.errors:
        title, kind = "Finished with problems", "error"
    else:
        title, kind = "Complete", "ok"
    return RunSummary(title, " · ".join(parts), _run_details(result), kind)


def _run_details(result: RunResult) -> str:
    lines: list[str] = []
    if result.errors:
        lines.append(f"Errors ({len(result.errors)}):")
        lines += [f"  {error.src}  -  {error.message}" for error in result.errors]
    if result.skipped_duplicates:
        if lines:
            lines.append("")
        lines.append(
            f"Identical file already at destination, left in place "
            f"({len(result.skipped_duplicates)}):"
        )
        lines += [f"  {move.src}  =  {move.dest}" for move in result.skipped_duplicates]
    if result.journal_path is not None:
        if lines:
            lines.append("")
        lines.append(f"Undo journal: {result.journal_path}")
    return "\n".join(lines)


def undo_summary(result: UndoResult) -> RunSummary:
    parts = []
    if result.restored:
        parts.append(f"{result.restored:,} restored")
    if result.removed:
        noun = "copy" if result.removed == 1 else "copies"
        parts.append(f"{result.removed:,} {noun} removed")
    if result.errors:
        parts.append(f"{len(result.errors):,} could not be undone")
    details = "\n".join(f"  {e.src}  -  {e.message}" for e in result.errors)
    if result.errors:
        details = "Not undone (run Undo again after fixing):\n" + details
    kind = "ok" if result.ok else "error"
    title = "Undo complete" if result.ok else "Undo finished with problems"
    return RunSummary(title, " · ".join(parts) or "Nothing changed", details, kind)


# ---------------------------------------------------------------------- review


def review_files(output: Path, config: Config) -> list[Path]:
    """Files under the output's review folders (``Videos``, ``Other``), sorted by path."""
    found: list[Path] = []
    for category in sorted(REVIEW_CATEGORIES):
        folder = Path(output) / config.folder_for(category)
        if folder.is_dir():
            found.extend(scan(folder, config))
    return sorted(found, key=lambda p: str(p).lower())


def current_category(path: Path, output: Path, config: Config) -> Category | None:
    try:
        first = path.relative_to(output).parts[0]
    except (ValueError, IndexError):
        return None
    return config.category_for_folder(first)


def review_destination(path: Path, category: Category, output: Path, config: Config) -> Path:
    """Where a reviewed file goes: the category folder, keeping ``YYYY/MM - Month``
    sub-folders only when the target category uses date folders too."""
    output = Path(output)
    target = output / config.folder_for(category)
    try:
        inner = path.relative_to(output).parts[1:-1]
    except ValueError:
        inner = ()
    if inner and category in config.date_categories:
        target = target.joinpath(*inner)
    return target / path.name


def describe_file(path: Path, root: Path | None = None) -> list[tuple[str, str]]:
    """Label/value pairs for the review info panel (location relative to ``root``)."""
    try:
        stat = path.stat()
    except OSError as exc:
        return [("Error", str(exc))]
    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    return [
        ("Type", (path.suffix.lstrip(".").upper() or "No extension") + " file"),
        ("Size", format_bytes(stat.st_size)),
        ("Modified", modified),
        ("Folder", _relative_folder(path.parent, root)),
    ]


def _relative_folder(folder: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return str(folder.relative_to(root)) or "."
        except ValueError:
            pass
    return str(folder)


def review_reason(category: Category | None) -> str:
    if category is Category.VIDEOS:
        return "Orientation could not be detected. Is it vertical, horizontal or finished?"
    if category is Category.OTHER:
        return "Unrecognised file type. Choose where it belongs, or skip it."
    return ""


# ---------------------------------------------------------------- recent runs


@dataclass(frozen=True)
class RunRecord:
    """One undoable run, read from its journal."""

    journal: Path
    started: datetime | None
    mode: str
    files: int
    source: str

    @property
    def title(self) -> str:
        verb = "Copied" if self.mode == Mode.COPY.value else "Moved"
        return f"{verb} {plural(self.files, 'file')}"


def _parse_started(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def recent_runs(output: Path, limit: int = 5) -> list[RunRecord]:
    """The newest undoable runs first (reads at most ``limit`` journals)."""
    try:
        journals = list_journals(output)
    except OSError:
        return []
    records = []
    for journal in reversed(journals[-limit:]):
        try:
            header, ops = read_journal(journal)
        except OSError:
            continue
        records.append(
            RunRecord(
                journal=journal,
                started=_parse_started(header.get("started", "")),
                mode=str(header.get("mode", Mode.MOVE.value)),
                files=len(ops),
                source=str(header.get("source", "")),
            )
        )
    return records


def format_when(when: datetime | None, now: datetime | None = None) -> str:
    """``Today, 18:40`` / ``Yesterday, 09:12`` / ``Oct 3, 18:40`` / ``Oct 3, 2024``."""
    if when is None:
        return "Unknown time"
    now = now or datetime.now(when.tzinfo)
    days = (now.date() - when.date()).days
    clock = when.strftime("%H:%M")
    if days == 0:
        return f"Today, {clock}"
    if days == 1:
        return f"Yesterday, {clock}"
    month_day = f"{when.strftime('%b')} {when.day}"
    if when.year == now.year:
        return f"{month_day}, {clock}"
    return f"{month_day}, {when.year}"


def counts_text(counts: Iterable[tuple[Category, int]]) -> str:
    return ", ".join(f"{category.label}: {count:,}" for category, count in counts)
