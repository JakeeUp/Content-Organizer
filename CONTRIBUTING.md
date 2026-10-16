# Contributing to Content Organizer

Thanks for your interest! Bug reports, feature ideas, docs fixes and pull requests are all welcome.

## Ground rules

- **Never risk user files.** Anything that moves, copies or deletes files has to stay *plan → execute → journal*. It must never overwrite, and it must be undoable.
- **The core stays Qt-free.** Only `src/content_organizer/gui/` may import PyQt6.
- **No import-time side effects.** Core modules must not configure logging, write files or touch `sys.stdout`/`PATH` when they are imported.
- Keep the README honest: document only what is implemented.

## Development setup

You need Python **3.11+** and Git. FFmpeg is optional, but you need it to run the `ffmpeg`-marked tests.

```bash
git clone https://github.com/JakeeUp/Content-Organizer.git
cd Content-Organizer
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,gui]"
pre-commit install
```

Try it on a **throwaway** folder, never your real footage:

```bash
content-organizer organize ./sample-inbox ./sample-out --dry-run
content-organizer-gui
```

## Checks

| What | Command |
|---|---|
| Tests (everything) | `pytest` |
| Tests without real FFmpeg | `pytest -m "not ffmpeg"` |
| Only the real-FFmpeg tests | `pytest -m ffmpeg` |
| Coverage report | `pytest --cov --cov-report=term-missing` |
| Lint | `ruff check .` (auto-fix: `ruff check . --fix`) |
| Format | `ruff format .` |
| Type check (core) | `mypy` |
| Everything pre-commit runs | `pre-commit run --all-files` |

CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check`, `mypy` and `pytest` with a coverage gate on **Ubuntu, Windows and macOS × Python 3.11, 3.12 and 3.13**, and builds the sdist and wheel. Make sure the checks pass locally before opening a PR. The PR template has a short checklist.

Releases: pushing a `v*` tag runs `.github/workflows/release.yml`. It builds `ContentOrganizer.exe` (Windows) and `ContentOrganizer-macos.zip` (macOS) with PyInstaller (`packaging/pyinstaller_entry.py`), plus the sdist and wheel, and attaches them all to a GitHub Release.

### About the `ffmpeg` marker

Tests marked `@pytest.mark.ffmpeg` (in `tests/test_real_ffmpeg.py`) generate tiny real videos with `ffmpeg` and probe them with `ffprobe`. They are **skipped automatically** when either binary is missing from `PATH`. All other tests use `FakeProber` or the canned ffprobe JSON in `tests/data/`, so they need no FFmpeg. When you add probe logic, add a JSON fixture first, and a real-FFmpeg test only if the behaviour depends on how FFmpeg itself writes files.

### GUI tests

GUI tests live in `tests/gui/` and use `pytest-qt`. On a headless machine or in CI, set `QT_QPA_PLATFORM=offscreen`. Put display logic in `gui/presenters.py` (Qt-free) where you can, so it can be unit-tested without widgets.

## Branches, commits and pull requests

1. Fork the repo and create a branch from `main`: `feat/watch-mode`, `fix/rotation-180`, `docs/config-examples`.
2. Use **[Conventional Commits](https://www.conventionalcommits.org/)** for commit messages:

   ```text
   feat(rules): add 'short' and 'reel' default vertical tags
   fix(probe): honour display-matrix rotation on cover-art-first files
   docs(readme): document --clean-names
   test(executor): cover undo after partial failure
   refactor(gui): move dashboard into its own widget
   chore(ci): add Python 3.13 to the matrix
   ```

   Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `ci`, `build`. Add `!` after the type (or a `BREAKING CHANGE:` footer) for incompatible changes, such as a renamed config key.
3. Keep PRs focused, with one logical change each. Add or update tests, and add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
4. Open the PR against `main`. Say *what* changed and *why*, and include before/after output or a screenshot for user-visible changes.

## Common changes

### Adding a file extension

Add it to the right list in [`src/content_organizer/defaults.toml`](src/content_organizer/defaults.toml) under `[extensions]`. If it is a pro or rare format, consider whether it belongs in the defaults or just in the [configuration docs](docs/configuration.md) as an example. Add a case to `tests/test_rules.py`.

### Adding a naming tag

1. Add the token to the category's list under `[tags]` in `defaults.toml`. Tags are whole tokens, so pick words that are unlikely to appear inside normal file names. Check what a short tag could accidentally match. `green` is fine because `greenland` is a different token, but a tag like `a` would be a bad idea.
2. Remember that **table order is priority**. Put the tag in the category where it should win.
3. Add positive *and* negative cases to `tests/test_rules.py`, for example `"clip_short.mp4"` matches and `"shortcut.mp4"` doesn't.
4. Update the naming-tag table in `README.md` and `docs/configuration.md`.

### Adding a category

Categories are an enum, so adding one touches a few places:

1. **`categories.py`:** add a member to `Category` (its value is the default folder name), and an entry in both `CATEGORY_MEDIA` and `CATEGORY_LABELS`. If the rules can't place files in it confidently, consider adding it to `REVIEW_CATEGORIES`.
2. **`defaults.toml`:** add it to `[folders]`, add it to `[tags]` if it is tag-driven, and add it to `[layout] date_categories` if it should get date folders.
3. **`rules.py`:** only if it is reached by something *other* than a tag. For example, a new orientation bucket would need a branch in `categorize()` and probably a new `Orientation` value in `probe.py`.
4. **GUI:** give it a colour in both palettes in `theme.py`, and make sure the Library breakdown and the Review page offer it.
5. **Tests:** rules (how files reach it), planner (folder, date layout), config (folder override), stats (counted correctly).
6. **Docs:** the category tables in `README.md` and `docs/configuration.md`, plus a CHANGELOG entry.

### Changing the journal format

The journal has a `version` field. If you change its shape, bump `JOURNAL_VERSION` in `executor.py` and keep `undo_last_run` able to read older journals. Users may have undo logs from earlier releases.

## Reporting bugs

Please include:

- the output of `content-organizer doctor`
- the command you ran or the GUI steps, and what you expected
- for misclassified videos, the output of
  `ffprobe -v error -select_streams v -show_streams -show_format -of json "<file>"` (this shows only metadata, not the video)
- the relevant lines from the log file (its path is printed by `doctor`)

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
