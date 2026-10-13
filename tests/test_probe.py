from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from content_organizer import probe as probe_mod
from content_organizer.probe import (
    Orientation,
    VideoInfo,
    find_ffprobe,
    parse_ffprobe_json,
    parse_ffprobe_output,
    parse_timestamp,
)

DATA = Path(__file__).parent / "data"


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_iphone_display_matrix_rotation_is_vertical():
    info = parse_ffprobe_json(load("iphone_portrait.json"))
    assert info is not None
    assert (info.width, info.height) == (1920, 1080)
    assert info.rotation == 270  # -90 normalised
    assert info.display_size == (1080, 1920)
    assert info.orientation is Orientation.VERTICAL
    assert info.duration == pytest.approx(12.345)
    assert info.creation_time == datetime(2024, 3, 5, 18, 22, 41, tzinfo=UTC)


def test_rotate_tag_and_epoch_creation_time():
    info = parse_ffprobe_json(load("android_rotate_tag.json"))
    assert info is not None
    assert info.rotation == 270
    assert info.orientation is Orientation.VERTICAL
    assert info.creation_time is None  # 1970 placeholder ignored


def test_cover_art_stream_is_skipped():
    info = parse_ffprobe_json(load("cover_art_first.json"))
    assert info is not None
    assert (info.width, info.height) == (720, 1280)
    assert info.orientation is Orientation.VERTICAL


def test_plain_landscape_and_square():
    landscape = {"streams": [{"codec_type": "video", "width": 1920, "height": 1080}]}
    square = {"streams": [{"codec_type": "video", "width": 1080, "height": 1080}]}
    assert parse_ffprobe_json(landscape).orientation is Orientation.HORIZONTAL
    assert parse_ffprobe_json(square).orientation is Orientation.SQUARE


def test_sample_aspect_ratio_applied():
    # anamorphic 1440x1080 with 4:3 pixels displays as 1920x1080
    data = {
        "streams": [
            {"codec_type": "video", "width": 1440, "height": 1080, "sample_aspect_ratio": "4:3"}
        ]
    }
    assert parse_ffprobe_json(data).display_size == (1920, 1080)


@pytest.mark.parametrize(
    "text",
    ["", "not json", "[]", '{"streams": []}', '{"streams": [{"codec_type": "audio"}]}'],
)
def test_garbage_returns_none(text):
    assert parse_ffprobe_output(text) is None


def test_missing_dimensions_unknown():
    info = parse_ffprobe_json({"streams": [{"codec_type": "video", "width": 0}]})
    assert info is not None
    assert info.orientation is Orientation.UNKNOWN
    assert info.display_size is None


def test_parse_timestamp_variants():
    assert parse_timestamp("2023-07-01T10:00:00Z") == datetime(2023, 7, 1, 10, tzinfo=UTC)
    assert parse_timestamp("1904-01-01T00:00:00Z") is None
    assert parse_timestamp("garbage") is None


def test_probe_never_raises(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)

    monkeypatch.setattr(probe_mod.subprocess, "run", boom)
    assert probe_mod.probe(tmp_path / "x.mp4", Path("ffprobe")) is None


def test_probe_nonzero_exit(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="Invalid data")

    monkeypatch.setattr(probe_mod.subprocess, "run", fail)
    assert probe_mod.probe(tmp_path / "x.mp4", Path("ffprobe")) is None


def test_probe_parses_stdout(monkeypatch, tmp_path):
    text = (DATA / "iphone_portrait.json").read_text(encoding="utf-8")

    def ok(cmd, **kwargs):
        assert cmd[0] == "ffprobe-path"
        return subprocess.CompletedProcess(cmd, 0, stdout=text, stderr="")

    monkeypatch.setattr(probe_mod.subprocess, "run", ok)
    info = probe_mod.probe(tmp_path / "x.mov", Path("ffprobe-path"))
    assert isinstance(info, VideoInfo)
    assert info.orientation is Orientation.VERTICAL


def test_find_ffprobe_falls_back_to_install_dir(monkeypatch, isolated_user_dirs):
    monkeypatch.setattr(probe_mod.shutil, "which", lambda name: None)
    assert find_ffprobe() is None
    exe = "ffprobe.exe" if probe_mod.sys.platform == "win32" else "ffprobe"
    target = isolated_user_dirs / "ffmpeg" / "bin" / exe
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")
    assert find_ffprobe() == target
