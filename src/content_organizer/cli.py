"""Command-line interface: ``content-organizer organize|undo|stats|doctor``.

Exit codes: 0 success, 1 finished with problems (per-file errors, nothing to undo,
ffprobe missing in ``doctor``), 2 usage or configuration error, 130 interrupted.
"""

from __future__ import annotations

import argparse
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from content_organizer import __version__
from content_organizer.categories import Category
from content_organizer.config import Config, ConfigError, default_config_path, load_config
from content_organizer.executor import (
    Mode,
    NothingToUndoError,
    ProgressEvent,
    execute,
    undo_last_run,
)
from content_organizer.ffmpeg_install import install_dir, manual_install_hint
from content_organizer.logging_setup import configure_logging, log_file_path
from content_organizer.planner import Options, Plan, PlanError, build_plan
from content_organizer.probe import Prober, ffprobe_version, find_ffprobe
from content_organizer.rules import MONTH_NAMES
from content_organizer.stats import library_stats

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true", help="show debug logging")
    common.add_argument("--config", type=Path, metavar="FILE", help="use this config TOML")

    parser = argparse.ArgumentParser(
        prog="content-organizer",
        description="Sort a media inbox into VerticalVideos, HorizontalVideos, Audio, ...",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    org = sub.add_parser("organize", parents=[common], help="organize a folder")
    org.add_argument("source", type=Path, help="folder to organize (your inbox)")
    org.add_argument("output", type=Path, help="destination folder")
    org.add_argument("-n", "--dry-run", action="store_true", help="show the plan, change nothing")
    org.add_argument("--copy", action="store_true", help="copy instead of move")
    org.add_argument("--no-date-folders", action="store_true", help="no YYYY/MM subfolders")
    org.add_argument("--clean-names", action="store_true", help="strip naming tags from names")
    org.add_argument("--no-probe", action="store_true", help="skip ffprobe (videos -> Videos)")

    undo = sub.add_parser("undo", parents=[common], help="undo the last run into OUTPUT")
    undo.add_argument("output", type=Path)

    stats = sub.add_parser("stats", parents=[common], help="count files per category / month")
    stats.add_argument("folder", type=Path)

    sub.add_parser("doctor", parents=[common], help="check ffprobe, config and log locations")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # never crash printing odd file names
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    configure_logging(verbose=args.verbose)
    try:
        if args.command == "doctor":
            return cmd_doctor(args)
        config = load_config(args.config)
        if args.command == "organize":
            return cmd_organize(args, config)
        if args.command == "undo":
            return cmd_undo(args)
        return cmd_stats(args, config)
    except (ConfigError, PlanError) as exc:
        _err(f"error: {exc}")
        return EXIT_USAGE
    except KeyboardInterrupt:
        _err("\ninterrupted")
        return EXIT_INTERRUPTED
    except OSError as exc:  # e.g. the journal folder cannot be created; nothing moved
        _err(f"error: {exc}")
        return EXIT_PROBLEMS


# --------------------------------------------------------------------------- commands


def cmd_organize(args: argparse.Namespace, config: Config, prober: Prober | None = None) -> int:
    options = Options(
        date_folders=not args.no_date_folders,
        clean_names=args.clean_names,
        probe=not args.no_probe,
    )
    plan = build_plan(args.source, args.output, options, prober=prober, config=config)
    if options.probe and not plan.probe_available:
        _err("warning: ffprobe not found - videos go to 'Videos'. Run 'content-organizer doctor'.")

    if args.dry_run:
        print_plan(plan)
        return EXIT_OK
    if not plan.moves:
        print("Nothing to organize.")
        return EXIT_OK

    cancel = threading.Event()
    mode = Mode.COPY if args.copy else Mode.MOVE
    try:
        result = execute(plan, mode, progress=_ProgressLine(sys.stderr), cancel=cancel)
    except KeyboardInterrupt:
        cancel.set()
        raise
    verb = "copied" if mode is Mode.COPY else "moved"
    print(f"\n{plural(result.stats.processed, 'file')} {verb} to {plan.output}")
    if result.stats.duplicates:
        print(f"{plural(result.stats.duplicates, 'duplicate')} skipped (already in output):")
        for move in result.skipped_duplicates:
            print(f"  {_rel(move.src, plan.source)}")
    if result.errors:
        print(f"{plural(len(result.errors), 'file')} failed:")
        for error in result.errors:
            print(f"  {error.src}: {error.message}")
    if result.journal_path:
        print(f'Undo with: content-organizer undo "{plan.output}"')
    return EXIT_OK if result.ok else EXIT_PROBLEMS


def cmd_undo(args: argparse.Namespace) -> int:
    try:
        result = undo_last_run(args.output)
    except NothingToUndoError as exc:
        _err(str(exc))
        return EXIT_PROBLEMS
    restored = plural(result.restored, "moved file")
    removed = plural(result.removed, "copy", "copies")
    print(f"Restored {restored}, removed {removed}.")
    for error in result.errors:
        print(f"  could not undo {error.src}: {error.message}")
    if result.errors:
        print("Remaining operations were kept; run undo again after fixing them.")
    return EXIT_OK if result.ok else EXIT_PROBLEMS


def cmd_stats(args: argparse.Namespace, config: Config) -> int:
    folder = Path(args.folder)
    if not folder.is_dir():
        _err(f"error: not a folder: {folder}")
        return EXIT_USAGE
    stats = library_stats(folder, config)
    print(f"{plural(stats.total, 'file')} in {stats.root}\n")
    rows = [(c.label, str(stats.by_category[c])) for c in Category if stats.by_category[c]]
    print_table(("CATEGORY", "FILES"), rows)
    if stats.by_month:
        print()
        month_rows = [
            (f"{year}-{month:02d} {MONTH_NAMES[month - 1][:3]}", str(count))
            for (year, month), count in stats.month_series()
        ]
        print_table(("MONTH", "FILES"), month_rows)
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    ok = True
    ffprobe = find_ffprobe()
    if ffprobe:
        print(f"[ok]   ffprobe: {ffprobe}")
        print(f"       {ffprobe_version(ffprobe) or 'version unknown (could not run it)'}")
    else:
        ok = False
        print("[warn] ffprobe: not found - video orientation detection is disabled")
        print(f"       {manual_install_hint()}")
        if sys.platform == "win32":
            print("       (or use the GUI's one-click FFmpeg download)")
    config_path = args.config or default_config_path()
    try:
        load_config(args.config)
        state = "found" if Path(config_path).is_file() else "not present, using defaults"
        print(f"[ok]   config: {config_path} ({state})")
    except ConfigError as exc:
        ok = False
        print(f"[err]  config: {exc}")
    print(f"[info] log file: {log_file_path()}")
    print(f"[info] ffmpeg install dir: {install_dir()}")
    print(f"[info] content-organizer {__version__}, Python {sys.version.split()[0]}")
    return EXIT_OK if ok else EXIT_PROBLEMS


# --------------------------------------------------------------------------- output


def print_plan(plan: Plan, out: TextIO | None = None) -> None:
    """Readable dry-run table plus per-category summary."""
    stream = out or sys.stdout
    rows = []
    for move in plan.moves:
        dest = _rel(move.dest, plan.output)
        if move.possible_duplicate:
            dest += "  (possible duplicate)"
        rows.append((move.category.value, _rel(move.src, plan.source), "->", dest))
    if rows:
        print_table(("CATEGORY", "SOURCE", "", "DESTINATION"), rows, stream)
    total = plural(len(plan.moves), "file")
    print(f"\nDry run: {total} would be organized into {plan.output}", file=stream)
    for category in Category:
        count = plan.counts().get(category, 0)
        if count:
            print(f"  {category.label:<30} {count:>6}", file=stream)
    review = sum(1 for move in plan.moves if move.needs_review)
    if review:
        msg = f"{plural(review, 'file')} could not be placed confidently (Videos/Other)."
        print(msg, file=stream)
    print("No files were changed.", file=stream)


def print_table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], out: TextIO | None = None
) -> None:
    stream = out or sys.stdout
    widths = [max(len(str(r[i])) for r in [headers, *rows]) for i in range(len(headers))]
    for row in [headers, *rows]:
        cells = [str(cell).ljust(widths[i]) for i, cell in enumerate(row)]
        print("  ".join(cells).rstrip(), file=stream)


class _ProgressLine:
    """Single updating progress line on a TTY; silent otherwise."""

    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self.enabled = stream.isatty()

    def __call__(self, event: ProgressEvent) -> None:
        if not self.enabled:
            return
        name = event.move.src.name
        if len(name) > 50:
            name = name[:47] + "..."
        line = f"[{event.done}/{event.total}] {event.outcome.value:<9} {name}"
        self.stream.write("\r" + line.ljust(80)[:80])
        self.stream.flush()


def plural(count: int, singular: str, many: str | None = None) -> str:
    """``"1 file"``, ``"2 files"``; pass ``many`` for irregular plurals."""
    return f"{count} {singular if count == 1 else (many or singular + 's')}"


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _err(message: str) -> None:
    print(message, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
