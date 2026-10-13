"""ffprobe failure modes: missing binary, timeouts, garbage output. ``probe`` never raises."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from content_organizer import probe as probe_mod
from content_organizer.planner import Options, build_plan
from content_organizer.probe import (
    ffprobe_version,
    find_ffprobe,
    parse_ffprobe_json,
    parse_ffprobe_output,
    parse_timestamp,
    probe,
)


def _fake_run(stdout="", returncode=0, exc=None):
    def run(*args, **kwargs):
        if exc is not None:
            raise exc
        return SimpleNamespace(stdout=stdout, stderr="boom", returncode=returncode)

    return run


@pytest.mark.parametrize(
    "exc",
    [
        subprocess.TimeoutExpired(cmd="ffprobe", timeout=15),
        FileNotFoundError(2, "No such file"),
        PermissionError(13, "denied"),
    ],
)
def test_probe_swallows_subprocess_failures(monkeypatch, tmp_path, exc):
    monkeypatch.setattr(probe_mod.subprocess, "run", _fake_run(exc=exc))
    assert probe(tmp_path / "a.mp4", Path("ffprobe")) is None
    assert ffprobe_version(Path("ffprobe")) is None


def test_probe_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(probe_mod.subprocess, "run", _fake_run(stdout="{}", returncode=1))
    assert probe(tmp_path / "a.mp4", Path("ffprobe")) is None


def test_ffprobe_version_empty_output(monkeypatch):
    monkeypatch.setattr(probe_mod.subprocess, "run", _fake_run(stdout=""))
    assert ffprobe_version(Path("ffprobe")) is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "{",
        "[]",
        "null",
        "42",
        '{"streams": "nope"}',
        '{"streams": [1, "x", null]}',
        '{"streams": [{"codec_type": "audio"}]}',
        '{"streams": [{"codec_type": "video", "width": "wide", "height": -5}]}',
        '{"streams": [{"codec_type": "video", "width": 1e400, "height": 10}]}',
        '{"streams": [{"codec_type": "video", "width": 10, "height": 20, "side_data_list": 7}]}',
        '{"streams": [{"codec_type": "video", "width": 10, "height": 20,'
        ' "side_data_list": [{"rotation": "nan"}]}]}',
        '{"streams": [{"codec_type": "video", "width": 10, "height": 20,'
        ' "tags": {"rotate": "Infinity"}}]}',
        '{"streams": [{"codec_type": "video", "width": 10, "height": 20,'
        ' "tags": {"rotate": 1e400}}]}',
        '{"streams": [{"codec_type": "video", "width": 10, "height": 20,'
        ' "sample_aspect_ratio": "0:0"}], "format": []}',
        '{"streams": [{"codec_type": "video", "width": 10, "height": 20,'
        ' "disposition": "x", "tags": ["creation_time"]}], "format": {"tags": 5}}',
        '{"streams": [{"codec_type": "video", "width": 10, "height": 20}],'
        ' "format": {"tags": {"creation_time": 12345, "CREATION_TIME": "garbage"}}}',
    ],
)
def test_corrupt_ffprobe_json_never_raises(text, monkeypatch, tmp_path):  # regression
    parse_ffprobe_output(text)  # must not raise
    monkeypatch.setattr(probe_mod.subprocess, "run", _fake_run(stdout=text))
    probe(tmp_path / "a.mp4", Path("ffprobe"))  # contract: never raises


def test_nan_rotation_is_treated_as_unrotated():
    info = parse_ffprobe_json(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1080,
                    "height": 1920,
                    "side_data_list": [{"rotation": "nan"}],
                }
            ]
        }
    )
    assert info is not None and info.rotation == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-03-05T10:20:30.000000Z", datetime(2024, 3, 5, 10, 20, 30, tzinfo=UTC)),
        ("2024-03-05T10:20:30+02:00", datetime(2024, 3, 5, 8, 20, 30, tzinfo=UTC)),
        ("2024-03-05 10:20:30", datetime(2024, 3, 5, 10, 20, 30, tzinfo=UTC)),
        ("  2024-03-05T10:20:30Z  ", datetime(2024, 3, 5, 10, 20, 30, tzinfo=UTC)),
        ("1970-01-01T00:00:00Z", None),
        ("1904-01-01T00:00:00Z", None),
        ("0000-00-00T00:00:00Z", None),
        ("garbage", None),
        ("", None),
        ("2024-13-45T99:99:99Z", None),
    ],
)
def test_parse_timestamp(value, expected):
    assert parse_timestamp(value) == expected


def test_garbage_creation_time_falls_back_to_mtime(make_tree, tmp_path, config, monkeypatch):
    src = make_tree(["clip.mp4"], mtime=datetime(2022, 6, 15, 12, 0))
    payload = json.dumps(
        {
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}],
            "format": {"tags": {"creation_time": "not-a-date"}},
        }
    )
    monkeypatch.setattr(probe_mod.subprocess, "run", _fake_run(stdout=payload))
    prober = probe_mod.make_prober(Path("ffprobe"))
    plan = build_plan(src, tmp_path / "out", Options(), prober=prober, config=config)
    dest = plan.moves[0].dest
    assert dest.parent.as_posix().endswith("VerticalVideos/2022/06 - June")


def test_ffprobe_timeout_during_planning_puts_video_in_videos(
    make_tree, tmp_path, config, monkeypatch
):
    src = make_tree(["clip.mp4"])
    monkeypatch.setattr(
        probe_mod.subprocess, "run", _fake_run(exc=subprocess.TimeoutExpired("ffprobe", 15))
    )
    plan = build_plan(
        src,
        tmp_path / "out",
        Options(date_folders=False),
        prober=probe_mod.make_prober(Path("ffprobe")),
        config=config,
    )
    assert plan.moves[0].dest.parent.name == "Videos"
    assert plan.moves[0].needs_review


def test_missing_ffprobe_plan_flags_unavailable(make_tree, tmp_path, config, monkeypatch):
    src = make_tree(["clip.mp4"])
    monkeypatch.setattr("content_organizer.planner.find_ffprobe", lambda: None)
    plan = build_plan(src, tmp_path / "out", Options(date_folders=False), config=config)
    assert not plan.probe_available
    assert plan.moves[0].dest.parent.name == "Videos"


def test_find_ffprobe_in_extra_dir_nested(tmp_path, monkeypatch):
    monkeypatch.setattr(probe_mod.shutil, "which", lambda name: None)
    exe = tmp_path / "x" / "ffmpeg-7" / "bin" / f"ffprobe{probe_mod._EXE}"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    assert find_ffprobe([tmp_path / "missing", tmp_path / "x"]) == exe


def test_find_ffprobe_none(tmp_path, monkeypatch):
    monkeypatch.setattr(probe_mod.shutil, "which", lambda name: None)
    assert find_ffprobe([tmp_path]) is None
