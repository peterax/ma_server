"""
Per-player preset configuration for the Bose SoundTouch provider.

Builds the config entries shown in each speaker's player settings, allowing the
user to map every physical preset button (1-6) to a Music Assistant media item
via a search-and-select flow.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from music_assistant_models.config_entries import ConfigEntry, ConfigValueOption
from music_assistant_models.enums import ConfigEntryType, MediaType
from music_assistant_models.errors import MusicAssistantError
from music_assistant_models.media_items import (
    Album,
    Artist,
    Audiobook,
    Genre,
    ItemMapping,
    Playlist,
    Podcast,
    Radio,
    Track,
)

from .const import PRESET_IDS

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ConfigValueType
    from music_assistant_models.media_items import SearchResults
    from music_assistant_models.queue_item import QueueItem

    from music_assistant.mass import MusicAssistant

SearchResultItem = (
    Artist | Album | Track | Radio | Playlist | Audiobook | Podcast | Genre | ItemMapping
)

SEARCH_RESULT_LIMIT = 25
SEARCH_TIMEOUT = 10

SEARCHABLE_MEDIA_TYPES = (
    MediaType.ARTIST,
    MediaType.ALBUM,
    MediaType.TRACK,
    MediaType.PLAYLIST,
    MediaType.RADIO,
    MediaType.AUDIOBOOK,
    MediaType.PODCAST,
    MediaType.GENRE,
)
DEFAULT_MEDIA_TYPE = MediaType.PLAYLIST
MEDIA_TYPE_OPTIONS = [
    ConfigValueOption(title=media_type.value.replace("_", " ").title(), value=media_type.value)
    for media_type in SEARCHABLE_MEDIA_TYPES
]


def preset_media_key(preset_id: int) -> str:
    """Return the config key holding the media URI for the given preset."""
    return f"preset_{preset_id}_media"


def preset_media_type_key(preset_id: int) -> str:
    """Return the config key holding the media type for the given preset."""
    return f"preset_{preset_id}_media_type"


def preset_media_label_key(preset_id: int) -> str:
    """Return the config key holding the display label for the given preset."""
    return f"preset_{preset_id}_media_label"


async def build_preset_config_entries(
    mass: MusicAssistant,
    player_id: str,
    action: str | None,
    values: dict[str, ConfigValueType] | None,
) -> list[ConfigEntry]:
    """Return the preset config entries for a SoundTouch player."""
    values = values or {}
    entries: list[ConfigEntry] = []
    for preset_id in PRESET_IDS:
        media_type_key = preset_media_type_key(preset_id)
        search_key = f"preset_{preset_id}_search"
        selected_key = f"preset_{preset_id}_selected_media"
        media_key = preset_media_key(preset_id)
        media_label_key = preset_media_label_key(preset_id)
        search_action = f"preset_{preset_id}_search_media"
        copy_action = f"preset_{preset_id}_copy_media"
        save_current_action = f"preset_{preset_id}_save_current"

        media_type = _media_type_config_value(values, media_type_key)
        query = _string_config_value(values, search_key).strip()
        selected_media = _string_config_value(values, selected_key)
        media_value = _string_config_value(values, media_key)
        media_label = _string_config_value(values, media_label_key)

        if action == copy_action and selected_media:
            media_value = selected_media
            media_label = selected_media
        elif action == save_current_action and (
            current_item := _get_current_queue_item(mass, player_id)
        ):
            if current_media := current_item.media_item:
                if current_media.uri:
                    media_value = current_media.uri
                    media_label = _format_media_label(
                        current_media.name,
                        current_media.media_type.value,
                        current_media.provider,
                    )
                    media_type = (
                        current_media.media_type
                        if current_media.media_type in SEARCHABLE_MEDIA_TYPES
                        else media_type
                    )
                    values[media_type_key] = media_type.value
                    values[media_key] = media_value
                    values[media_label_key] = media_label

        media_options = await _build_preset_media_options(
            mass=mass,
            media_type=media_type,
            query=query,
            selected_media=selected_media,
            media_value=media_value,
            media_label=media_label,
            refresh_results=action in (search_action, copy_action),
        )
        if action == copy_action and selected_media:
            media_label = _option_title(media_options, selected_media) or selected_media
            values[media_key] = media_value
            values[media_label_key] = media_label

        entries.append(
            ConfigEntry(
                key=f"preset_{preset_id}_header",
                type=ConfigEntryType.DIVIDER,
                translation_key="preset_header",
                translation_params=[str(preset_id)],
                required=False,
                category="presets",
            )
        )
        entries.extend(
            (
                ConfigEntry(
                    key=f"preset_{preset_id}_save_current_button",
                    type=ConfigEntryType.ACTION,
                    translation_key="preset_save_current_action",
                    translation_params=[str(preset_id)],
                    action=save_current_action,
                    category="presets",
                ),
                ConfigEntry(
                    key=media_type_key,
                    type=ConfigEntryType.STRING,
                    translation_key="preset_media_type",
                    translation_params=[str(preset_id)],
                    required=False,
                    default_value=media_type.value,
                    value=media_type.value,
                    options=MEDIA_TYPE_OPTIONS,
                    category="presets",
                ),
                ConfigEntry(
                    key=search_key,
                    type=ConfigEntryType.STRING,
                    translation_key="preset_search",
                    translation_params=[str(preset_id)],
                    required=False,
                    default_value=query,
                    value=query,
                    category="presets",
                ),
                ConfigEntry(
                    key=f"preset_{preset_id}_do_search",
                    type=ConfigEntryType.ACTION,
                    translation_key="preset_search_action",
                    translation_params=[str(preset_id)],
                    action=search_action,
                    category="presets",
                ),
            )
        )

        if media_options:
            entries.extend(
                (
                    ConfigEntry(
                        key=selected_key,
                        type=ConfigEntryType.STRING,
                        translation_key="preset_result_selection",
                        translation_params=[str(preset_id)],
                        required=False,
                        default_value=selected_media,
                        value=selected_media,
                        options=media_options,
                        category="presets",
                    ),
                    ConfigEntry(
                        key=copy_action,
                        type=ConfigEntryType.ACTION,
                        translation_key="preset_select_action",
                        translation_params=[str(preset_id)],
                        action=copy_action,
                        category="presets",
                    ),
                )
            )
        entries.append(
            ConfigEntry(
                key=media_key,
                type=ConfigEntryType.STRING,
                translation_key="preset_media",
                translation_params=[str(preset_id)],
                required=False,
                default_value=media_value,
                value=media_value,
                options=media_options,
                category="presets",
            )
        )
        entries.append(
            ConfigEntry(
                key=media_label_key,
                type=ConfigEntryType.STRING,
                translation_key="preset_media_label",
                translation_params=[str(preset_id)],
                required=False,
                default_value=media_label,
                value=media_label,
                read_only=True,
                category="presets",
            )
        )

    return entries


async def _build_preset_media_options(
    mass: MusicAssistant,
    media_type: MediaType,
    query: str,
    selected_media: str,
    media_value: str,
    media_label: str,
    refresh_results: bool,
) -> list[ConfigValueOption]:
    """Build the result dropdown for a preset without losing the current selection."""
    media_options = await _build_media_options(mass, media_type, query) if refresh_results else []
    if selected_media and selected_media not in {option.value for option in media_options}:
        media_options.append(ConfigValueOption(title=selected_media, value=selected_media))
    if media_value and media_value not in {option.value for option in media_options}:
        media_options.append(ConfigValueOption(title=media_label or media_value, value=media_value))
    return media_options


async def _build_media_options(
    mass: MusicAssistant,
    media_type: MediaType,
    query: str,
) -> list[ConfigValueOption]:
    """Build dropdown options for a preset media search."""
    options_by_value: dict[str, ConfigValueOption] = {}
    for item in await _search_media_items(mass, media_type, query):
        value = item.uri
        if not value or value in options_by_value:
            continue
        options_by_value[value] = ConfigValueOption(
            title=f"{item.name} ({item.media_type.value}, {item.provider})",
            value=value,
        )
    return sorted(options_by_value.values(), key=lambda option: (option.title or "").lower())


async def _search_media_items(
    mass: MusicAssistant,
    media_type: MediaType,
    query: str,
) -> list[SearchResultItem]:
    """Search MA media items for preset config options."""
    if not query or media_type not in SEARCHABLE_MEDIA_TYPES:
        return []
    try:
        search_result = await asyncio.wait_for(
            mass.music.search(
                search_query=query,
                media_types=[media_type],
                limit=SEARCH_RESULT_LIMIT,
                library_only=False,
            ),
            timeout=SEARCH_TIMEOUT,
        )
    except MusicAssistantError, TimeoutError:
        return []
    return _iter_search_result_items(search_result, media_type)


def _iter_search_result_items(
    search_result: SearchResults,
    media_type: MediaType,
) -> list[SearchResultItem]:
    """Extract media items from a typed MA search result."""
    match media_type:
        case MediaType.ARTIST:
            return list(search_result.artists)
        case MediaType.ALBUM:
            return list(search_result.albums)
        case MediaType.GENRE:
            return list(search_result.genres)
        case MediaType.TRACK:
            return list(search_result.tracks)
        case MediaType.PLAYLIST:
            return list(search_result.playlists)
        case MediaType.RADIO:
            return list(search_result.radio)
        case MediaType.AUDIOBOOK:
            return list(search_result.audiobooks)
        case MediaType.PODCAST:
            return list(search_result.podcasts)
        case _:
            return []


def _string_config_value(values: dict[str, ConfigValueType] | None, key: str) -> str:
    """Return a string config value (empty string if missing/not a string)."""
    if values and isinstance(value := values.get(key), str):
        return value
    return ""


def _media_type_config_value(
    values: dict[str, ConfigValueType] | None,
    key: str,
) -> MediaType:
    """Return a searchable media type from config values."""
    media_type = MediaType(_string_config_value(values, key) or DEFAULT_MEDIA_TYPE.value)
    return media_type if media_type in SEARCHABLE_MEDIA_TYPES else DEFAULT_MEDIA_TYPE


def _get_current_queue_item(mass: MusicAssistant, player_id: str) -> QueueItem | None:
    """Return the currently playing queue item for a player or its active group."""
    queue = mass.player_queues.get_active_queue(player_id) or mass.player_queues.get(player_id)
    return queue.current_item if queue else None


def _format_media_label(name: str, media_type: str, provider: str) -> str:
    """Return a human-readable preset media label."""
    return f"{name} ({media_type}, {provider})"


def _option_title(options: list[ConfigValueOption], value: str) -> str | None:
    """Return the title for an option value."""
    return next((option.title for option in options if option.value == value), None)
