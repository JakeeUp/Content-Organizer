from __future__ import annotations

import sys

import pytest

from content_organizer.scanner import scan


def rels(paths, root):
    return [p.relative_to(root).as_posix() for p in paths]


def test_skips_system_hidden_partial_and_journal(make_tree, config):
    root = make_tree(
        [
            "b.mp4",
            "A.jpg",
            "desktop.ini",
            "Thumbs.db",
            ".DS_Store",
            "._b.mp4",
            "movie.mp4.part",
            "file.crdownload",
            "x.tmp",
            ".hidden/inside.mp4",
            ".content-organizer/journal-1.jsonl",
            "sub/c.wav",
            "Adobe Premiere Pro Auto-Save/edit.prproj",
        ]
    )
    assert rels(scan(root, config), root) == ["A.jpg", "b.mp4", "sub/c.wav"]


def test_output_nested_in_source_is_pruned(make_tree, config):
    root = make_tree(["new.mp4", "Organized/Images/old.jpg", "Organized/Videos/v.mp4"])
    found = rels(scan(root, config, exclude=[root / "Organized"]), root)
    assert found == ["new.mp4"]


def test_exclude_compares_resolved_paths(make_tree, config):
    root = make_tree(["new.mp4", "out/old.jpg"])
    weird = root / "sub" / ".." / "out"
    assert rels(scan(root, config, exclude=[weird]), root) == ["new.mp4"]


def test_source_equal_to_exclude_yields_nothing(make_tree, config):
    root = make_tree(["a.mp4"])
    assert list(scan(root, config, exclude=[root])) == []


def test_deterministic_order(make_tree, config):
    root = make_tree(["z/1.mp4", "a/2.mp4", "m.mp4", "B.mp4"])
    assert rels(scan(root, config), root) == ["B.mp4", "m.mp4", "a/2.mp4", "z/1.mp4"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows hidden attribute")
def test_windows_hidden_attribute(make_tree, config):
    import ctypes

    root = make_tree(["visible.mp4", "secret.mp4"])
    ctypes.windll.kernel32.SetFileAttributesW(str(root / "secret.mp4"), 0x2)
    assert rels(scan(root, config), root) == ["visible.mp4"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_symlinks_skipped(make_tree, config):
    root = make_tree(["real.mp4"])
    (root / "link.mp4").symlink_to(root / "real.mp4")
    assert rels(scan(root, config), root) == ["real.mp4"]
