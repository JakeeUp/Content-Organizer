"""Hostile config files must fail with a clear :class:`ConfigError`, never misplace files."""

from __future__ import annotations

import pytest

from content_organizer.config import ConfigError, load_config


def write(tmp_path, text, name="config.toml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[tags]\nMusic = 'song'\n", "list of strings"),
        ("[tags]\nMusic = [1, 2]\n", "list of strings"),
        ("tags = 5\n", "must be a table"),
        ("[extensions]\nvideo = '.mp4'\n", "list of strings"),
        ("[extensions]\nmovies = ['.mp4']\n", "unknown name"),
        ("[folders]\nImages = 3\n", "plain folder name"),
        ("[folders]\nImages = ''\n", "plain folder name"),
        ("[folders]\nImages = 'a/b'\n", "plain folder name"),
        ("[folders]\nImages = 'Music'\n", "share the same folder"),
        ("[folders]\nImages = 'music'\n", "share the same folder"),
        ("[layout]\ndate_categories = 'Videos'\n", "list of strings"),
        ("[layout]\ndate_categories = ['Nope']\n", "unknown name"),
        ("[scan]\nskip_files = 'x'\n", "list of strings"),
        ("[tags]\nOther = ['x']\n", "not supported"),
        ("[tags]\nPremiereProjects = ['x']\n", "not supported"),
        ("this is = not toml [", "Cannot read config"),
    ],
)
def test_bad_values_raise_clear_errors(tmp_path, text, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path, text))


@pytest.mark.parametrize(
    "folder",
    ["..", ".", ".content-organizer", ".hidden", "C:", "a:b", "bad?", "trailing."],
)
def test_folder_names_that_escape_or_hide_are_rejected(tmp_path, folder):  # regression
    """``..`` would write outside the output; ``C:`` would jump drives on Windows;
    dot-folders are skipped by the scanner and stats; trailing dots/spaces are
    silently stripped by Windows."""
    text = f"[folders]\nImages = {folder!r}\n".replace("'", '"')
    with pytest.raises(ConfigError, match=r"folders\.Images"):
        load_config(write(tmp_path, text))


@pytest.mark.parametrize(
    "text",
    [
        "[folder]\nImages = 'Pics'\n",  # typo of [folders]
        "[tag]\nMusic = ['bgm']\n",
        "[layout]\ndate_category = ['Videos']\n",
        "[scan]\nskip_file = ['*.bak']\n",
        "unknown_top_level = 1\n",
    ],
)
def test_unknown_keys_are_reported(tmp_path, text):  # regression
    """A typo used to be silently ignored, so the user's setting never applied."""
    with pytest.raises(ConfigError, match="unknown"):
        load_config(write(tmp_path, text))


def test_non_utf8_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b"[folders]\nImages = '\xff\xfe'\n")
    with pytest.raises(ConfigError, match="Cannot read config"):
        load_config(path)


def test_valid_customisation_round_trip(tmp_path):
    cfg = load_config(
        write(
            tmp_path,
            "[folders]\nVerticalVideos = 'Shorts'\n"
            "[tags]\nMusic = ['_BGM_', 'song']\n"
            "[extensions]\nvideo = ['MXF', '.mp4']\n",
        )
    )
    assert cfg.folder_for(next(c for c in cfg.folders if c.value == "VerticalVideos")) == "Shorts"
    assert ".mxf" in cfg.extensions
    assert dict(cfg.tags)[next(c for c, _ in cfg.tags if c.value == "Music")] == ("bgm", "song")


def test_default_config_file_is_picked_up(isolated_user_dirs):
    (isolated_user_dirs / "config.toml").write_text(
        "[folders]\nImages = 'Pictures'\n", encoding="utf-8"
    )
    cfg = load_config()
    assert cfg.source_path == isolated_user_dirs / "config.toml"
    assert "Pictures" in cfg.folders.values()
