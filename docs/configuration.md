# Configuration reference

Content Organizer's rules (which extensions count as video, which naming tags exist, what the output folders are called, which folders get date sub-folders, and what to skip) come from a TOML file. Nothing is hard-coded in Python.

- **Built-in defaults:** [`src/content_organizer/defaults.toml`](../src/content_organizer/defaults.toml), shipped inside the package.
- **Your overrides:** an optional `config.toml` in the per-user config directory, or any file passed with `--config FILE`.

## Where the user file lives

Run `content-organizer doctor` to see the exact path on your machine:

```console
$ content-organizer doctor
...
[ok]   config: C:\Users\you\AppData\Local\content-organizer\config.toml (not present, using defaults)
```

| OS | Default path |
|---|---|
| Windows | `%LOCALAPPDATA%\content-organizer\config.toml` |
| macOS | `~/Library/Application Support/content-organizer/config.toml` |
| Linux | `$XDG_CONFIG_HOME/content-organizer/config.toml` (usually `~/.config/...`) |

The file is optional. If it is missing, the defaults are used. A path given with `--config` **must** exist, or the command stops with exit code 2.

## How merging works

1. The defaults are loaded first.
2. Your file is merged over them **table by table, key by key**. You only write what you change.
3. **A list replaces the default list entirely.** If you set `[extensions] video = [".mxf"]`, only `.mxf` files count as video. Copy the defaults you want to keep.
4. The merged result is validated **before any file is scanned**. If it is invalid you get a clear error and exit code 2.
5. **Typos are errors, not silent no-ops.** An unknown section (`[folder]`) or key (`date_category`) is rejected, and the error lists the valid names.

```toml
# Minimal example: only renames two folders, everything else stays default
[folders]
VerticalVideos = "Shorts"
HorizontalVideos = "YouTube"
```

## Category names

Every section that refers to a category uses its **internal name**, the default folder name. This stays the same even after you rename a folder in `[folders]`.

| Name | Media type | Notes |
|---|---|---|
| `VerticalVideos` | video | Display height > width, or a vertical tag |
| `HorizontalVideos` | video | Display width ≥ height (square included), or a horizontal tag |
| `Videos` | video | Orientation unknown. Flagged for review |
| `GreenscreenEffects` | video | Tag only |
| `FinalizedVideos` | video | Tag only, or the GUI review queue |
| `Images` | image | |
| `Music` | audio | Tag only |
| `SoundEffects` | audio | Tag only |
| `Audio` | audio | Untagged audio |
| `PremiereProjects` | project | Can't have tags |
| `Other` | other | Any other file. Can't have tags. Flagged for review |

---

## `[extensions]`

Maps a **media type** to a list of file extensions. The extension is always decided first. A tag can only move a file between categories *of the same media type*.

| Key | Default |
|---|---|
| `video` | `.mp4 .mov .m4v .avi .mkv .webm .flv .wmv .mts .m2ts .3gp` |
| `image` | `.jpg .jpeg .png .gif .bmp .webp .heic .tif .tiff` |
| `audio` | `.mp3 .wav .flac .m4a .aac .ogg .opus .aif .aiff .wma` |
| `project` | `.prproj .aep .aepx .mogrt` |

- Valid keys are `video`, `image`, `audio`, `project` and `other`.
- Extensions are case-insensitive. The leading dot is optional (`"mxf"` and `".mxf"` mean the same).
- An extension that isn't listed anywhere is media type `other` and goes to `Other/`.

```toml
[extensions]
video = [".mp4", ".mov", ".m4v", ".mkv", ".webm", ".mts", ".mxf", ".braw", ".r3d"]
```

## `[tags]`

Maps a **category** to a list of naming tags. A tag matches when it is a **whole token** of the file name without its extension. Names are split on `_`, `-`, `.` and spaces, and the comparison is case-insensitive.

| Category | Default tags |
|---|---|
| `FinalizedVideos` | `final` |
| `GreenscreenEffects` | `greenscreen`, `green`, `chroma` |
| `VerticalVideos` | `vertical`, `vert`, `9x16` |
| `HorizontalVideos` | `horizontal`, `horiz`, `16x9` |
| `SoundEffects` | `sfx`, `soundeffect`, `sound` |
| `Music` | `music`, `song` |

Rules:

- **Whole tokens only.** `clip_vert.mp4` matches `vert`. `vertigo.mp4`, `holiday_greenland.mp4` and `ocean_soundtrack.wav` match nothing.
- **Same media type only.** Audio tags only apply to audio files and video tags only to video files, so `intro_music.mp4` is still a video.
- **Priority = table order.** When several tags match, the category listed first wins (`final` beats `vert`, and `sfx` beats `music`). Categories that already exist in the defaults keep their default position, even if you redefine them. A category that isn't in the defaults is checked after all the default ones.
- **Tags beat ffprobe.** `wide_shot_vert.mp4` goes to `VerticalVideos` even if the video is 16:9.
- You can write tags with or without a leading underscore. `"_vert"` and `"vert"` are the same.
- `PremiereProjects` and `Other` can't have tags. Doing so is a config error.
- `--clean-names` removes matched tag tokens from the file name: `Beach_VERT-take2.mp4` becomes `Beach-take2.mp4`. Words that only *contain* a tag are never touched, and a name is never reduced to nothing.

