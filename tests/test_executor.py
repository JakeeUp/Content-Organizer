from __future__ import annotations

import errno
import json
import threading

import pytest

from content_organizer import executor as executor_mod
from content_organizer.categories import Category
from content_organizer.executor import (
    Mode,
    NothingToUndoError,
    Outcome,
    execute,
    list_journals,
    read_journal,
    undo_last_run,
)
from content_organizer.planner import Options, build_plan

NO_PROBE = Options(probe=False, date_folders=False)


def files_under(root):
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".content-organizer" not in p.parts
    )


def test_move_and_journal(make_tree, tmp_path, config):
    src = make_tree(["a.png", "sub/b.wav", "c_vert.mp4"])
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)
    events = []
    result = execute(plan, Mode.MOVE, progress=events.append)

    assert result.ok
    assert result.stats.moved == 3
    assert result.stats.per_category[Category.AUDIO] == 1
    assert files_under(src) == []
    assert files_under(out) == ["Audio/b.wav", "Images/a.png", "VerticalVideos/c_vert.mp4"]
    assert [e.done for e in events] == [1, 2, 3]
    assert all(e.outcome is Outcome.MOVED for e in events)

    header, ops = read_journal(result.journal_path)
    assert header["mode"] == "move" and header["version"] == 1
    assert {op["category"] for op in ops} == {"Images", "Audio", "VerticalVideos"}
    assert all(op["op"] == "move" for op in ops)


def test_undo_restores_moves(make_tree, tmp_path, config):
    src = make_tree(["a.png", "deep/er/b.wav"])
    out = tmp_path / "out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    result = undo_last_run(out)
    assert result.ok and result.restored == 2
    assert files_under(src) == ["a.png", "deep/er/b.wav"]
    assert files_under(out) == []
    assert not any(out.glob("Images"))  # empty category folders pruned
    assert list_journals(out) == []
    assert list((out / ".content-organizer").glob("*.undone"))
    with pytest.raises(NothingToUndoError):
        undo_last_run(out)


def test_undo_refuses_to_clobber_and_can_retry(make_tree, tmp_path, config):
    src = make_tree({"a.png": "orig", "b.png": "orig-b"})
    out = tmp_path / "out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    (src / "a.png").write_text("new file in the way")

    result = undo_last_run(out)
    assert result.restored == 1
    assert len(result.errors) == 1 and "already exists" in result.errors[0].message
    assert (src / "a.png").read_text() == "new file in the way"
    assert (out / "Images" / "a.png").exists()

    (src / "a.png").unlink()
    retry = undo_last_run(out)
    assert retry.ok and retry.restored == 1
    assert (src / "a.png").read_text() == "orig"


def test_copy_mode_and_undo(make_tree, tmp_path, config):
    src = make_tree(["a.png", "b.mp4"])
    out = tmp_path / "out"
    result = execute(build_plan(src, out, NO_PROBE, config=config), Mode.COPY)
    assert result.stats.copied == 2 and result.stats.moved == 0
    assert files_under(src) == ["a.png", "b.mp4"]
    assert files_under(out) == ["Images/a.png", "Videos/b.mp4"]

    (out / "Videos" / "b.mp4").write_text("edited after copy - keep me")
    undo = undo_last_run(out)
    assert undo.removed == 1 and len(undo.errors) == 1
    assert files_under(src) == ["a.png", "b.mp4"]
    assert files_under(out) == ["Videos/b.mp4"]


def test_duplicate_is_skipped_and_source_kept(make_tree, tmp_path, config):
    src = make_tree({"same.png": "identical", "clash.png": "AAAA"})
    out = make_tree({"Images/same.png": "identical", "Images/clash.png": "BBBB"}, root="out")
    plan = build_plan(src, out, NO_PROBE, config=config)
    result = execute(plan, Mode.MOVE)
    assert result.stats.duplicates == 1
    assert [m.src.name for m in result.skipped_duplicates] == ["same.png"]
    assert (src / "same.png").exists()  # left alone in move mode
    # same size but different content -> renamed at execution time, never overwritten
    assert (out / "Images" / "clash.png").read_text() == "BBBB"
    assert (out / "Images" / "clash_1.png").read_text() == "AAAA"


def test_destination_appearing_after_planning(make_tree, tmp_path, config):
    src = make_tree({"a.png": "mine"})
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)
    (out / "Images").mkdir(parents=True)
    (out / "Images" / "a.png").write_text("someone else's")
    execute(plan)
    assert (out / "Images" / "a.png").read_text() == "someone else's"
    assert (out / "Images" / "a_1.png").read_text() == "mine"


def test_cancel_stops_between_files(make_tree, tmp_path, config):
    src = make_tree(["1.png", "2.png", "3.png"])
    out = tmp_path / "out"
    cancel = threading.Event()

    def progress(event):
        if event.done == 1:
            cancel.set()

    result = execute(
        build_plan(src, out, NO_PROBE, config=config), progress=progress, cancel=cancel
    )
    assert result.stats.cancelled and not result.ok
    assert result.stats.moved == 1
    assert files_under(src) == ["2.png", "3.png"]
    _, ops = read_journal(result.journal_path)
    assert len(ops) == 1


def test_per_file_errors_are_collected(make_tree, tmp_path, config):
    src = make_tree(["a.png", "b.png"])
    plan = build_plan(src, tmp_path / "out", NO_PROBE, config=config)
    (src / "a.png").unlink()  # vanished after planning
    events = []
    result = execute(plan, progress=events.append)
    assert result.stats.failed == 1 and result.stats.moved == 1
    assert result.errors[0].src.name == "a.png"
    assert [e.outcome for e in events] == [Outcome.FAILED, Outcome.MOVED]


def test_no_journal_when_nothing_done(make_tree, tmp_path, config):
    src = make_tree(["same.png"])
    out = make_tree({"Images/same.png": "same.png"}, root="out")
    result = execute(build_plan(src, out, NO_PROBE, config=config))
    assert result.journal_path is None
    assert list_journals(out) == []


def test_cross_device_move_falls_back_to_copy(make_tree, tmp_path, config, monkeypatch):
    src = make_tree({"a.png": "payload"})
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)

    def exdev(self, target):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(executor_mod.Path, "rename", exdev)
    result = execute(plan)
    assert result.ok
    assert not (src / "a.png").exists()
    assert (out / "Images" / "a.png").read_text() == "payload"
    assert not list((out / "Images").glob("*.co-partial"))


def test_torn_journal_line_is_ignored(make_tree, tmp_path, config):
    src = make_tree(["a.png"])
    out = tmp_path / "out"
    result = execute(build_plan(src, out, NO_PROBE, config=config))
    with open(result.journal_path, "a", encoding="utf-8") as fh:
        fh.write('{"type": "op", "src": "trunc')
    _, ops = read_journal(result.journal_path)
    assert len(ops) == 1
    assert undo_last_run(out).restored == 1


def test_journal_is_jsonl(make_tree, tmp_path, config):
    src = make_tree(["a.png"])
    result = execute(build_plan(src, tmp_path / "out", NO_PROBE, config=config))
    lines = result.journal_path.read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in lines]
    assert [e["type"] for e in entries] == ["run", "op"]
    assert set(entries[1]) == {"type", "op", "src", "dest", "category", "size", "ts"}
