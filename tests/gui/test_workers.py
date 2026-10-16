"""Background tasks run the core off the GUI thread and report through signals."""

from __future__ import annotations

import hashlib
import io
import zipfile

from PyQt6.QtCore import Qt

from content_organizer.categories import Category
from content_organizer.executor import Mode
from content_organizer.gui.workers import (
    ExecuteTask,
    FfmpegInstallTask,
    PlanTask,
    StatsTask,
    UndoTask,
    start_task,
)
from content_organizer.planner import Options, build_plan
from content_organizer.probe import VideoInfo

NO_PROBE = Options(probe=False, date_folders=False)


def run(qtbot, task, timeout=10_000):
    with qtbot.waitSignal(task.done, timeout=timeout):
        start_task(task)


def test_plan_task_uses_injected_prober(qtbot, make_tree, tmp_path, config, fake_prober):
    src = make_tree(["clip.mp4", "a.png"])
    prober = fake_prober({"clip.mp4": VideoInfo(width=1080, height=1920)})
    task = PlanTask(src, tmp_path / "out", Options(date_folders=False), config, prober)
    progress, results = [], []
    task.progressed.connect(lambda done, total, path: progress.append((done, total)))
    task.succeeded.connect(results.append)
    run(qtbot, task)
    plan = results[0]
    assert {m.src.name: m.category for m in plan.moves} == {
        "clip.mp4": Category.VERTICAL,
        "a.png": Category.IMAGES,
    }
    assert progress[-1] == (2, 2)


def test_plan_task_reports_invalid_paths(qtbot, tmp_path, config):
    task = PlanTask(tmp_path, tmp_path, NO_PROBE, config)
    errors = []
    task.failed.connect(errors.append)
    run(qtbot, task)
    assert errors and "different" in errors[0]


def test_execute_task_progress_and_cancel(qtbot, make_tree, tmp_path, config):
    src = make_tree([f"f{i}.png" for i in range(10)])
    plan = build_plan(src, tmp_path / "out", NO_PROBE, config=config)

    task = ExecuteTask(plan, Mode.COPY)
    events, results = [], []
    task.progressed.connect(events.append)
    task.succeeded.connect(results.append)
    run(qtbot, task)
    assert [e.done for e in events] == list(range(1, 11))
    assert results[0].stats.copied == 10

    plan2 = build_plan(src, tmp_path / "out2", NO_PROBE, config=config)
    task2 = ExecuteTask(plan2, Mode.MOVE)
    task2.progressed.connect(lambda _e: task2.cancel(), Qt.ConnectionType.DirectConnection)
    results2 = []
    task2.succeeded.connect(results2.append)
    run(qtbot, task2)
    assert results2[0].stats.cancelled and results2[0].stats.moved == 1


def test_stats_and_undo_tasks(qtbot, make_tree, tmp_path, config):
    src = make_tree(["a.png"])
    out = tmp_path / "out"
    undo = UndoTask(out)
    nothing = []
    undo.nothing_to_undo.connect(nothing.append)
    run(qtbot, undo)
    assert nothing

    run(qtbot, ExecuteTask(build_plan(src, out, NO_PROBE, config=config), Mode.MOVE))
    stats_task = StatsTask(out, config)
    stats = []
    stats_task.succeeded.connect(stats.append)
    run(qtbot, stats_task)
    assert stats[0].total == 1

    undo = UndoTask(out)
    done = []
    undo.succeeded.connect(done.append)
    run(qtbot, undo)
    assert done[0].restored == 1 and (src / "a.png").is_file()


# ---------------------------------------------------------------------- ffmpeg


def make_archive(padding: int = 0) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("ffmpeg-7/bin/ffprobe.exe", b"MZ" + b"\0" * padding)
        zf.writestr("ffmpeg-7/bin/ffmpeg.exe", b"MZ")
    return buffer.getvalue()


class _Response(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


def opener_for(archive: bytes):
    digest = hashlib.sha256(archive).hexdigest()

    def opener(request, timeout):
        if request.full_url.endswith(".sha256"):
            return _Response(f"{digest}  ffmpeg.zip".encode())
        return _Response(archive)

    return opener


def test_ffmpeg_install_task_success(qtbot, tmp_path):
    task = FfmpegInstallTask(opener=opener_for(make_archive()), dest_dir=tmp_path, platform="win32")
    results, progress = [], []
    task.succeeded.connect(results.append)
    task.progressed.connect(lambda done, total: progress.append((done, total)))
    run(qtbot, task)
    assert results[0].name == "ffprobe.exe" and results[0].is_file()
    assert progress[-1][0] == progress[-1][1] > 0


def test_ffmpeg_install_task_cancel(qtbot, tmp_path):
    archive = make_archive(padding=3 * 1024 * 1024)  # several download chunks
    task = FfmpegInstallTask(opener=opener_for(archive), dest_dir=tmp_path, platform="win32")
    task.progressed.connect(
        lambda done, _total: task.cancel() if done else None, Qt.ConnectionType.DirectConnection
    )
    cancelled, failed = [], []
    task.cancelled.connect(lambda: cancelled.append(True))
    task.failed.connect(failed.append)
    run(qtbot, task)
    assert cancelled and not failed
    assert not (tmp_path / "bin" / "ffprobe.exe").exists()


def test_ffmpeg_install_task_unsupported_platform(qtbot, tmp_path):
    task = FfmpegInstallTask(dest_dir=tmp_path, platform="linux")
    hints = []
    task.unsupported.connect(hints.append)
    run(qtbot, task)
    assert "apt" in hints[0] or "package manager" in hints[0]


def test_window_install_flow_enables_video_analysis(qtbot, make_window, tmp_path, message_boxes):
    window = make_window(ffprobe=None)
    video = window.organize.option_rows["video"]
    assert not video.isEnabled()
    task = window.ffmpeg.start(
        opener=opener_for(make_archive()), dest_dir=tmp_path, platform="win32"
    )
    qtbot.waitUntil(lambda: not window.context.running(type(task)), timeout=10_000)
    assert video.isEnabled()
    ffprobe = window.context.ffprobe
    assert ffprobe is not None and ffprobe.name == "ffprobe.exe"
    assert not window.organize.ffmpeg_notice.isVisibleTo(window)
    assert not window.settings_page.install_button.isVisibleTo(window)
    assert [kind for kind, _ in message_boxes] == ["information"]  # exactly one success box
