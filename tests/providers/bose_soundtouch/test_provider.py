"""Tests for the Bose SoundTouch player provider."""

from unittest.mock import AsyncMock, Mock, patch

from music_assistant.providers.bose_soundtouch.provider import BoseSoundTouchProvider


async def test_loaded_in_mass_handles_empty_manual_discovery_config() -> None:
    """Provider startup does not fail when manual discovery has no configured value."""
    provider = BoseSoundTouchProvider.__new__(BoseSoundTouchProvider)
    provider.config = Mock()
    provider.config.get_value.return_value = None

    with patch.object(
        BoseSoundTouchProvider, "try_add_player", new_callable=AsyncMock
    ) as add_player:
        await provider.loaded_in_mass()

    add_player.assert_not_awaited()
