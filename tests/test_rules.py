from __future__ import annotations

from datetime import datetime
from pathlib import PurePath

import pytest

from content_organizer.categories import Category, MediaType
from content_organizer.probe import VideoInfo
from content_organizer.rules import (
    categorize,
    clean_filename,
    date_folder,
    match_tag,
    media_type_for,
    parse_date_folder,
    tokenize,
)


def test_tokenize_splits_on_all_delimiters():
    assert tokenize("My Clip_vert-9x16.final") == ["my", "clip", "vert", "9x16", "final"]
    assert tokenize("__leading") == ["leading"]


@pytest.mark.parametrize(
    ("name", "media"),
    [
        ("a.MP4", MediaType.VIDEO),
        ("a.jpeg", MediaType.IMAGE),
        ("a.wav", MediaType.AUDIO),
        ("edit.prproj", MediaType.PROJECT),
        ("notes.txt", MediaType.OTHER),
        ("noext", MediaType.OTHER),
    ],
)
def test_media_type_by_extension(config, name, media):
    assert media_type_for(name, config) is media


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("boom_sfx.wav", Category.SOUND_EFFECTS),
        ("BOOM-SFX.WAV", Category.SOUND_EFFECTS),
        ("chill song.mp3", Category.MUSIC),
        ("beach_vert.mp4", Category.VERTICAL),
        ("beach.9x16.mov", Category.VERTICAL),
        ("wide_16x9.mp4", Category.HORIZONTAL),
        ("smoke_greenscreen.mp4", Category.GREENSCREEN),
        ("ad_final.mp4", Category.FINALIZED),
    ],
)
def test_tags_match_whole_tokens(config, name, expected):
    assert categorize(name, config).category is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # substrings must not match (audit B6)
        ("holiday_greenland.mp4", Category.VIDEOS),
        ("ocean_soundtrack.mp3", Category.AUDIO),
        ("my_projection.mp4", Category.VIDEOS),
        ("vertigo.mp4", Category.VIDEOS),
        ("audiobook_ch1.mp3", Category.AUDIO),
        ("songbird.wav", Category.AUDIO),
        ("horizon_view.mp4", Category.VIDEOS),
        # tags never override the extension's media type
        ("intro_music.mp4", Category.VIDEOS),
        ("logo_project.png", Category.IMAGES),
        ("notes_sfx.txt", Category.OTHER),
        ("thumb_vert.jpg", Category.IMAGES),
    ],
)
def test_no_false_positive_tags(config, name, expected):
    assert categorize(name, config).category is expected


def test_untagged_defaults(config):
    assert categorize("voice.m4a", config).category is Category.AUDIO
    assert categorize("cut.aep", config).category is Category.PROJECTS
    assert categorize("pic.png", config).category is Category.IMAGES
    assert categorize("readme", config).category is Category.OTHER


def test_first_listed_tag_category_wins(config):
    # "final" is listed before "vert" in defaults.toml
    assert categorize("ad_vert_final.mp4", config).category is Category.FINALIZED
    assert match_tag("x_sound_music.wav", MediaType.AUDIO, config) == (
        Category.SOUND_EFFECTS,
        "sound",
    )


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        (VideoInfo(1080, 1920), Category.VERTICAL),
        (VideoInfo(1920, 1080), Category.HORIZONTAL),
        (VideoInfo(1920, 1080, rotation=90), Category.VERTICAL),
        (VideoInfo(1920, 1080, rotation=270), Category.VERTICAL),
        (VideoInfo(1080, 1920, rotation=180), Category.VERTICAL),
        (VideoInfo(1080, 1080), Category.HORIZONTAL),  # square -> horizontal
        (VideoInfo(None, None), Category.VIDEOS),
        (None, Category.VIDEOS),
    ],
)
def test_video_orientation(config, info, expected):
    assert categorize("clip.mp4", config, info).category is expected


def test_tag_beats_probe(config):
    decision = categorize("clip_horiz.mp4", config, VideoInfo(1080, 1920))
    assert decision.category is Category.HORIZONTAL
    assert "horiz" in decision.reason


@pytest.mark.parametrize(
    ("name", "cleaned"),
    [
        ("Beach_VERT-take2.mp4", "Beach-take2.mp4"),
        ("boom_sfx.wav", "boom.wav"),
        ("Clip_SFX.wav", "Clip.wav"),
        ("2024-01-05_take-2_vert.mp4", "2024-01-05_take-2.mp4"),
        ("my_projection.mp4", "my_projection.mp4"),
        ("ocean_soundtrack.mp3", "ocean_soundtrack.mp3"),
        ("_sfx.wav", "_sfx.wav"),  # never produce an empty stem
        ("sfx.wav", "sfx.wav"),
        ("green_day_song.mp3", "green_day.mp3"),  # video tag "green" kept on audio
        ("plain name.mp4", "plain name.mp4"),
    ],
)
def test_clean_filename(config, name, cleaned):
    assert clean_filename(name, config) == cleaned


def test_date_folder_is_sortable_and_english():
    assert date_folder(datetime(2024, 3, 9)) == PurePath("2024", "03 - March")
    assert date_folder(datetime(2023, 12, 1)) == PurePath("2023", "12 - December")


@pytest.mark.parametrize(
    ("year", "month", "expected"),
    [
        ("2024", "03 - March", (2024, 3)),
        ("2024", "12", (2024, 12)),
        ("2024", "March", (2024, 3)),
        ("2024", "13 - Nope", None),
        ("24", "03 - March", None),
        ("2024", "Holiday", None),
    ],
)
def test_parse_date_folder(year, month, expected):
    assert parse_date_folder(year, month) == expected
