"""ffprobe discovery and video metadata parsing.

* :func:`find_ffprobe` returns an explicit executable path (``PATH`` first, then the
  per-user install dir used by :mod:`content_organizer.ffmpeg_install`). ``PATH`` is never
  modified.
* :func:`probe` never raises for bad or unreadable files - it returns ``None``.
* Orientation is rotation-aware: the legacy ``tags.rotate`` and the display-matrix
  ``side_data_list[].rotation`` are both honoured, and 90/270 degree rotations swap
  width and height. Non-square pixels (``sample_aspect_ratio``) are applied too.
* Square video (display width == height) is reported as :attr:`Orientation.SQUARE`;
  the rules file it under ``HorizontalVideos`` because it is not Shorts/Reels-ready.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
_EXE = ".exe" if sys.platform == "win32" else ""
# Avoid flashing a console window per probe when running under the windowed GUI.
_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Orientation(StrEnum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    SQUARE = "square"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VideoInfo:
    """What we need to know about a video. Dimensions are as *stored* (pre-rotation)."""

    width: int | None = None
    height: int | None = None
    rotation: int = 0
    """Clockwise display rotation normalised to 0, 90, 180 or 270."""
    duration: float | None = None
    creation_time: datetime | None = None
    sample_aspect_ratio: float = 1.0

    @property
    def display_size(self) -> tuple[int, int] | None:
        """(width, height) as a viewer sees it, or ``None`` if unknown."""
        if not self.width or not self.height:
            return None
        width = round(self.width * self.sample_aspect_ratio)
        height = self.height
        if self.rotation in (90, 270):
            width, height = height, width
        return width, height

    @property
    def orientation(self) -> Orientation:
        size = self.display_size
        if size is None:
            return Orientation.UNKNOWN
        width, height = size
        if height > width:
            return Orientation.VERTICAL
        if width > height:
            return Orientation.HORIZONTAL
        return Orientation.SQUARE

    def describe(self) -> str:
        """Short human description, e.g. ``"1920x1080 rotated 90 -> vertical"``."""
        if not self.width or not self.height:
            return "no video dimensions"
        text = f"{self.width}x{self.height}"
        if self.rotation:
            text += f" rotated {self.rotation}"
        return f"{text} -> {self.orientation.value}"


#: Anything that can turn a path into :class:`VideoInfo` (or ``None``). Tests inject fakes.
Prober = Callable[[Path], VideoInfo | None]


def find_ffprobe(extra_dirs: list[Path] | None = None) -> Path | None:
    """Locate ffprobe: ``PATH``, then ``extra_dirs``, then the app's install dir."""
    found = shutil.which("ffprobe")
    if found:
        return Path(found)
    from content_organizer.ffmpeg_install import install_dir  # local: avoid import cycle

    for directory in [*(extra_dirs or []), install_dir()]:
        if not directory.is_dir():
            continue
        direct = directory / f"ffprobe{_EXE}"
        if direct.is_file():
            return direct
        for candidate in sorted(directory.rglob(f"ffprobe{_EXE}")):
            if candidate.is_file():
                return candidate
    return None


def ffprobe_version(ffprobe: Path, timeout: float = 5.0) -> str | None:
    """First line of ``ffprobe -version``, or ``None`` if it cannot be run."""
    try:
        result = subprocess.run(
            [str(ffprobe), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=_CREATIONFLAGS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout.splitlines()[0].strip()


def probe(path: Path, ffprobe: Path, timeout: float = DEFAULT_TIMEOUT) -> VideoInfo | None:
    """Run ffprobe on ``path``. Returns ``None`` on any failure (logged at DEBUG)."""
    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        "-select_streams",
        "v",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=_CREATIONFLAGS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("ffprobe failed for %s: %s", path.name, exc)
        return None
    if result.returncode != 0:
        log.debug("ffprobe exit %s for %s: %s", result.returncode, path.name, result.stderr[:200])
        return None
    return parse_ffprobe_output(result.stdout)


def make_prober(ffprobe: Path, timeout: float = DEFAULT_TIMEOUT) -> Prober:
    """Bind an ffprobe executable into a :data:`Prober`."""

    def _prober(path: Path) -> VideoInfo | None:
        return probe(path, ffprobe, timeout)

    return _prober


def parse_ffprobe_output(text: str) -> VideoInfo | None:
    """Parse ffprobe's JSON text; ``None`` if it is not valid JSON or has no video."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return parse_ffprobe_json(data)
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:  # hostile JSON
        log.debug("Unusable ffprobe JSON: %s", exc)
        return None


def parse_ffprobe_json(data: Mapping[str, Any]) -> VideoInfo | None:
    """Build :class:`VideoInfo` from ffprobe's ``-show_streams -show_format`` JSON."""
    stream = _main_video_stream(data.get("streams"))
    if stream is None:
        return None
    fmt_raw = data.get("format")
    fmt: Mapping[str, Any] = fmt_raw if isinstance(fmt_raw, Mapping) else {}
    return VideoInfo(
        width=_positive_int(stream.get("width")),
        height=_positive_int(stream.get("height")),
        rotation=_rotation(stream),
        duration=_float(fmt.get("duration")) or _float(stream.get("duration")),
        creation_time=_creation_time(fmt, stream),
        sample_aspect_ratio=_ratio(stream.get("sample_aspect_ratio")),
    )


def _main_video_stream(streams: Any) -> Mapping[str, Any] | None:
    """First video stream that is not embedded cover art."""
    if not isinstance(streams, list):
        return None
    for stream in streams:
        if not isinstance(stream, Mapping) or stream.get("codec_type") != "video":
            continue
        disposition = stream.get("disposition")
        if isinstance(disposition, Mapping) and disposition.get("attached_pic") == 1:
            continue
        return stream
    return None


def _rotation(stream: Mapping[str, Any]) -> int:
    raw: Any = None
    side_data = stream.get("side_data_list")
    for side in side_data if isinstance(side_data, list) else []:
        if isinstance(side, Mapping) and "rotation" in side:
            raw = side["rotation"]
            break
    if raw is None:
        tags = stream.get("tags")
        if isinstance(tags, Mapping):
            raw = tags.get("rotate")
    value = _float(raw)
    if value is None:
        return 0
    # Display-matrix rotation is counter-clockwise (e.g. -90); normalise to 0..270.
    return int(round(value / 90.0) * 90) % 360


def _creation_time(fmt: Mapping[str, Any], stream: Mapping[str, Any]) -> datetime | None:
    for source in (fmt, stream):
        tags = source.get("tags")
        if not isinstance(tags, Mapping):
            continue
        for key, value in tags.items():
            if key.lower() == "creation_time" and isinstance(value, str):
                parsed = parse_timestamp(value)
                if parsed is not None:
                    return parsed
    return None


def parse_timestamp(value: str) -> datetime | None:
    """Parse ffprobe's ISO timestamps. Placeholder epochs (1904/1970) count as unknown."""
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if parsed.year <= 1970:
        return None
    return parsed


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _float(value: Any) -> float | None:
    """Finite float or ``None`` (NaN/Infinity from broken metadata count as missing)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _ratio(value: Any) -> float:
    if isinstance(value, str) and ":" in value:
        num, _, den = value.partition(":")
        try:
            n, d = int(num), int(den)
        except ValueError:
            return 1.0
        if n > 0 and d > 0:
            return n / d
    return 1.0
