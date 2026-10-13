from __future__ import annotations

from datetime import datetime

from content_organizer.categories import Category
from content_organizer.stats import library_stats


def test_counts_organized_layout(make_tree, config):
    root = make_tree(
        [
            "VerticalVideos/2024/03 - March/a.mp4",
            "VerticalVideos/2024/03 - March/b.mp4",
            "HorizontalVideos/2023/12 - December/c.mp4",
            "HorizontalVideos/2024/January/legacy.mp4",
            "Audio/voice.wav",
            "loose.mp4",
            "loose.mp3",
        ],
        mtime=datetime(2022, 6, 1),
    )
    stats = library_stats(root, config)
    assert stats.total == 7
    assert stats.by_category[Category.VERTICAL] == 2
    assert stats.by_category[Category.HORIZONTAL] == 2
    assert stats.by_category[Category.AUDIO] == 2  # Audio folder + loose mp3
    assert stats.by_category[Category.VIDEOS] == 1  # loose video, no probing
    assert list(stats.by_month) == [(2022, 6), (2023, 12), (2024, 1), (2024, 3)]
    assert stats.by_month[(2024, 3)] == 2
    assert stats.by_month[(2022, 6)] == 3  # mtime fallback
    assert stats.month_folders[(2024, 3)] == [root / "VerticalVideos" / "2024" / "03 - March"]


def test_month_series_sorted_across_years(make_tree, config):
    root = make_tree(
        [
            "Videos/2024/01 - January/a.mp4",
            "Videos/2023/02 - February/b.mp4",
            "Images/2023/11 - November/x.png",
        ]
    )
    series = library_stats(root, config).month_series()
    assert series == [((2023, 2), 1), ((2023, 11), 1), ((2024, 1), 1)]


def test_skips_journal_dir(make_tree, config):
    root = make_tree(["Images/a.png", ".content-organizer/journal-1.jsonl"])
    assert library_stats(root, config).total == 1
