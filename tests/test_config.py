from __future__ import annotations

from pathlib import Path

import pytest

from content_organizer.categories import Category, MediaType
from content_organizer.config import ConfigError, load_config, merge


def test_defaults_load(config):
    assert config.extensions[".mp4"] is MediaType.VIDEO
    assert config.folder_for(Category.AUDIO) == "Audio"
    assert Category.VERTICAL in config.date_categories
    assert "desktop.ini" in config.skip_files
    assert config.source_path is None


def test_merge_tables_and_replace_lists():
    base = {"a": {"x": 1, "y": [1, 2]}, "b": 1}
    assert merge(base, {"a": {"y": [3]}}) == {"a": {"x": 1, "y": [3]}, "b": 1}


def test_user_file_overrides(tmp_path: Path):
    user = tmp_path / "config.toml"
    user.write_text(
        '[folders]\nVerticalVideos = "Shorts"\n'
        '[tags]\nMusic = ["bgm"]\n'
        '[extensions]\nvideo = [".mp4", "MXF"]\n',
        encoding="utf-8",
    )
    cfg = load_config(user)
    assert cfg.source_path == user
    assert cfg.folder_for(Category.VERTICAL) == "Shorts"
    assert cfg.folder_for(Category.HORIZONTAL) == "HorizontalVideos"
    assert dict(cfg.tags)[Category.MUSIC] == ("bgm",)
    assert dict(cfg.tags)[Category.SOUND_EFFECTS]  # untouched default
    assert cfg.extensions[".mxf"] is MediaType.VIDEO
    assert ".mov" not in cfg.extensions  # list replaced
    assert cfg.category_for_folder("shorts") is Category.VERTICAL


def test_default_user_path_is_used(isolated_user_dirs: Path):
    (isolated_user_dirs / "config.toml").write_text('[folders]\nAudio = "Voice"\n', "utf-8")
    assert load_config().folder_for(Category.AUDIO) == "Voice"


@pytest.mark.parametrize(
    "text",
    [
        "[tags]\nNope = ['x']\n",
        "[tags]\nPremiereProjects = ['x']\n",
        "[folders]\nAudio = 'a/b'\n",
        "[folders]\nAudio = 'Music'\n",
        "[extensions]\nvideo = '.mp4'\n",
        "not toml = = =",
    ],
)
def test_invalid_config_raises(tmp_path: Path, text: str):
    user = tmp_path / "bad.toml"
    user.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(user)


def test_missing_explicit_file_raises(tmp_path: Path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.toml")
