"""Property-based tests for the pure rules (hypothesis)."""

from __future__ import annotations

from pathlib import PurePath

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from content_organizer.categories import Category
from content_organizer.config import load_config
from content_organizer.rules import (
    categorize,
    clean_filename,
    date_folder,
    parse_date_folder,
    split_name,
    tokenize,
)

CONFIG = load_config()
ALL_TAGS = sorted({t for _, tags in CONFIG.tags for t in tags})
EXTENSIONS = [*sorted(CONFIG.extensions), ".txt", ".MP4", ".Wav", ""]
SEPARATORS = ["_", "-", " ", ".", "__", " - ", "._"]

# Name fragments biased towards the interesting cases: tags, separators, unicode.
fragment = st.one_of(
    st.sampled_from(ALL_TAGS),
    st.sampled_from([t.upper() for t in ALL_TAGS]),
    st.sampled_from(SEPARATORS),
    st.text(
        alphabet=st.characters(exclude_categories=("Cs", "Cc"), exclude_characters='/\\:*?"<>|'),
        min_size=1,
        max_size=8,
    ),
)
stems = st.lists(fragment, min_size=1, max_size=8).map("".join)
names = st.builds(lambda stem, ext: stem + ext, stems, st.sampled_from(EXTENSIONS)).filter(
    lambda n: n not in {".", ".."} and n.strip() != ""
)


@settings(max_examples=500, deadline=None)
@given(names)
def test_clean_filename_keeps_extension_and_nonempty_stem(name):
    cleaned = clean_filename(name, CONFIG)
    assert split_name(cleaned)[1] == split_name(name)[1], (name, cleaned)
    stem = split_name(cleaned)[0]
    assert stem.strip(" ._-") or cleaned == name, (name, cleaned)
    assert "/" not in cleaned and "\\" not in cleaned


@settings(max_examples=300, deadline=None)
@given(names)
def test_clean_filename_is_idempotent(name):
    once = clean_filename(name, CONFIG)
    assert clean_filename(once, CONFIG) == once
    # Cleaning never changes the media type and so never changes the category family.
    assert (
        categorize(once, CONFIG).category.media_type is categorize(name, CONFIG).category.media_type
    )


@settings(max_examples=300, deadline=None)
@given(names)
def test_categorize_never_raises_and_respects_media_type(name):
    decision = categorize(name, CONFIG)
    assert isinstance(decision.category, Category)
    ext = split_name(name)[1].lower()
    assert decision.category.media_type is CONFIG.extensions.get(ext, decision.category.media_type)
    assert decision.reason


@settings(max_examples=200, deadline=None)
@given(stems)
def test_tokenize_tokens_have_no_separators(stem):
    for token in tokenize(stem):
        assert token and token == token.lower()
        assert not any(sep in token for sep in "_-. ")


@given(st.datetimes())
def test_date_folder_round_trips(when):
    year, month = date_folder(when).parts
    assert parse_date_folder(year, month) == (when.year, when.month)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("_sfx.wav", "_sfx.wav"),  # only a tag -> unchanged, never ".wav"
        ("sfx.wav", "sfx.wav"),
        ("SFX_.wav", "SFX_.wav"),
        ("-music-.mp3", "-music-.mp3"),
        ("vert_final.mp4", "vert_final.mp4"),
        ("a_sfx.wav", "a.wav"),
        ("sfx_a.wav", "a.wav"),
        ("a.b_sfx.wav", "a.b.wav"),
        ("Clip_SFX.WAV", "Clip.WAV"),
        ("my_projection_vert.mp4", "my_projection.mp4"),
        ("ocean_soundtrack.mp3", "ocean_soundtrack.mp3"),
        ("photo_vert.png", "photo_vert.png"),  # video tag on an image: untouched
        ("café_🎬_vert.mov", "café_🎬.mov"),
        (".hidden_sfx", ".hidden_sfx"),
    ],
)
def test_clean_filename_examples(name, expected):
    assert clean_filename(name, CONFIG) == expected
    assert PurePath(clean_filename(name, CONFIG)).suffix == PurePath(name).suffix
