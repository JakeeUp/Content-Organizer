# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-10-12

A ground-up rewrite. The tool is now a tested Python package with a Qt-free core, a CLI, and a rebuilt GUI. The focus is safety (preview, undo, no overwrites) and correct vertical/horizontal detection.

### Added

- **Dry-run preview**: `content-organizer organize --dry-run` and the GUI preview show every planned move with its reason before anything changes.
- **Undo**: every operation is appended to `<output>/.content-organizer/journal-*.jsonl` and flushed straight away. `content-organizer undo OUT` and the GUI undo reverse the last run, including interrupted runs. A partial undo keeps the remaining operations so you can try again. The journal is created **before** the first file is touched, so if it can't be written, nothing moves. Undoing a copy run never deletes a copy whose original is gone, because that copy may now be the only one.
- **Copy mode** (`--copy`) as an alternative to moving.
- **Duplicate detection**: an existing destination file with the same size and SHA-256 is skipped and reported, not stored again.
- **Cancel** for organize runs, checked between files. Files already processed stay processed and journalled.
- **Command-line interface** with `organize`, `undo`, `stats` and `doctor` subcommands, `python -m content_organizer`, and documented exit codes. Unexpected OS errors are reported as `error: …` with exit code 1, not a traceback.
- **TOML configuration**: extensions, naming tags, folder names, date layout and skip lists in a bundled `defaults.toml`, overridable per user (`config.toml`) or per run (`--config`). Validation is strict: unknown sections and keys (typos) are rejected, and folder names that could escape the output folder or be hidden or renamed by the OS (`..`, `C:`, `.name`, `name.`, `<>:"|?*`, control characters) are refused.
- **Recording-date folders**: video dates come from ffprobe `creation_time` (local time), falling back to the modified time. Placeholder 1904/1970 dates are ignored.
- **`Audio` category** for untagged audio, and a `Videos` category for videos whose orientation can't be determined.
- **Junk skipping**: hidden and system files, symlinks, partial downloads (`*.part`, `*.crdownload`, …), and Adobe cache and auto-save folders are left alone.
- **Review queue**: files in `Videos` and `Other` are flagged. The review dialog can send them to any category, with an image preview, number-key shortcuts and Previous/Skip navigation. Each review move is journaled, so it can be undone.
- **Rebuilt desktop app**: a dashboard window with drag-and-drop folder fields that check paths as you type, a filterable preview dialog, live progress with **Cancel** (Esc), run summaries, **Undo last run**, **Open output folder**, a library ring chart with category bars and a clickable monthly chart, a non-blocking FFmpeg banner, File/Run/Help menus (including Open Config Folder and Open Log Folder), keyboard shortcuts, and remembered folders and options. `content-organizer-gui` or `python -m content_organizer.gui` starts it.
- **Release builds**: tagged releases attach `ContentOrganizer.exe` (Windows), `ContentOrganizer-macos.zip` (macOS app) and the sdist and wheel.
- **Library stats / dashboard**: per-category and per-month counts for any folder (`content-organizer stats`), sorted chronologically across years.
- **Safer FFmpeg installer (Windows)**: streamed download with real progress, cancel and a timeout, verified against the published SHA-256 (fails closed), and installed into the per-user data folder. On macOS and Linux it shows package-manager instructions.
- Rotating log file in the per-user log directory, and `-v/--verbose` for console debug output.
- `pyproject.toml` packaging (src layout) with `content-organizer` and `content-organizer-gui` entry points, and `[gui]`/`[dev]` extras.
- Test suite (pytest, pytest-qt, hypothesis property tests, adversarial file-system tests) with a branch-coverage gate, plus ruff, mypy, pre-commit, and GitHub Actions CI on Ubuntu, Windows and macOS × Python 3.11–3.13. Issue and PR templates and Dependabot.
- Documentation: a new README, `CONTRIBUTING.md`, `docs/architecture.md`, `docs/configuration.md`.

### Changed

