from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conftest import HORIZONTAL, PHONE_PORTRAIT, VERTICAL, FakeProber
from content_organizer.categories import Category
from content_organizer.planner import Options, PlanError, build_plan
from content_organizer.probe import VideoInfo

MARCH = datetime(2024, 3, 15, 12, 0)


def dests(plan):
    return {m.src.name: m.dest.relative_to(plan.output).as_posix() for m in plan.moves}


def test_basic_plan(make_tree, tmp_path, config):
    src = make_tree(
        [
            "tall.mp4",
            "wide.mov",
            "phone.mov",
            "pic.png",
            "boom_sfx.wav",
            "voice.m4a",
            "edit.prproj",
            "notes.txt",
        ],
        mtime=MARCH,
    )
    prober = FakeProber({"tall.mp4": VERTICAL, "wide.mov": HORIZONTAL, "phone.mov": PHONE_PORTRAIT})
    plan = build_plan(src, tmp_path / "out", Options(), prober=prober, config=config)
    assert dests(plan) == {
        "tall.mp4": "VerticalVideos/2024/03 - March/tall.mp4",
        "wide.mov": "HorizontalVideos/2024/03 - March/wide.mov",
        "phone.mov": "VerticalVideos/2024/03 - March/phone.mov",
        "pic.png": "Images/pic.png",
        "boom_sfx.wav": "SoundEffects/boom_sfx.wav",
        "voice.m4a": "Audio/voice.m4a",
        "edit.prproj": "PremiereProjects/edit.prproj",
        "notes.txt": "Other/notes.txt",
    }
    assert plan.probe_available
    assert sorted(p.name for p in prober.calls) == ["phone.mov", "tall.mp4", "wide.mov"]
    assert plan.counts()[Category.VERTICAL] == 2
    assert [m.src.name for m in plan.moves if m.needs_review] == ["notes.txt"]


def test_plan_touches_nothing(make_tree, tmp_path, config):
    src = make_tree(["a.mp4", "b.jpg"])
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    build_plan(src, tmp_path / "out", Options(probe=False), config=config)
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


def test_creation_time_preferred_over_mtime(make_tree, tmp_path, config):
    src = make_tree(["clip.mp4"], mtime=MARCH)
    info = VideoInfo(1080, 1920, creation_time=datetime(2021, 7, 4, 12, tzinfo=UTC))
    plan = build_plan(src, tmp_path / "out", prober=FakeProber(default=info), config=config)
    assert dests(plan)["clip.mp4"] == "VerticalVideos/2021/07 - July/clip.mp4"


def test_no_date_folders_and_clean_names(make_tree, tmp_path, config):
    src = make_tree(["beach_vert.mp4", "hit_sfx.wav"])
    options = Options(date_folders=False, clean_names=True, probe=False)
    plan = build_plan(src, tmp_path / "out", options, config=config)
    assert dests(plan) == {
        "beach_vert.mp4": "VerticalVideos/beach.mp4",
        "hit_sfx.wav": "SoundEffects/hit.wav",
    }


def test_no_probe_puts_videos_in_videos(make_tree, tmp_path, config):
    src = make_tree(["clip.mp4"], mtime=MARCH)
    prober = FakeProber(default=VERTICAL)
    plan = build_plan(src, tmp_path / "out", Options(probe=False), prober=prober, config=config)
    assert dests(plan)["clip.mp4"] == "Videos/2024/03 - March/clip.mp4"
    assert prober.calls == []
    assert not plan.probe_available


def test_collisions_within_plan(make_tree, tmp_path, config):
    src = make_tree({"a/pic.png": "1", "b/pic.png": "22", "c/pic.png": "333"})
    plan = build_plan(src, tmp_path / "out", Options(probe=False), config=config)
    targets = sorted(m.dest.name for m in plan.moves)
    assert targets == ["pic.png", "pic_1.png", "pic_2.png"]


def test_collision_with_clean_names(make_tree, tmp_path, config):
    src = make_tree({"x_sfx.wav": "1", "x-SFX.wav": "22"})
    plan = build_plan(src, tmp_path / "out", Options(clean_names=True, probe=False), config=config)
    assert sorted(m.dest.name for m in plan.moves) == ["x.wav", "x_1.wav"]


def test_existing_destination(make_tree, tmp_path, config):
    src = make_tree({"same.png": "abc", "diff.png": "abc"})
    out = make_tree({"Images/same.png": "xyz", "Images/diff.png": "longer"}, root="out")
    plan = build_plan(src, out, Options(probe=False), config=config)
    by_name = {m.src.name: m for m in plan.moves}
    assert by_name["same.png"].dest == out / "Images" / "same.png"
    assert by_name["same.png"].possible_duplicate
    assert by_name["diff.png"].dest == out / "Images" / "diff_1.png"
    assert not by_name["diff.png"].possible_duplicate


def test_output_inside_source_is_excluded(make_tree, config):
    src = make_tree(["new.png", "Organized/Images/old.png"])
    plan = build_plan(src, src / "Organized", Options(probe=False), config=config)
    assert [m.src.name for m in plan.moves] == ["new.png"]


@pytest.mark.parametrize("case", ["same", "missing", "file"])
def test_invalid_paths(tmp_path, config, case):
    src = tmp_path / "src"
    src.mkdir()
    out: Path = {"same": src, "missing": tmp_path / "out", "file": tmp_path / "f.txt"}[case]
    if case == "file":
        out.write_text("x")
    if case == "missing":
        src = tmp_path / "nope"
    with pytest.raises(PlanError):
        build_plan(src, out, Options(probe=False), config=config)


def test_progress_and_cancel(make_tree, tmp_path, config):
    src = make_tree(["1.png", "2.png", "3.png"])
    cancel = threading.Event()
    seen = []

    def progress(done, total, path):
        seen.append((done, total))
        if done == 2:
            cancel.set()

    plan = build_plan(
        src, tmp_path / "out", Options(probe=False), config=config, progress=progress, cancel=cancel
    )
    assert seen == [(1, 3), (2, 3)]
    assert plan.cancelled
    assert len(plan) == 2


def test_custom_folder_names(make_tree, tmp_path):
    from content_organizer.config import build_config, load_defaults_dict, merge

    cfg = build_config(merge(load_defaults_dict(), {"folders": {"VerticalVideos": "Shorts"}}))
    src = make_tree(["a_vert.mp4"])
    plan = build_plan(src, tmp_path / "out", Options(date_folders=False, probe=False), config=cfg)
    assert dests(plan)["a_vert.mp4"] == "Shorts/a_vert.mp4"
