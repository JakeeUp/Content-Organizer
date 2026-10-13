"""Qt-free view-model helpers."""

from __future__ import annotations

from pathlib import Path

from content_organizer.categories import Category
from content_organizer.executor import FileError, Mode, RunResult, RunStats, UndoResult
from content_organizer.gui import presenters
from content_organizer.planner import PlannedMove


def test_validate_folders(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    v = presenters.validate_folders("", "")
    assert v.source.kind == v.output.kind == "neutral" and not v.ready
    assert presenters.validate_folders(str(src), str(src)).output.kind == "error"
    assert presenters.validate_folders(str(src), str(src / "out")).output.kind == "warn"
    assert presenters.validate_folders(str(src / "x"), str(tmp_path / "o")).source.kind == "error"
    ok = presenters.validate_folders(f"  {src}  ", str(tmp_path / "new"))
    assert ok.ready and "created" in ok.output.message
    (tmp_path / "file.txt").write_text("x")
    assert presenters.validate_source(str(tmp_path / "file.txt")).kind == "error"


def test_run_summary_texts(tmp_path):
    move = PlannedMove(tmp_path / "a", tmp_path / "b", Category.IMAGES, "image")
    result = RunResult(
        stats=RunStats(total=5, moved=3, duplicates=1, failed=1),
        errors=[FileError(tmp_path / "bad.png", "Access denied")],
        skipped_duplicates=[move],
    )
    summary = presenters.run_summary(result, Mode.MOVE)
    assert summary.title == "Finished with problems" and summary.kind == "error"
    assert summary.line == "3 moved · 1 duplicate skipped · 1 failed"
    assert "Access denied" in summary.details and "left in place" in summary.details

    cancelled = RunResult(stats=RunStats(total=5, copied=2, cancelled=True))
    summary = presenters.run_summary(cancelled, Mode.COPY)
    assert summary.title == "Cancelled" and "2 copied" in summary.line
    assert "3 not processed" in summary.line


def test_undo_summary(tmp_path):
    ok = presenters.undo_summary(UndoResult(journal_path=tmp_path / "j", restored=2, removed=1))
    assert ok.title == "Undo complete" and ok.line == "2 restored · 1 copy removed"
    bad = presenters.undo_summary(
        UndoResult(journal_path=tmp_path / "j", errors=[FileError(Path("x"), "exists")])
    )
    assert bad.kind == "error" and "run Undo again" in bad.details


def test_review_destination_keeps_date_folders_only_for_dated_categories(tmp_path, config):
    out = tmp_path
    src = out / "Videos" / "2024" / "03 - March" / "clip.mp4"
    assert presenters.review_destination(src, Category.VERTICAL, out, config) == (
        out / "VerticalVideos" / "2024" / "03 - March" / "clip.mp4"
    )
    assert presenters.review_destination(src, Category.MUSIC, out, config) == (
        out / "Music" / "clip.mp4"
    )


def test_format_bytes():
    assert presenters.format_bytes(512) == "512 B"
    assert presenters.format_bytes(2048) == "2.0 KB"
    assert presenters.format_bytes(5 * 1024**3) == "5.0 GB"
