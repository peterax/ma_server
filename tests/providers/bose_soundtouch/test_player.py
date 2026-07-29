"""Tests for Bose SoundTouch player behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from music_assistant_models.enums import IdentifierType, PlayerType

from music_assistant.models.player import DeviceInfo
from music_assistant.providers.bose_soundtouch.client import SoundTouchClient
from music_assistant.providers.bose_soundtouch.config import preset_media_key
from music_assistant.providers.bose_soundtouch.player import BoseSoundTouchPlayer


def _player(
    player_id: str = "bose_soundtouch_member",
    *,
    active_group: str | None = None,
    groups: list[SimpleNamespace] | None = None,
    media_id: str = "library://radio/1",
    raw_media_id: str | None = None,
) -> BoseSoundTouchPlayer:
    player = BoseSoundTouchPlayer.__new__(BoseSoundTouchPlayer)
    player.mass = SimpleNamespace(  # type: ignore[assignment]
        config=SimpleNamespace(
            get_raw_player_config_value=MagicMock(
                side_effect=lambda _player_id, key: (
                    raw_media_id if key == preset_media_key(1) else None
                )
            )
        ),
        players=SimpleNamespace(all_players=MagicMock(return_value=groups or [])),
        player_queues=SimpleNamespace(play_media=AsyncMock()),
    )
    player.logger = MagicMock()
    player._player_id = player_id
    player._attr_name = "Bose"
    player._config = SimpleNamespace(  # type: ignore[assignment]
        get_value=MagicMock(
            side_effect=lambda key: media_id if key == preset_media_key(1) else None
        )
    )
    player._state = SimpleNamespace(active_group=active_group)  # type: ignore[assignment]
    return player


def _group(
    player_id: str,
    *,
    group_members: list[str] | None = None,
    static_group_members: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        player_id=player_id,
        type=PlayerType.GROUP,
        state=SimpleNamespace(
            group_members=group_members or [],
            static_group_members=static_group_members or [],
        ),
    )


def test_preset_queue_uses_active_group() -> None:
    """Preset playback targets the active MA group when present."""
    player = _player(active_group="syncgroup_office")

    assert player._get_preset_queue_id() == "syncgroup_office"


def test_preset_queue_uses_configured_group_member() -> None:
    """Preset playback targets a configured group containing this speaker."""
    player = _player(
        groups=[
            _group("other_group", group_members=["other_player"]),
            _group("syncgroup_office", static_group_members=["bose_soundtouch_member"]),
        ]
    )

    assert player._get_preset_queue_id() == "syncgroup_office"


def test_update_ip_address_keeps_initial_ip_identifier() -> None:
    """The initial SoundTouch IP is available for protocol matching."""
    player = BoseSoundTouchPlayer.__new__(BoseSoundTouchPlayer)
    player._client = cast("SoundTouchClient", SimpleNamespace(ip_address="192.0.2.10"))
    player._attr_device_info = DeviceInfo(model="Bose", manufacturer="Bose")

    player.update_ip_address("192.0.2.10")

    assert player.device_info.identifiers[IdentifierType.IP_ADDRESS] == "192.0.2.10"


@pytest.mark.asyncio
async def test_handle_preset_suppresses_duplicate_group_events() -> None:
    """Two preset events for the same group/media only enqueue once."""
    player = _player(active_group="syncgroup_office")
    BoseSoundTouchPlayer._recent_preset_commands.clear()

    await player._handle_preset(1)
    await player._handle_preset(1)

    cast("AsyncMock", player.mass.player_queues.play_media).assert_awaited_once_with(
        queue_id="syncgroup_office",
        media="library://radio/1",
    )


@pytest.mark.asyncio
async def test_handle_preset_falls_back_to_raw_player_config() -> None:
    """Preset playback still works when parsed provider entries are not present."""
    player = _player(media_id="", raw_media_id="library://radio/2")

    await player._handle_preset(1)

    cast("AsyncMock", player.mass.player_queues.play_media).assert_awaited_once_with(
        queue_id="bose_soundtouch_member",
        media="library://radio/2",
    )
