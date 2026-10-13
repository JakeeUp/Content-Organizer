"""More CLI behaviour: exit codes, dry-run purity, doctor/stats/undo output."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from conftest import VERTICAL, FakeProber
from content_organizer import cli
from content_organizer.cli import EXIT_INTERRUPTED, EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE, main


def tree_state(root: Path) -> dict[str, tuple[bool, int, bytes | None]]:
    """Every path under ``root`` with (is_dir, mtime_ns, bytes)."""
    state = {}
    for p in sorted(root.rglob("*")):
        st = p.stat()
        state[p.relative_to(root).as_posix()] = (
            p.is_dir(),
            st.st_mtime_ns if p.is_file() else 0,
            p.read_bytes() if p.is_file() else None,
        )
    return state


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--copy"],
        ["--clean-names"],
        ["--no-date-folders"],
        ["--copy", "--clean-names", "--no-date-folders"],
    ],
)
def test_dry_run_writes_nothing_anywhere(make_tree, tmp_path, flags, capsys):
    make_tree(["clip_vert.mp4", "a/b/pic.png", "song_music.mp3", "x.txt"])
    make_tree({"Images/pic.png": "a/b/pic.png"}, root="out")  # existing output
    src, out = tmp_path / "src", tmp_path / "out"
    before = tree_state(tmp_path)
    assert main(["organize", str(src), str(out), "--dry-run", "--no-probe", *flags]) == EXIT_OK
    assert tree_state(tmp_path) == before
    assert not (out / ".content-organizer").exists()
    text = capsys.readouterr().out
    assert "(possible duplicate)" in text
    assert "No files were changed." in text


def test_dry_run_with_output_inside_source(make_tree, capsys):
    src = make_tree(["a.png"])
    before = tree_state(src)
    assert main(["organize", str(src), str(src / "out"), "-n", "--no-probe"]) == EXIT_OK
    assert tree_state(src) == before


def test_dry_run_review_count_and_probe_warning(make_tree, tmp_path, monkeypatch, capsys):
    src = make_tree(["clip.mp4", "notes.txt"])
    monkeypatch.setattr("content_organizer.planner.find_ffprobe", lambda: None)
    assert main(["organize", str(src), str(tmp_path / "out"), "-n"]) == EXIT_OK
    captured = capsys.readouterr()
    assert "ffprobe not found" in captured.err
    assert "2 files could not be placed confidently" in captured.out


def test_organize_with_injected_prober(make_tree, tmp_path, capsys):
    src = make_tree(["clip.mp4"])
    args = cli.build_parser().parse_args(
        ["organize", str(src), str(tmp_path / "out"), "--no-date-folders"]
    )
    code = cli.cmd_organize(args, cli.load_config(), prober=FakeProber(default=VERTICAL))
    assert code == EXIT_OK
    assert (tmp_path / "out" / "VerticalVideos" / "clip.mp4").exists()


def test_nothing_to_organize(make_tree, tmp_path, capsys):
    src = make_tree(["desktop.ini"])
    assert main(["organize", str(src), str(tmp_path / "out"), "--no-probe"]) == EXIT_OK
    assert "Nothing to organize" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_duplicates_and_errors_are_listed(make_tree, tmp_path, monkeypatch, capsys):
    src = make_tree({"same.png": "S", "bad.png": "B"})
    out = make_tree({"Images/same.png": "S"}, root="out")
    real = cli.execute.__globals__["move_file"]

    def flaky(a, b):
        if a.name == "bad.png":
            raise PermissionError(13, "Access is denied")
        real(a, b)

    monkeypatch.setattr("content_organizer.executor.move_file", flaky)
    assert main(["organize", str(src), str(out), "--no-probe"]) == EXIT_PROBLEMS
    text = capsys.readouterr().out
    assert "1 duplicate skipped" in text and "same.png" in text
    assert "1 file failed" in text and "Access is denied" in text


def test_undo_with_no_journal(tmp_path, capsys):
    (tmp_path / "out").mkdir()
    assert main(["undo", str(tmp_path / "out")]) == EXIT_PROBLEMS
    assert "No organizer runs to undo" in capsys.readouterr().err


def test_undo_on_missing_folder(tmp_path, capsys):
    assert main(["undo", str(tmp_path / "does-not-exist")]) == EXIT_PROBLEMS


def test_undo_partial_reports_and_exit_1(make_tree, tmp_path, capsys):
    src = make_tree(["a.png", "b.png"])
    out = tmp_path / "out"
    assert main(["organize", str(src), str(out), "--no-probe"]) == EXIT_OK
    (src / "a.png").write_text("in the way")
    capsys.readouterr()
    assert main(["undo", str(out)]) == EXIT_PROBLEMS
    text = capsys.readouterr().out
    assert "Restored 1 moved file," in text
    assert "could not undo" in text and "run undo again" in text


def test_copy_undo_message(make_tree, tmp_path, capsys):
    src = make_tree(["a.png"])
    out = tmp_path / "out"
    assert main(["organize", str(src), str(out), "--copy", "--no-probe"]) == EXIT_OK
    assert "1 file copied" in capsys.readouterr().out
    assert main(["undo", str(out)]) == EXIT_OK
    assert "removed 1 copy." in capsys.readouterr().out


def test_stats_output(make_tree, capsys):
    root = make_tree(
        [
            "VerticalVideos/2024/03 - March/a.mp4",
            "VerticalVideos/2024/03 - March/b.mp4",
            "HorizontalVideos/2024/01 - January/c.mp4",
            "Images/d.png",
            "loose.wav",
        ]
    )
    assert main(["stats", str(root)]) == EXIT_OK
    out = capsys.readouterr().out
    assert out.startswith("5 files in ")
    assert "CATEGORY" in out and "MONTH" in out
    lines = {line.split("  ")[0].strip(): line.split()[-1] for line in out.splitlines() if line}
    assert lines["Vertical Videos"] == "2"
    assert lines["Horizontal Videos"] == "1"
    assert lines["Audio"] == "1"
    assert lines["2024-03 Mar"] == "2"


def test_stats_empty_folder(tmp_path, capsys):
    assert main(["stats", str(tmp_path)]) == EXIT_OK
    assert capsys.readouterr().out.startswith("0 files in ")


def test_stats_not_a_folder(tmp_path, capsys):
    assert main(["stats", str(tmp_path / "nope")]) == EXIT_USAGE
    assert "not a folder" in capsys.readouterr().err


def test_doctor_all_ok(monkeypatch, capsys, tmp_path):
    fake = tmp_path / "ffprobe"
    monkeypatch.setattr(cli, "find_ffprobe", lambda: fake)
    monkeypatch.setattr(cli, "ffprobe_version", lambda p: "ffprobe version 7.1")
    assert main(["doctor"]) == EXIT_OK
    out = capsys.readouterr().out
    assert f"[ok]   ffprobe: {fake}" in out
    assert "ffprobe version 7.1" in out
    assert "not present, using defaults" in out
    assert "ffmpeg install dir" in out and "content-organizer 2.0.0" in out


def test_doctor_unrunnable_ffprobe(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "find_ffprobe", lambda: tmp_path / "ffprobe")
    monkeypatch.setattr(cli, "ffprobe_version", lambda p: None)
    assert main(["doctor"]) == EXIT_OK
    assert "version unknown" in capsys.readouterr().out


def test_doctor_bad_config(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "find_ffprobe", lambda: tmp_path / "ffprobe")
    monkeypatch.setattr(cli, "ffprobe_version", lambda p: "v")
    bad = tmp_path / "bad.toml"
    bad.write_text("[folders]\nImages = '..'\n", encoding="utf-8")
    assert main(["doctor", "--config", str(bad)]) == EXIT_PROBLEMS
    assert "[err]  config:" in capsys.readouterr().out


def test_doctor_found_user_config(monkeypatch, capsys, tmp_path, isolated_user_dirs):
    monkeypatch.setattr(cli, "find_ffprobe", lambda: tmp_path / "ffprobe")
    monkeypatch.setattr(cli, "ffprobe_version", lambda p: "v")
    (isolated_user_dirs / "config.toml").write_text("", encoding="utf-8")
    assert main(["doctor"]) == EXIT_OK
    assert "(found)" in capsys.readouterr().out


def test_missing_explicit_config_is_usage_error(make_tree, tmp_path, capsys):
    src = make_tree(["a.png"])
    code = main(["organize", str(src), str(tmp_path / "o"), "--config", str(tmp_path / "x.toml")])
    assert code == EXIT_USAGE
    assert "Config file not found" in capsys.readouterr().err


def test_output_is_file_is_usage_error(make_tree, tmp_path):
    src = make_tree(["a.png"])
    (tmp_path / "f").write_text("x")
    assert main(["organize", str(src), str(tmp_path / "f"), "--no-probe"]) == EXIT_USAGE


def test_no_command_is_usage_error():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "2.0.0" in capsys.readouterr().out


def test_keyboard_interrupt_exit_130(make_tree, tmp_path, monkeypatch, capsys):
    src = make_tree(["a.png", "b.png"])

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("content_organizer.executor.move_file", interrupted)
    assert main(["organize", str(src), str(tmp_path / "out"), "--no-probe"]) == EXIT_INTERRUPTED
    assert "interrupted" in capsys.readouterr().err


def test_os_error_is_reported_not_traceback(make_tree, tmp_path, capsys):  # regression
    src = make_tree(["a.png"])
    out = make_tree({".content-organizer": "blocking file"}, root="out")
    assert main(["organize", str(src), str(out), "--no-probe"]) == EXIT_PROBLEMS
    assert "error:" in capsys.readouterr().err
    assert (src / "a.png").exists()


def test_progress_line_on_tty():
    class Tty(io.StringIO):
        def isatty(self):
            return True

    from content_organizer.executor import Outcome, ProgressEvent
    from content_organizer.planner import PlannedMove

    stream = Tty()
    line = cli._ProgressLine(stream)
    move = PlannedMove(Path("x" * 80 + ".png"), Path("o/x.png"), cli.Category.IMAGES, "r")
    line(ProgressEvent(1, 2, move, Outcome.MOVED, None))
    text = stream.getvalue()
    assert text.startswith("\r[1/2] moved")
    assert "..." in text and len(text) == 81


def test_progress_line_silent_when_not_tty():
    stream = io.StringIO()
    line = cli._ProgressLine(stream)
    assert not line.enabled


def test_unicode_names_print_without_crashing(make_tree, tmp_path, capsys):
    src = make_tree(["日本語_🎬.png"])
    assert main(["organize", str(src), str(tmp_path / "out"), "-n", "--no-probe"]) == EXIT_OK
    assert "No files were changed." in capsys.readouterr().out


def test_relative_paths_are_resolved(make_tree, tmp_path, monkeypatch):
    make_tree(["a.png"])
    monkeypatch.chdir(tmp_path)
    assert main(["organize", "src", "out", "--no-probe"]) == EXIT_OK
    assert (tmp_path / "out" / "Images" / "a.png").exists()


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "0 files"), (1, "1 file"), (2, "2 files"), (1000, "1000 files")],
)
def test_plural(count, expected):
    assert cli.plural(count, "file") == expected


def test_plural_irregular():
    assert cli.plural(1, "copy", "copies") == "1 copy"
    assert cli.plural(3, "copy", "copies") == "3 copies"


def test_singular_messages_in_dry_run(make_tree, tmp_path, capsys):
    src = make_tree(["notes.txt"])
    assert main(["organize", str(src), str(tmp_path / "out"), "-n", "--no-probe"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Dry run: 1 file would be organized" in out
    assert "1 file could not be placed confidently" in out
