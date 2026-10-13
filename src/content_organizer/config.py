"""Configuration: bundled ``defaults.toml`` merged with an optional user TOML file.

The user file lives at :func:`default_config_path` (per-user config dir via
``platformdirs``) unless a path is passed explicitly. Tables merge key by key and lists
replace the default list, so a user file only needs the keys it changes.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, TypeVar

from platformdirs import user_config_path

from content_organizer import APP_NAME
from content_organizer.categories import Category, MediaType

_E = TypeVar("_E", Category, MediaType)


class ConfigError(ValueError):
    """The configuration file is unreadable or invalid."""


@dataclass(frozen=True)
class Config:
    """Validated, immutable configuration."""

    extensions: Mapping[str, MediaType]
    """Lower-case extension (with dot) -> media type."""
    tags: tuple[tuple[Category, tuple[str, ...]], ...]
    """Ordered (category, lower-case tag tokens); earlier categories win."""
    folders: Mapping[Category, str]
    date_categories: frozenset[Category]
    skip_files: tuple[str, ...] = ()
    skip_dirs: tuple[str, ...] = ()
    source_path: Path | None = field(default=None, compare=False)
    """User config file that was merged in, if any."""

    def folder_for(self, category: Category) -> str:
        """Output folder name for ``category``."""
        return self.folders.get(category, category.value)

    def category_for_folder(self, name: str) -> Category | None:
        """Reverse lookup of :meth:`folder_for` (case-insensitive)."""
        lowered = name.lower()
        for category, folder in self.folders.items():
            if folder.lower() == lowered:
                return category
        return None


def default_config_path() -> Path:
    """Where the user config file is looked up when none is given."""
    return user_config_path(APP_NAME, appauthor=False) / "config.toml"


def load_defaults_dict() -> dict[str, Any]:
    """Parse the bundled ``defaults.toml``."""
    text = resources.files("content_organizer").joinpath("defaults.toml").read_text("utf-8")
    return tomllib.loads(text)


def load_config(path: Path | str | None = None) -> Config:
    """Load defaults and merge the user file over them.

    ``path=None`` uses :func:`default_config_path` if that file exists. An explicit
    ``path`` that does not exist raises :class:`ConfigError`.
    """
    data = load_defaults_dict()
    user_path: Path | None = None
    if path is not None:
        user_path = Path(path)
        if not user_path.is_file():
            raise ConfigError(f"Config file not found: {user_path}")
    elif default_config_path().is_file():
        user_path = default_config_path()

    if user_path is not None:
        try:
            user_data = tomllib.loads(user_path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"Cannot read config {user_path}: {exc}") from exc
        data = merge(data, user_data)
    return build_config(data, source_path=user_path)


def merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge tables; non-table values (including lists) replace."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


_SECTIONS: dict[str, frozenset[str] | None] = {
    "extensions": None,  # keys validated as MediaType names below
    "tags": None,  # keys validated as Category names below
    "folders": None,
    "layout": frozenset({"date_categories"}),
    "scan": frozenset({"skip_files", "skip_dirs"}),
}
# Characters Windows forbids in file names (plus path separators).
_BAD_FOLDER_CHARS = frozenset('<>:"/\\|?*')


def _check_keys(data: Mapping[str, Any]) -> None:
    """Reject unknown sections/keys so a typo never silently loses a setting."""
    for key in data:
        if key not in _SECTIONS:
            raise ConfigError(f"unknown section [{key}] (expected one of: {', '.join(_SECTIONS)})")
    for section, allowed in _SECTIONS.items():
        value = data.get(section)
        if allowed is None or not isinstance(value, Mapping):
            continue
        for key in value:
            if key not in allowed:
                expected = ", ".join(sorted(allowed))
                raise ConfigError(f"[{section}]: unknown key {key!r} (expected one of: {expected})")


def _valid_folder_name(folder: Any) -> bool:
    if not isinstance(folder, str):
        return False
    name = folder.strip()
    return bool(
        name
        and not name.startswith(".")  # '.', '..', hidden and the journal dir
        and not name.endswith(".")  # Windows silently drops trailing dots
        and not (_BAD_FOLDER_CHARS & set(name))
        and all(ord(ch) >= 32 for ch in name)
    )


def build_config(data: Mapping[str, Any], source_path: Path | None = None) -> Config:
    """Validate a merged config dict and build a :class:`Config`."""
    _check_keys(data)
    extensions: dict[str, MediaType] = {}
    for media_name, exts in _table(data, "extensions").items():
        media = _enum(MediaType, media_name, "extensions")
        for ext in _str_list(exts, f"extensions.{media_name}"):
            norm = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            extensions[norm] = media

    tags: list[tuple[Category, tuple[str, ...]]] = []
    for cat_name, values in _table(data, "tags").items():
        category = _enum(Category, cat_name, "tags")
        if category.media_type not in (MediaType.VIDEO, MediaType.AUDIO, MediaType.IMAGE):
            raise ConfigError(f"tags.{cat_name}: tags are not supported for this category")
        tokens = tuple(v.strip("_- .").lower() for v in _str_list(values, f"tags.{cat_name}"))
        tags.append((category, tuple(t for t in tokens if t)))

    folders = {c: c.value for c in Category}
    for cat_name, folder in _table(data, "folders").items():
        if not _valid_folder_name(folder):
            raise ConfigError(
                f"folders.{cat_name} must be a plain folder name "
                f'(no path separators, no leading/trailing dot, none of <>:"|?*): {folder!r}'
            )
        folders[_enum(Category, cat_name, "folders")] = folder.strip()
    if len({f.lower() for f in folders.values()}) != len(folders):
        raise ConfigError("folders: two categories share the same folder name")

    layout = _table(data, "layout")
    date_categories = frozenset(
        _enum(Category, name, "layout.date_categories")
        for name in _str_list(layout.get("date_categories", []), "layout.date_categories")
    )

    scan = _table(data, "scan")
    return Config(
        extensions=extensions,
        tags=tuple(tags),
        folders=folders,
        date_categories=date_categories,
        skip_files=tuple(p.lower() for p in _str_list(scan.get("skip_files", []), "scan")),
        skip_dirs=tuple(p.lower() for p in _str_list(scan.get("skip_dirs", []), "scan")),
        source_path=source_path,
    )


def _table(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"[{key}] must be a table")
    return value


def _str_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where} must be a list of strings")
    return value


def _enum(enum: type[_E], name: str, where: str) -> _E:
    try:
        return enum(name)
    except ValueError:
        valid = ", ".join(e.value for e in enum)
        raise ConfigError(f"{where}: unknown name {name!r} (expected one of: {valid})") from None
