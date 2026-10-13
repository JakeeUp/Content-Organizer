"""Shared fixtures: isolated user dirs, a source-tree builder and a fake ffprobe."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import pytest

from content_organizer.config import Config, load_config
from content_organizer.probe import VideoInfo

TreeBuilder = Callable[..., Path]


@pytest.fixture(autouse=True)
def isolated_user_dirs(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Keep tests away from the real per-user config, log and ffmpeg dirs."""
    home = tmp_path_factory.mktemp("userdirs")
    monkeypatch.setattr(
        "content_organizer.config.default_config_path", lambda: home / "config.toml"
    )
    monkeypatch.setattr("content_organizer.cli.default_config_path", lambda: home / "config.toml")
    monkeypatch.setattr(
        "content_organizer.logging_setup.log_file_path", lambda: home / "logs" / "test.log"
    )
    monkeypatch.setattr("content_organizer.ffmpeg_install.install_dir", lambda: home / "ffmpeg")
    yield home
    import logging

    for handler in list(logging.getLogger("content_organizer").handlers):
        logging.getLogger("content_organizer").removeHandler(handler)
        handler.close()


@pytest.fixture
def config() -> Config:
    return load_config()


@pytest.fixture
def make_tree(tmp_path: Path) -> TreeBuilder:
    """Create files from ``{"rel/path.ext": content}``; returns the root.

    Content may be ``str`` or ``bytes`` (default: the file name). ``mtime`` sets every
    file's modification time.
    """

    def _make(
        files: Mapping[str, str | bytes] | list[str],
        root: str = "src",
        mtime: datetime | None = None,
    ) -> Path:
        base = tmp_path / root
        base.mkdir(parents=True, exist_ok=True)
        items = files.items() if isinstance(files, Mapping) else ((f, None) for f in files)
        for rel, content in items:
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            data = content if content is not None else rel
            if isinstance(data, str):
                data = data.encode()
            path.write_bytes(data)
            if mtime is not None:
                ts = mtime.timestamp()
                os.utime(path, (ts, ts))
        return base

    return _make


class FakeProber:
    """Stands in for ffprobe: returns canned :class:`VideoInfo` per file name."""

    def __init__(
        self, infos: Mapping[str, VideoInfo | None] | None = None, default: VideoInfo | None = None
    ) -> None:
        self.infos = dict(infos or {})
        self.default = default
        self.calls: list[Path] = []

    def __call__(self, path: Path) -> VideoInfo | None:
        self.calls.append(path)
        return self.infos.get(path.name, self.default)


VERTICAL = VideoInfo(width=1080, height=1920)
HORIZONTAL = VideoInfo(width=1920, height=1080)
PHONE_PORTRAIT = VideoInfo(width=1920, height=1080, rotation=90)


@pytest.fixture
def fake_prober() -> type[FakeProber]:
    return FakeProber
