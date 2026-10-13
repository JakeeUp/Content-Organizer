"""Download a private copy of ffmpeg/ffprobe (Windows only), Qt-free.

Installs the gyan.dev "release essentials" build into ``<user data dir>/ffmpeg/bin``.
The download is streamed in chunks with a ``progress(bytes_done, total)`` callback
(``total`` is ``None`` when the server sends no Content-Length), can be cancelled with a
:class:`threading.Event`, has a network timeout, and is verified against the SHA-256 that
gyan.dev publishes next to the archive (``<url>.sha256``). Only ``bin/*.exe`` members are
extracted, flattened, so archive paths can never escape the install dir.

On macOS/Linux :func:`install_ffmpeg` raises :class:`UnsupportedPlatformError` whose
message explains how to install ffmpeg with the system package manager.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import sys
import threading
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from platformdirs import user_data_path

from content_organizer import APP_NAME, __version__

log = logging.getLogger(__name__)

GYAN_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DEFAULT_TIMEOUT = 30.0
_CHUNK = 256 * 1024
_SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")

#: ``progress(bytes_done, total_or_None)``
DownloadProgress = Callable[[int, int | None], None]
#: ``opener(request, timeout=...)`` returning a response with ``.read(n)`` and ``.headers``.
Opener = Callable[..., Any]


class InstallError(RuntimeError):
    """Download, verification or extraction failed."""


class InstallCancelled(InstallError):
    """The cancel event was set."""


class UnsupportedPlatformError(InstallError):
    """Automatic install is not offered on this OS."""


def install_dir() -> Path:
    """Where the private ffmpeg copy lives."""
    return user_data_path(APP_NAME, appauthor=False) / "ffmpeg"


def manual_install_hint(platform: str = sys.platform) -> str:
    """Platform-specific instructions for installing ffmpeg by hand."""
    if platform == "darwin":
        return "Install ffmpeg with Homebrew:  brew install ffmpeg"
    if platform.startswith("linux"):
        return (
            "Install ffmpeg with your package manager, e.g.  sudo apt install ffmpeg  "
            "or  sudo dnf install ffmpeg"
        )
    return "Install ffmpeg and make sure ffprobe is on your PATH: https://ffmpeg.org/download.html"


def install_ffmpeg(
    progress: DownloadProgress | None = None,
    cancel: threading.Event | None = None,
    *,
    url: str = GYAN_URL,
    dest_dir: Path | None = None,
    opener: Opener = urllib.request.urlopen,
    timeout: float = DEFAULT_TIMEOUT,
    platform: str = sys.platform,
) -> Path:
    """Download, verify and extract ffmpeg. Returns the path to ``ffprobe.exe``."""
    if platform != "win32":
        raise UnsupportedPlatformError(manual_install_hint(platform))

    target = Path(dest_dir) if dest_dir is not None else install_dir()
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "ffmpeg-download.zip.part"
    try:
        expected = fetch_expected_sha256(url + ".sha256", opener, timeout)
        actual = _download(url, archive, opener, timeout, progress, cancel)
        if actual.lower() != expected.lower():
            raise InstallError("Checksum mismatch - the download is corrupt or was tampered with")
        if cancel is not None and cancel.is_set():
            raise InstallCancelled("Cancelled")
        return extract_binaries(archive, target / "bin")
    finally:
        archive.unlink(missing_ok=True)


def fetch_expected_sha256(url: str, opener: Opener, timeout: float) -> str:
    """Read the published ``.sha256`` file and return the hex digest."""
    try:
        with opener(_request(url), timeout=timeout) as response:
            text = response.read(4096).decode("ascii", errors="replace")
    except OSError as exc:
        raise InstallError(f"Could not fetch checksum: {exc}") from exc
    match = _SHA256_RE.search(text)
    if match is None:
        raise InstallError("Checksum file did not contain a SHA-256 digest")
    return match.group(1)


def _download(
    url: str,
    dest: Path,
    opener: Opener,
    timeout: float,
    progress: DownloadProgress | None,
    cancel: threading.Event | None,
) -> str:
    digest = hashlib.sha256()
    try:
        with opener(_request(url), timeout=timeout) as response, open(dest, "wb") as fh:
            length = response.headers.get("Content-Length")
            total = int(length) if length and str(length).isdigit() else None
            done = 0
            if progress is not None:
                progress(done, total)
            while chunk := response.read(_CHUNK):
                if cancel is not None and cancel.is_set():
                    raise InstallCancelled("Cancelled")
                fh.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    except InstallError:
        raise
    except OSError as exc:  # URLError, timeouts and disk errors are all OSErrors
        raise InstallError(f"Download failed: {exc}") from exc
    return digest.hexdigest()


def extract_binaries(archive: Path, bin_dir: Path) -> Path:
    """Extract ``*/bin/*.exe`` from the archive into ``bin_dir``; return ffprobe's path."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                member = PurePosixPath(info.filename)
                if info.is_dir() or member.parent.name != "bin" or member.suffix != ".exe":
                    continue
                with zf.open(info) as src, open(bin_dir / member.name, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except (zipfile.BadZipFile, OSError) as exc:
        raise InstallError(f"Could not extract ffmpeg: {exc}") from exc
    ffprobe = bin_dir / "ffprobe.exe"
    if not ffprobe.is_file():
        raise InstallError("ffprobe.exe was not found in the downloaded archive")
    log.info("ffmpeg installed to %s", bin_dir)
    return ffprobe


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