- **Plan → execute architecture**: building a plan touches no files. Execution, journalling and undo live in a separate executor.
- **Date folders** are now `YYYY/MM - MonthName` (for example `2024/03 - March`), which sort correctly and don't depend on the system language. The legacy `YYYY/MonthName` layout is still recognised by stats.
- Date folders now also apply to `FinalizedVideos` (configurable through `[layout] date_categories`).
- **Tags never override the extension**: a tag can only refine the category within the file's media type (`intro_music.mp4` stays a video).
- `--clean-names` now removes only whole, matched tag tokens and keeps the other separators: `Beach_VERT-take2.mp4` becomes `Beach-take2.mp4`.
- Square videos are filed as `HorizontalVideos` on purpose (they aren't Shorts-ready). This is now documented.
- FFmpeg is located without modifying `PATH`: first `PATH`, then the per-user install folder. On Windows ffprobe runs with no console window.
- The config, log and FFmpeg folders moved from the current working directory to the per-user platform directories.
- Personal branding was removed from the app title and code.

### Fixed

- **Output folder inside the source** was re-scanned on every run, so organized files were moved again and renamed `a_1`, `a_1_1`, …. The output is now pruned from the scan, and paths are compared after `resolve()`.
- **Rotation ignored**: phone portrait clips stored as 1920x1080 with `rotate=90` or a display-matrix rotation were filed as horizontal. The sample aspect ratio is now applied, and an attached cover-art stream that comes first is no longer mistaken for the video.
- **Substring tag matching**: `_green` matched `holiday_greenland.mp4`, `_sound` matched `soundtrack`, `_vert` matched `vertigo`, and `_project` matched `projection`. Tags are now whole, case-insensitive tokens.
- **Untagged audio** was dumped into `Uncategorized` and always flagged for review. It now goes to `Audio`.
- **Clean names mangled files**: `my_projection` became `myion`, cleaning was case-sensitive, every `_`/`-` was replaced with a space, and `_sfx.wav` became `.wav`.
- **Duplicates piled up** as `name_1`, `name_2` even when they were byte-identical.
- **Silent overwrite and partial-file risks** in cross-drive moves. They now copy to a uniquely named temporary file, check the size, rename, and only then delete. If the source can't be deleted (locked or read-only), the copy is rolled back, so no untracked second copy is left behind.
- **Bad dates and metadata**: a corrupt `creation_time` (such as year 9999), a pre-1970 modified time on Windows, or malformed ffprobe output could crash the run or silently drop the file. These now fall back to the next date source, or to no date folder.
- **Import-time side effects**: importing the engine replaced `sys.stdout`/`sys.stderr`, reconfigured root logging, and created `organizer.log` in the working directory. It could crash in read-only folders and broke test capture.
- ffmpeg detection checked for `ffmpeg` but ran `ffprobe`, so a missing ffprobe silently disabled detection.
- Hidden and system files (`desktop.ini`, `Thumbs.db`, `.DS_Store`) and partial downloads were moved into `Other`.
- Per-file errors were only logged. They are now shown in the GUI run summary, and the CLI lists them and exits with code 1.
- The monthly chart sorted months alphabetically and merged years. Clicking opened only one category's folder.
- The FFmpeg download's Cancel button didn't cancel. The success dialog appeared twice, progress assumed a fixed 77 MB size, and the prompt repeated on every launch after the user declined.
- Typed folder paths in the GUI were ignored (only Browse worked), and the GUI froze during scans because the work ran on the UI thread.
- The review dialog offered only 4 destinations, so `FinalizedVideos` couldn't be reached.
- All 11 output folders were created up front, even when empty.

### Removed

- The `Uncategorized` folder (replaced by `Audio`, with `Videos`/`Other` as the review queue).
- The `main.py` `sys.path` bootstrap and `src/organizer.py`/`src/utils.py`, replaced by the `content_organizer` package.
- `test_ffmpeg.py`, an interactive script that pytest collected as a test, replaced by real automated tests marked `ffmpeg`.
- The README instruction to run from `src/`, which wrote files into the source tree.

## [1.0.0] - 2026-01-26

### Added

- Initial release: a PyQt6 desktop app that moves files from an inbox into category folders (vertical/horizontal videos via FFmpeg, images, audio, Premiere projects).
- Optional year/month folders for videos, naming-tag overrides, and a "clean names" option.
- Monthly distribution chart, category counters and a review dialog.
- One-click FFmpeg download on Windows.

[Unreleased]: https://github.com/JakeeUp/Content-Organizer/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/JakeeUp/Content-Organizer/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/JakeeUp/Content-Organizer/releases/tag/v1.0.0
