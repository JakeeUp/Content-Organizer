from __future__ import annotations

import subprocess
import sys

import pytest

from content_organizer import cli
from content_organizer.cli import EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE, main


def snapshot(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


def test_dry_run_changes_nothing(make_tree, tmp_path, capsys):
    src = make_tree(["clip_vert.mp4", "pic.png", "notes.txt", "desktop.ini"])
    out = tmp_path / "out"
    before = snapshot(tmp_path)
    code = main(["organize", str(src), str(out), "--dry-run", "--no-probe"])
    assert code == EXIT_OK
    assert snapshot(tmp_path) == before
    assert not out.exists()
    text = capsys.readouterr().out
    assert "VerticalVideos" in text and "clip_vert.mp4" in text
    assert "3 files would be organized" in text
    assert "desktop.ini" not in text
    assert "No files were changed." in text


def test_organize_then_undo(make_tree, tmp_path, capsys):
    src = make_tree(["a.png", "b.wav"])
    out = tmp_path / "out"
    assert main(["organize", str(src), str(out), "--no-probe"]) == EXIT_OK
    assert (out / "Images" / "a.png").exists()
    assert "2 files moved" in capsys.readouterr().out
    assert main(["undo", str(out)]) == EXIT_OK
    assert (src / "a.png").exists() and (src / "b.wav").exists()
    assert main(["undo", str(out)]) == EXIT_PROBLEMS


def test_copy_flag(make_tree, tmp_path):
    src = make_tree(["a.png"])
    out = tmp_path / "out"
    assert main(["organize", str(src), str(out), "--copy", "--no-probe"]) == EXIT_OK
    assert (src / "a.png").exists() and (out / "Images" / "a.png").exists()


def test_errors_give_exit_1(make_tree, tmp_path, monkeypatch):
    src = make_tree(["a.png"])

    def failing_move(src_path, dest):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr("content_organizer.executor.move_file", failing_move)
    assert main(["organize", str(src), str(tmp_path / "out"), "--no-probe"]) == EXIT_PROBLEMS


def test_same_source_and_output_is_usage_error(make_tree, capsys):
    src = make_tree(["a.png"])
    assert main(["organize", str(src), str(src), "--dry-run"]) == EXIT_USAGE
    assert "different" in capsys.readouterr().err


def test_missing_source_is_usage_error(tmp_path):
    assert main(["organize", str(tmp_path / "nope"), str(tmp_path / "out")]) == EXIT_USAGE


def test_bad_config_is_usage_error(make_tree, tmp_path):
    src = make_tree(["a.png"])
    bad = tmp_path / "bad.toml"
    bad.write_text("[tags]\nBogus = ['x']\n", encoding="utf-8")
    args = ["organize", str(src), str(tmp_path / "out"), "--dry-run", "--config", str(bad)]
    assert main(args) == EXIT_USAGE


def test_argparse_errors_exit_2():
    with pytest.raises(SystemExit) as exc:
        main(["organize"])
    assert exc.value.code == 2


def test_stats_command(make_tree, capsys):
    root = make_tree(
        [
            "VerticalVideos/2024/03 - March/a.mp4",
            "VerticalVideos/2023/12 - December/b.mp4",
            "Images/c.png",
        ]
    )
    assert main(["stats", str(root)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Vertical Videos" in out
    assert out.index("2023-12") < out.index("2024-03")


def test_doctor_reports(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_ffprobe", lambda: None)
    assert main(["doctor"]) == EXIT_PROBLEMS
    out = capsys.readouterr().out
    assert "ffprobe: not found" in out and "log file" in out


def test_python_dash_m_entry_point():
    result = subprocess.run(
        [sys.executable, "-m", "content_organizer", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "2.0.0" in result.stdout
