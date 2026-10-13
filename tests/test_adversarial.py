"""Adversarial QA: try hard to lose, clobber or misplace user files.

Each test documents an attack on the planner/executor/undo engine. Tests marked
``# regression`` reproduced a real bug before the fix described in the QA report.
"""

from __future__ import annotations

import errno
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conftest import FakeProber
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
from content_organizer.planner import Options, PlanError, build_plan
from content_organizer.probe import VideoInfo

NO_PROBE = Options(probe=False, date_folders=False)


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` (excluding journals) with its bytes."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".content-organizer" not in p.parts
    }


def all_bytes(*roots: Path) -> list[bytes]:
    """Sorted multiset of file contents under ``roots`` - proves nothing was lost."""
    return sorted(b for r in roots if r.exists() for b in snapshot(r).values())


# --------------------------------------------------------------------------- path layout


def test_output_nested_in_source_is_pruned_and_rerun_is_stable(make_tree, config):
    src = make_tree({"a.png": "A", "b.wav": "B"})
    out = src / "Organized"
    execute(build_plan(src, out, NO_PROBE, config=config))
    assert snapshot(out) == {"Audio/b.wav": b"B", "Images/a.png": b"A"}

    # A second run must not re-collect already organised files (old B1: a_1_1.png ...).
    (src / "c.png").write_text("C")
    plan = build_plan(src, out, NO_PROBE, config=config)
    assert [m.src.name for m in plan.moves] == ["c.png"]
    execute(plan)
    assert snapshot(out) == {"Audio/b.wav": b"B", "Images/a.png": b"A", "Images/c.png": b"C"}


def test_output_nested_with_different_spelling_is_still_pruned(make_tree, config):
    src = make_tree({"a.png": "A"})
    out = src / "out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    (src / "b.png").write_text("B")
    spelled = Path(str(src) + os.sep + "sub" + os.sep + ".." + os.sep + "out" + os.sep)
    plan = build_plan(src, spelled, NO_PROBE, config=config)
    assert [m.src.name for m in plan.moves] == ["b.png"]


def _case_insensitive(directory: Path) -> bool:
    probe_file = directory / "CaseProbe.tmp"
    probe_file.write_text("x")
    try:
        return (directory / "caseprobe.tmp").exists()
    finally:
        probe_file.unlink()


def test_output_nested_with_different_case_on_case_insensitive_fs(make_tree, config):
    src = make_tree({"a.png": "A"})
    if not _case_insensitive(src):
        pytest.skip("case-sensitive file system")
    out = src / "Out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    (src / "b.png").write_text("B")
    plan = build_plan(src, src / "OUT", NO_PROBE, config=config)
    assert [m.src.name for m in plan.moves] == ["b.png"]


def test_same_folder_with_different_case_is_rejected(make_tree):
    src = make_tree(["a.png"])
    if not _case_insensitive(src):
        pytest.skip("case-sensitive file system")
    with pytest.raises(PlanError):
        build_plan(src, Path(str(src).upper()), NO_PROBE)


def test_output_equal_to_source_via_dotdot_is_rejected(make_tree):
    src = make_tree(["a.png"])
    with pytest.raises(PlanError):
        build_plan(src, src / "x" / "..", NO_PROBE)


def test_output_is_a_file_is_rejected(make_tree, tmp_path):
    src = make_tree(["a.png"])
    target = tmp_path / "file.txt"
    target.write_text("not a folder")
    with pytest.raises(PlanError, match="not a folder"):
        build_plan(src, target, NO_PROBE)


def test_source_nested_in_output(make_tree, tmp_path, config):
    """Organising ``out/inbox`` into ``out`` works and never touches other output files."""
    out = make_tree({"Images/old.png": "OLD"}, root="out")
    inbox = make_tree({"new.png": "NEW", "sub/x.wav": "X"}, root="out/inbox")
    result = execute(build_plan(inbox, out, NO_PROBE, config=config))
    assert result.ok
    assert snapshot(out) == {
        "Audio/x.wav": b"X",
        "Images/new.png": b"NEW",
        "Images/old.png": b"OLD",
    }
    undo_last_run(out)
    assert snapshot(inbox) == {"new.png": b"NEW", "sub/x.wav": b"X"}
    assert snapshot(out)["Images/old.png"] == b"OLD"


def test_source_is_a_category_folder_of_output(make_tree, config):
    """Re-organising an already organised folder in place is a no-op, never a loss."""
    out = make_tree({"Images/a.png": "A"}, root="out")
    result = execute(build_plan(out / "Images", out, NO_PROBE, config=config))
    assert result.stats.moved == 0
    assert snapshot(out) == {"Images/a.png": b"A"}


def test_empty_source(make_tree, tmp_path, config):
    src = make_tree([])
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)
    assert len(plan) == 0
    result = execute(plan)
    assert result.ok and result.journal_path is None
    assert not out.exists() or list_journals(out) == []


def test_output_created_when_missing_with_parents(make_tree, tmp_path, config):
    src = make_tree(["a.png"])
    out = tmp_path / "deep" / "new" / "out"
    assert execute(build_plan(src, out, NO_PROBE, config=config)).ok
    assert (out / "Images" / "a.png").is_file()


# --------------------------------------------------------------------------- odd names


@pytest.mark.parametrize(
    "name",
    [
        "café_vert.mp4",
        "日本語の動画.mov",
        "emoji_🎬_final.mp4",
        "Ñandú 🎵 song.mp3",
        "_sfx.wav",
        "-music-.mp3",
        "noextension",
        "trailing.dots..png",
        "UPPER.PNG",
        "space name .jpg",
    ],
)
def test_odd_names_round_trip(make_tree, tmp_path, config, name):
    src = make_tree({name: name})
    out = tmp_path / "out"
    for clean in (False, True):
        plan = build_plan(src, out, Options(probe=False, clean_names=clean), config=config)
        (move,) = plan.moves
        assert move.dest.suffix.lower() == Path(name).suffix.lower()
        assert move.dest.stem.strip(" ._-"), move.dest
        assert execute(plan).ok
        assert all_bytes(out) == [name.encode()]
        assert undo_last_run(out).ok
        assert snapshot(src) == {name: name.encode()}


def test_very_long_filename(make_tree, tmp_path, config):
    """A name near the 255-char limit; a collision suffix may not fit -> recorded error."""
    name = "x" * 240 + ".png"
    src = make_tree({name: "long"})
    out = make_tree({"Images/" + name: "different-content"}, root="out")
    result = execute(build_plan(src, out, NO_PROBE, config=config))
    assert all_bytes(src, out) == sorted([b"long", b"different-content"])
    assert result.stats.moved + result.stats.failed == 1


def test_case_collision_within_one_plan(make_tree, tmp_path, config):
    """``Name.PNG`` and ``name.png`` from different folders must both survive."""
    src = make_tree({"a/Name.PNG": "upper", "b/name.png": "lower"})
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)
    result = execute(plan)
    assert result.ok
    assert all_bytes(out) == [b"lower", b"upper"]
    assert len({os.path.normcase(str(m.dest)).lower() for m in plan.moves}) == 2


def test_same_name_from_many_folders(make_tree, tmp_path, config):
    src = make_tree({f"d{i}/clip.png": f"content-{i}" for i in range(12)})
    out = tmp_path / "out"
    assert execute(build_plan(src, out, NO_PROBE, config=config)).ok
    assert len(snapshot(out)) == 12
    assert all_bytes(out) == sorted(f"content-{i}".encode() for i in range(12))


def test_clean_names_collapsing_to_same_name(make_tree, tmp_path, config):
    src = make_tree({"beach_vert.mp4": "1", "beach-VERTICAL.mp4": "22", "beach.mp4": "333"})
    out = tmp_path / "out"
    opts = Options(probe=False, date_folders=False, clean_names=True)
    assert execute(build_plan(src, out, opts, config=config)).ok
    assert all_bytes(out) == [b"1", b"22", b"333"]


# --------------------------------------------------------------------------- duplicates


def test_same_size_different_content_is_not_a_duplicate(make_tree, config):
    src = make_tree({"a.png": "AAAA"})
    out = make_tree({"Images/a.png": "BBBB"}, root="out")
    plan = build_plan(src, out, NO_PROBE, config=config)
    assert plan.moves[0].possible_duplicate
    result = execute(plan)
    assert result.stats.duplicates == 0 and result.stats.moved == 1
    assert snapshot(out) == {"Images/a.png": b"BBBB", "Images/a_1.png": b"AAAA"}


def test_zero_byte_files(make_tree, tmp_path, config):
    src = make_tree({"e1.png": b"", "sub/e1.png": b"", "e2.wav": b""})
    out = tmp_path / "out"
    result = execute(build_plan(src, out, NO_PROBE, config=config))
    # Two identical empty files with the same name: second is planned to e1_1 (not a dup
    # of a planned file), so all three are moved and nothing disappears.
    assert result.ok
    assert len(snapshot(out)) == 3


def test_zero_byte_duplicate_of_existing(make_tree, config):
    src = make_tree({"e.png": b""})
    out = make_tree({"Images/e.png": b""}, root="out")
    result = execute(build_plan(src, out, NO_PROBE, config=config))
    assert result.stats.duplicates == 1
    assert (src / "e.png").exists()


def test_directory_in_the_way_of_destination(make_tree, config):  # regression
    """A *folder* named like the destination file must not be hashed or clobbered."""
    src = make_tree({"thing": b""})
    out = make_tree({"Other/thing/keep.txt": "keep"}, root="out")
    result = execute(build_plan(src, out, NO_PROBE, config=config))
    assert result.ok, result.errors
    assert (out / "Other" / "thing" / "keep.txt").read_text() == "keep"
    assert (out / "Other" / "thing_1").is_file()


# --------------------------------------------------------------------------- failures mid-run


def test_locked_file_mid_run_is_recorded_and_run_continues(
    make_tree, tmp_path, config, monkeypatch
):
    src = make_tree({"1.png": "1", "2.png": "2", "3.png": "3"})
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)
    real_move = executor_mod.move_file

    def flaky(a, b):
        if a.name == "2.png":
            raise PermissionError(errno.EACCES, "The process cannot access the file")
        real_move(a, b)

    monkeypatch.setattr(executor_mod, "move_file", flaky)
    events = []
    result = execute(plan, progress=events.append)
    assert [e.outcome for e in events] == [Outcome.MOVED, Outcome.FAILED, Outcome.MOVED]
    assert result.stats.failed == 1 and not result.ok
    assert "cannot access" in result.errors[0].message
    _, ops = read_journal(result.journal_path)
    assert sorted(Path(op["src"]).name for op in ops) == ["1.png", "3.png"]

    monkeypatch.setattr(executor_mod, "move_file", real_move)
    assert undo_last_run(out).restored == 2
    assert snapshot(src) == {"1.png": b"1", "2.png": b"2", "3.png": b"3"}


@pytest.mark.skipif(os.name != "nt", reason="Windows file locking semantics")
def test_really_locked_file_on_windows(make_tree, tmp_path, config, monkeypatch):
    """An open handle without FILE_SHARE_DELETE blocks rename on Windows."""
    src = make_tree({"a.png": "A", "b.png": "B"})
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)
    with open(src / "a.png", "rb"):
        result = execute(plan)
    assert result.stats.failed == 1 and result.stats.moved == 1
    assert (src / "a.png").read_bytes() == b"A"
    assert not list(out.rglob("*.co-partial"))


def test_read_only_source_file(make_tree, tmp_path, config):
    src = make_tree({"ro.png": "RO"})
    (src / "ro.png").chmod(0o444)
    out = tmp_path / "out"
    try:
        execute(build_plan(src, out, NO_PROBE, config=config))
        assert all_bytes(src, out) == [b"RO"]
        undo_last_run(out)
        assert all_bytes(src, out) == [b"RO"]
    finally:
        for p in list(src.rglob("*")) + list(out.rglob("*")):
            p.chmod(0o666)


def test_cross_device_move_verifies_and_cleans(make_tree, tmp_path, config, monkeypatch):
    src = make_tree({"a.png": "payload", "b.wav": "bbb"})
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)

    def exdev(self, target):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(executor_mod.Path, "rename", exdev)
    result = execute(plan)
    assert result.ok
    assert snapshot(out) == {"Audio/b.wav": b"bbb", "Images/a.png": b"payload"}
    assert snapshot(src) == {}
    # Undo is cross-device too.
    assert undo_last_run(out).restored == 2
    assert snapshot(src) == {"a.png": b"payload", "b.wav": b"bbb"}
    assert not list(tmp_path.rglob("*.co-partial"))


def test_cross_device_size_mismatch_keeps_source(make_tree, tmp_path, config, monkeypatch):
    src = make_tree({"a.png": "payload"})
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)

    def exdev(self, target):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    def truncating_copy(a, b):
        Path(b).write_bytes(b"pay")

    monkeypatch.setattr(executor_mod.Path, "rename", exdev)
    monkeypatch.setattr(executor_mod.shutil, "copy2", truncating_copy)
    result = execute(plan)
    assert result.stats.failed == 1
    assert (src / "a.png").read_text() == "payload"
    assert not (out / "Images" / "a.png").exists()
    assert not list(out.rglob("*.co-partial"))


def test_cross_device_source_delete_fails_leaves_no_orphan_copy(  # regression
    make_tree, tmp_path, config, monkeypatch
):
    src = make_tree({"a.png": "payload"})
    out = tmp_path / "out"
    plan = build_plan(src, out, NO_PROBE, config=config)

    def exdev(self, target):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    real_unlink = Path.unlink

    def unlink(self, missing_ok=False):
        if self.name == "a.png" and self.parent == src:
            raise PermissionError(errno.EACCES, "Access is denied")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(executor_mod.Path, "rename", exdev)
    monkeypatch.setattr(executor_mod.Path, "unlink", unlink)
    result = execute(plan)
    assert result.stats.failed == 1
    assert (src / "a.png").read_text() == "payload"
    assert not (out / "Images" / "a.png").exists(), "untracked copy left in output"


def test_partial_temp_name_never_clobbers_user_file(make_tree, config, monkeypatch):  # regression
    src = make_tree({"a.png": "new"})
    out = make_tree({"Images/a.png.co-partial": "user data"}, root="out")
    plan = build_plan(src, out, NO_PROBE, config=config)
    result = execute(plan, Mode.COPY)
    assert result.ok
    assert (out / "Images" / "a.png.co-partial").read_text() == "user data"
    assert (out / "Images" / "a.png").read_text() == "new"


def test_journal_dir_blocked_by_a_file_moves_nothing(make_tree, config):  # regression
    """If the journal cannot be written, no file may be moved without a journal entry."""
    src = make_tree({"a.png": "A"})
    out = make_tree({".content-organizer": "I am a file"}, root="out")
    plan = build_plan(src, out, NO_PROBE, config=config)
    with pytest.raises(OSError):
        execute(plan)
    assert (src / "a.png").read_text() == "A"
    assert not (out / "Images").exists()


def test_progress_callback_exception_keeps_journal_consistent(make_tree, tmp_path, config):
    src = make_tree(["1.png", "2.png"])
    out = tmp_path / "out"

    def boom(event):
        raise RuntimeError("GUI died")

    with pytest.raises(RuntimeError):
        execute(build_plan(src, out, NO_PROBE, config=config), progress=boom)
    (journal,) = list_journals(out)
    _, ops = read_journal(journal)
    assert len(ops) == 1
    assert undo_last_run(out).restored == 1
    assert snapshot(src) == {"1.png": b"1.png", "2.png": b"2.png"}


# --------------------------------------------------------------------------- cancel + undo


def test_cancel_mid_run_then_undo_restores_exactly(make_tree, tmp_path, config):
    files = {f"f{i}.png": f"data{i}" for i in range(6)}
    src = make_tree(files)
    out = tmp_path / "out"
    before = snapshot(src)
    cancel = threading.Event()

    def progress(event):
        if event.done == 3:
            cancel.set()

    result = execute(
        build_plan(src, out, NO_PROBE, config=config), progress=progress, cancel=cancel
    )
    assert result.stats.cancelled and result.stats.moved == 3
    assert len(snapshot(src)) == 3
    undo = undo_last_run(out)
    assert undo.ok and undo.restored == 3
    assert snapshot(src) == before
    assert snapshot(out) == {}


def test_cancel_before_start_moves_nothing(make_tree, tmp_path, config):
    src = make_tree(["a.png"])
    cancel = threading.Event()
    cancel.set()
    result = execute(build_plan(src, tmp_path / "out", NO_PROBE, config=config), cancel=cancel)
    assert result.stats.cancelled and result.stats.moved == 0
    assert result.journal_path is None


# --------------------------------------------------------------------------- undo edge cases


def test_undo_twice_with_single_run(make_tree, tmp_path, config):
    src = make_tree(["a.png"])
    out = tmp_path / "out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    assert undo_last_run(out).ok
    with pytest.raises(NothingToUndoError):
        undo_last_run(out)
    assert snapshot(src) == {"a.png": b"a.png"}


def test_undo_is_last_in_first_out_across_runs(make_tree, tmp_path, config):
    src = make_tree({"a.png": "A"})
    out = tmp_path / "out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    (src / "b.png").write_text("B")
    execute(build_plan(src, out, NO_PROBE, config=config))
    assert len(list_journals(out)) == 2
    first = undo_last_run(out)
    assert first.restored == 1 and snapshot(src) == {"b.png": b"B"}
    second = undo_last_run(out)
    assert second.restored == 1 and snapshot(src) == {"a.png": b"A", "b.png": b"B"}


def test_undo_when_original_path_now_occupied(make_tree, tmp_path, config):
    src = make_tree({"a.png": "orig"})
    out = tmp_path / "out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    (src / "a.png").write_text("squatter")
    result = undo_last_run(out)
    assert not result.ok
    assert (src / "a.png").read_text() == "squatter"
    assert (out / "Images" / "a.png").read_text() == "orig"
    assert len(list_journals(out)) == 1  # kept for a retry


def test_undo_when_moved_file_was_deleted(make_tree, tmp_path, config):
    src = make_tree(["a.png", "b.png"])
    out = tmp_path / "out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    (out / "Images" / "a.png").unlink()
    result = undo_last_run(out)
    assert result.restored == 1 and len(result.errors) == 1
    assert "no longer exists" in result.errors[0].message


def test_undo_recreates_deleted_source_folders(make_tree, tmp_path, config):
    src = make_tree({"deep/nest/a.png": "A"})
    out = tmp_path / "out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    (src / "deep" / "nest").rmdir()
    (src / "deep").rmdir()
    assert undo_last_run(out).ok
    assert snapshot(src) == {"deep/nest/a.png": b"A"}


def test_copy_undo_deletes_only_copies(make_tree, tmp_path, config):
    src = make_tree({"a.png": "A", "b.wav": "B"})
    out = make_tree({"Images/unrelated.png": "U"}, root="out")
    execute(build_plan(src, out, NO_PROBE, config=config), Mode.COPY)
    undo = undo_last_run(out)
    assert undo.ok and undo.removed == 2
    assert snapshot(src) == {"a.png": b"A", "b.wav": b"B"}
    assert snapshot(out) == {"Images/unrelated.png": b"U"}


def test_copy_undo_keeps_copy_when_original_was_deleted(make_tree, tmp_path, config):  # regression
    """After a copy run the user may delete the inbox; undo must not destroy the only copy."""
    src = make_tree({"a.png": "A", "b.png": "B"})
    out = tmp_path / "out"
    execute(build_plan(src, out, NO_PROBE, config=config), Mode.COPY)
    (src / "a.png").unlink()
    undo = undo_last_run(out)
    assert undo.removed == 1 and len(undo.errors) == 1
    assert (out / "Images" / "a.png").read_text() == "A"
    assert all_bytes(src, out) == [b"A", b"B"]


def test_undo_with_corrupt_journal_entries(make_tree, tmp_path, config):
    src = make_tree(["a.png"])
    out = tmp_path / "out"
    result = execute(build_plan(src, out, NO_PROBE, config=config))
    with open(result.journal_path, "a", encoding="utf-8") as fh:
        fh.write('{"type": "op", "op": "move"}\n')  # missing src/dest
        fh.write("[1, 2, 3]\n")  # valid JSON, wrong shape
        fh.write("\n\n")
    undo = undo_last_run(out)
    assert undo.restored == 1
    assert any("malformed" in e.message for e in undo.errors)


def test_undo_pruning_never_removes_output_root_or_nonempty(make_tree, tmp_path, config):
    src = make_tree(["a.png", "b.png"])
    out = tmp_path / "out"
    execute(build_plan(src, out, NO_PROBE, config=config))
    (out / "Images" / "mine.txt").write_text("user file")
    undo_last_run(out)
    assert out.is_dir()
    assert (out / "Images" / "mine.txt").exists()


# --------------------------------------------------------------------------- dates


@pytest.mark.parametrize(
    "creation",
    [
        datetime(2023, 7, 14, 12, 0, tzinfo=UTC),
        datetime(9999, 12, 31, 23, 59, tzinfo=UTC),  # regression: astimezone overflow
        datetime(1, 1, 1, 0, 0, tzinfo=UTC),
    ],
)
def test_extreme_creation_times_never_crash_planning(make_tree, tmp_path, config, creation):
    src = make_tree(["clip.mp4"])
    prober = FakeProber(default=VideoInfo(width=1080, height=1920, creation_time=creation))
    plan = build_plan(src, tmp_path / "out", Options(), prober=prober, config=config)
    (move,) = plan.moves
    assert move.category is Category.VERTICAL
    assert move.dest.parent.parent.parent.name == "VerticalVideos"


def test_pre_epoch_mtime_still_planned(make_tree, tmp_path, config):  # regression (Windows)
    src = make_tree(["clip.mp4"])
    os.utime(src / "clip.mp4", (-86400 * 400, -86400 * 400))
    plan = build_plan(src, tmp_path / "out", Options(probe=False), config=config)
    assert len(plan.moves) == 1
    assert plan.moves[0].dest.name == "clip.mp4"


def test_timezone_suffixed_creation_time_buckets_locally(make_tree, tmp_path, config):
    src = make_tree(["clip.mp4"])
    when = datetime.fromisoformat("2024-03-15T12:00:00+05:30")
    prober = FakeProber(default=VideoInfo(width=1920, height=1080, creation_time=when))
    plan = build_plan(src, tmp_path / "out", Options(), prober=prober, config=config)
    local = when.astimezone()
    assert plan.moves[0].dest.parent.name.startswith(f"{local.month:02d} - ")
    assert plan.moves[0].dest.parent.parent.name == str(local.year)


def test_excluded_output_matched_by_identity_not_just_spelling(make_tree, config, monkeypatch):
    """Simulates macOS, where ``normcase`` is a no-op on a case-insensitive disk."""  # regression
    src = make_tree({"a.png": "A", "out/Images/old.png": "OLD"})
    if not _case_insensitive(src):
        pytest.skip("case-sensitive file system")
    from content_organizer import scanner

    monkeypatch.setattr(scanner, "_norm", lambda p: str(p))
    found = [p.name for p in scanner.scan(src, config, exclude=[src / "OUT"])]
    assert found == ["a.png"]


def test_case_collisions_planned_apart_even_where_normcase_is_identity(  # regression
    make_tree, tmp_path, config, monkeypatch
):
    """POSIX ``normcase`` does not fold case, but macOS disks are case-insensitive."""
    src = make_tree({"a/Name.PNG": "upper", "b/name.png": "lower"})
    monkeypatch.setattr(os.path, "normcase", lambda s: s)
    plan = build_plan(src, tmp_path / "out", NO_PROBE, config=config)
    assert len({str(m.dest).casefold() for m in plan.moves}) == 2
