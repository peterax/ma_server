"""Tests for the Bose SoundTouch player preset config entries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from music_assistant_models.enums import ConfigEntryType, MediaType

from music_assistant.providers.bose_soundtouch.config import (
    build_preset_config_entries,
    preset_media_key,
    preset_media_type_key,
)

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ConfigEntry, ConfigValueType

    from music_assistant.mass import MusicAssistant


class _MassStub:
    """Minimal Music Assistant stand-in for preset config tests."""

    def __init__(self) -> None:
        self.player_queues = SimpleNamespace(
            get_active_queue=lambda _player_id: None,
            get=lambda _player_id: None,
        )
        self.music = SimpleNamespace(search=self._search)
        self.searches: list[str] = []

    async def _search(self, search_query: str, **_kwargs: Any) -> Any:
        self.searches.append(search_query)
        return SimpleNamespace(
            artists=[],
            albums=[],
            genres=[],
            tracks=[],
            playlists=[],
            radio=[],
            audiobooks=[],
            podcasts=[],
        )


def _entries_by_key(entries: list[ConfigEntry]) -> dict[str, ConfigEntry]:
    """Index config entries by key."""
    return {entry.key: entry for entry in entries}


async def test_build_preset_entries_without_values() -> None:
    """A plain render exposes all six presets and runs no search."""
    mass = _MassStub()
    entries = _entries_by_key(
        await build_preset_config_entries(cast("MusicAssistant", mass), "player", None, {})
    )

    for preset_id in range(1, 7):
        assert entries[preset_media_key(preset_id)].type == ConfigEntryType.STRING
        assert entries[preset_media_type_key(preset_id)].default_value == MediaType.PLAYLIST.value
    assert mass.searches == []


async def test_build_preset_entries_searches_selected_preset() -> None:
    """Only the requested preset search is refreshed."""
    mass = _MassStub()
    values: dict[str, ConfigValueType] = {
        "preset_2_search": "morning",
        "preset_2_media_type": MediaType.PLAYLIST.value,
    }

    await build_preset_config_entries(
        cast("MusicAssistant", mass),
        "player",
        "preset_2_search_media",
        values,
    )

    assert mass.searches == ["morning"]
