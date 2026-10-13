from __future__ import annotations

import hashlib
import io
import threading
import zipfile

import pytest

from content_organizer.ffmpeg_install import (
    InstallCancelled,
    InstallError,
    UnsupportedPlatformError,
    install_ffmpeg,
)


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ffmpeg-7.1-essentials_build/bin/ffprobe.exe", b"probe")
        zf.writestr("ffmpeg-7.1-essentials_build/bin/ffmpeg.exe", b"mpeg")
        zf.writestr("ffmpeg-7.1-essentials_build/doc/readme.txt", b"docs")
        zf.writestr("../../evil/bin/x.txt", b"nope")
    return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, length: bool = True) -> None:
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))} if length else {}


def fake_opener(archive: bytes, digest: str | None = None, length: bool = True):
    digest = digest or hashlib.sha256(archive).hexdigest()

    def opener(request, timeout):
        assert timeout > 0
        if request.full_url.endswith(".sha256"):
            return FakeResponse(f"{digest}  ffmpeg-release-essentials.zip\n".encode())
        return FakeResponse(archive, length)

    return opener


def test_install_verifies_and_extracts_only_binaries(tmp_path):
    archive = make_zip()
    seen = []
    ffprobe = install_ffmpeg(
        progress=lambda done, total: seen.append((done, total)),
        dest_dir=tmp_path,
        opener=fake_opener(archive),
        platform="win32",
    )
    assert ffprobe == tmp_path / "bin" / "ffprobe.exe"
    assert ffprobe.read_bytes() == b"probe"
    assert sorted(p.name for p in (tmp_path / "bin").iterdir()) == ["ffmpeg.exe", "ffprobe.exe"]
    assert not list(tmp_path.glob("*.part"))
    assert not (tmp_path / "doc").exists()
    assert seen[0] == (0, len(archive)) and seen[-1] == (len(archive), len(archive))


def test_unknown_length_reports_none_total(tmp_path):
    seen = []
    install_ffmpeg(
        progress=lambda d, t: seen.append(t),
        dest_dir=tmp_path,
        opener=fake_opener(make_zip(), length=False),
        platform="win32",
    )
    assert set(seen) == {None}


def test_checksum_mismatch(tmp_path):
    with pytest.raises(InstallError, match="Checksum"):
        install_ffmpeg(
            dest_dir=tmp_path, opener=fake_opener(make_zip(), digest="0" * 64), platform="win32"
        )
    assert not (tmp_path / "bin" / "ffprobe.exe").exists()
    assert not list(tmp_path.glob("*.part"))


def test_cancel(tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(InstallCancelled):
        install_ffmpeg(
            cancel=cancel, dest_dir=tmp_path, opener=fake_opener(make_zip()), platform="win32"
        )
    assert not list(tmp_path.glob("*.part"))


def test_network_error_is_install_error(tmp_path):
    def opener(request, timeout):
        raise OSError("no network")

    with pytest.raises(InstallError):
        install_ffmpeg(dest_dir=tmp_path, opener=opener, platform="win32")


@pytest.mark.parametrize(("platform", "hint"), [("darwin", "brew"), ("linux", "apt")])
def test_non_windows_gets_package_manager_hint(tmp_path, platform, hint):
    with pytest.raises(UnsupportedPlatformError, match=hint):
        install_ffmpeg(dest_dir=tmp_path, platform=platform)