```toml
[tags]
VerticalVideos = ["vertical", "vert", "9x16", "short", "reel", "tiktok"]
Music = ["music", "song", "bgm"]
Audio = []          # an empty list is allowed
```

## `[folders]`

Maps a **category** to the name of its output folder.

| Category | Default folder |
|---|---|
| every category | the same as its name (`VerticalVideos` → `VerticalVideos/`, …) |

- A folder name must be a single, safe, non-empty name. It can't contain `/`, `\` or any of `< > : " | ? *`, can't contain control characters, and can't start or end with a dot. This rules out `..`, drive letters such as `C:`, hidden folders (which the scanner and dashboard would ignore), and names Windows would silently change.
- Two categories can't share a folder name (compared case-insensitively).
- The dashboard and `content-organizer stats` use this mapping to recognise categories in an organized library. If you rename a folder after organizing, rename it on disk too.

```toml
[folders]
VerticalVideos = "Shorts"
HorizontalVideos = "YouTube"
PremiereProjects = "Projects"
```

## `[layout]`

| Key | Default | Meaning |
|---|---|---|
| `date_categories` | `["VerticalVideos", "HorizontalVideos", "Videos", "FinalizedVideos"]` | Categories that get `YYYY/MM - MonthName` sub-folders when date folders are on |

- The date comes from the video's `creation_time` (read by ffprobe and converted to your local time zone). If there is none, or the file isn't a probed video, the file's modification time is used. The placeholder dates some cameras write (1904 and 1970) are ignored.
- Month names are always English (`03 - March`), so folders sort the same on every system.
- `--no-date-folders` (or the GUI toggle) turns date folders off for a run.

```toml
[layout]
date_categories = ["VerticalVideos", "HorizontalVideos", "Videos", "FinalizedVideos", "Images"]
```

> [!NOTE]
> Images aren't probed, so their date folder comes from the modification time. EXIF dates are on the roadmap.

## `[scan]`

Controls what the scanner leaves alone. Patterns are **case-insensitive shell globs** matched against the **name** of the file or folder, not the full path.

| Key | Default |
|---|---|
| `skip_files` | `desktop.ini`, `thumbs.db`, `.ds_store`, `._*`, `~$*`, `*.part`, `*.crdownload`, `*.tmp`, `*.partial`, `*.download`, `*.pek`, `*.cfa`, `*.ims` |
| `skip_dirs` | `$recycle.bin`, `system volume information`, `adobe premiere pro auto-save`, `adobe premiere pro audio previews`, `adobe premiere pro video previews`, `media cache files`, `media cache` |

These are always skipped, whatever the config says:

- hidden files and folders: names starting with `.`, and on Windows the *hidden* or *system* attribute
- symlinks
- the app's own `.content-organizer/` journal folder
- the output folder, when it sits inside the source

```toml
[scan]
# Lists replace the defaults, so keep the defaults and add your own
skip_files = [
    "desktop.ini", "thumbs.db", ".ds_store", "._*", "~$*",
    "*.part", "*.crdownload", "*.tmp", "*.partial", "*.download",
    "*.pek", "*.cfa", "*.ims",
    "*.xmp", "*.srt",                 # keep sidecars next to their originals
]
skip_dirs = [
    "$recycle.bin", "system volume information",
    "adobe premiere pro auto-save", "adobe premiere pro audio previews",
    "adobe premiere pro video previews", "media cache files", "media cache",
    "_projects",                      # don't touch my project folders
]
```

---

## Validation errors

These problems stop the run with exit code 2, before any file is touched:

| Problem | Example message |
|---|---|
| Invalid TOML or unreadable file | `Cannot read config …: Expected '=' after a key …` |
| Unknown category or media type | `tags: unknown name 'Shortz' (expected one of: VerticalVideos, …)` |
| Tags on `PremiereProjects` or `Other` | `tags.Other: tags are not supported for this category` |
| Unknown section | `unknown section [folder] (expected one of: extensions, tags, folders, layout, scan)` |
| Unknown key in a section | `[layout]: unknown key 'date_category' (expected one of: date_categories)` |
| Unsafe or empty folder name (`..`, `C:`, `.hidden`, `name.`, `a/b`) | `folders.Images must be a plain folder name (no path separators, no leading/trailing dot, none of <>:"\|?*): '..'` |
| Two categories with the same folder | `folders: two categories share the same folder name` |
| Wrong value type | `extensions.video must be a list of strings` |
| `--config` path doesn't exist | `Config file not found: …` |

`content-organizer doctor` also validates your config and reports `[err] config: …` if something is wrong.

## Other per-user paths

| What | Where (Windows) | Notes |
|---|---|---|
| Log file | `%LOCALAPPDATA%\content-organizer\Logs\content-organizer.log` | Rotating: 1 MB per file, 3 backups kept. `-v` also prints debug logs to the console |
| FFmpeg (GUI download) | `%LOCALAPPDATA%\content-organizer\ffmpeg\bin\` | Searched after `PATH`. `PATH` itself is never modified |
| Undo journals | `<output>/.content-organizer/journal-*.jsonl` | Per output folder, not per user |

On macOS and Linux the same files go in the standard [platformdirs](https://github.com/tox-dev/platformdirs) locations. `doctor` prints them.
