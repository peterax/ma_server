"""Tests for Bose SoundTouch player behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from music_assistant_models.enums import PlayerType

from music_assistant.providers.bose_soundtouch.player import BoseSoundTouchPlayer
from music_assistant.providers.bose_soundtouch.provider import BoseSoundTouchProvider


def _player(
    player_id: str = "bose_soundtouch_member",
    *,
    active_group: str | None = None,
    synced_to: str | None = None,
    groups: list[SimpleNamespace] | None = None,
) -> BoseSoundTouchPlayer:
    """Create the minimum SoundTouch player needed for preset tests."""
    player = BoseSoundTouchPlayer.__new__(BoseSoundTouchPlayer)
    synced_players = (
        [
            SimpleNamespace(
                player_id=synced_to,
                type=PlayerType.PLAYER,
                group_members=[player_id],
            )
        ]
        if synced_to
        else []
    )
    player.mass = SimpleNamespace(  # type: ignore[assignment]
        players=SimpleNamespace(
            all_players=MagicMock(return_value=groups or []),
            iter_players=MagicMock(return_value=synced_players),
        ),
        player_queues=SimpleNamespace(play_media=AsyncMock()),
    )
    player.logger = MagicMock()
    player._provider = cast(
        "BoseSoundTouchProvider",
        SimpleNamespace(
            instance_id="bose_soundtouch",
            get_preset_media=MagicMock(return_value="library://radio/1"),
        ),
    )
    player._player_id = player_id
    player._attr_name = "Bose"
    player._state = SimpleNamespace(active_group=active_group)  # type: ignore[assignment]
    return player


def _group(
    player_id: str,
    *,
    group_members: list[str] | None = None,
    static_group_members: list[str] | None = None,
) -> SimpleNamespace:
    """Create the minimum group state needed for preset routing tests."""
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


def test_preset_queue_uses_sync_leader() -> None:
    """Preset playback targets the native sync leader when there is no MA group."""
    player = _player(synced_to="bose_soundtouch_leader")

    assert player._get_preset_queue_id() == "bose_soundtouch_leader"


def test_preset_queue_uses_configured_group_member() -> None:
    """Preset playback targets a configured dormant group containing the speaker."""
    player = _player(
        groups=[
            _group("other_group", group_members=["other_player"]),
            _group("syncgroup_office", static_group_members=["bose_soundtouch_member"]),
        ]
    )

    assert player._get_preset_queue_id() == "syncgroup_office"


@pytest.mark.asyncio
async def test_handle_preset_suppresses_duplicate_group_events() -> None:
    """Two preset events for the same group and media enqueue only once."""
    player = _player(active_group="syncgroup_office")
    BoseSoundTouchPlayer._recent_preset_commands.clear()

    await player._handle_preset(1)
    await player._handle_preset(1)

    cast("AsyncMock", player.mass.player_queues.play_media).assert_awaited_once_with(
        queue_id="syncgroup_office",
        media="library://radio/1",
    )
