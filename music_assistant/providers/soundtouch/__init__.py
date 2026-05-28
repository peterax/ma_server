"""Bose SoundTouch Player Provider for Music Assistant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from music_assistant_models.config_entries import ConfigEntry
from music_assistant_models.enums import ConfigEntryType, ProviderFeature

from .constants import CONF_MANUAL_DISCOVERY_IP_ADDRESSES
from .provider import SoundTouchPlayerProvider

if TYPE_CHECKING:
    from music_assistant_models.config_entries import ConfigValueType, ProviderConfig
    from music_assistant_models.provider import ProviderManifest

    from music_assistant.mass import MusicAssistant
    from music_assistant.models import ProviderInstanceType


SUPPORTED_FEATURES = {
    ProviderFeature.REMOVE_PLAYER,
}


async def setup(
    mass: MusicAssistant, manifest: ProviderManifest, config: ProviderConfig
) -> ProviderInstanceType:
    """Initialize SoundTouch provider instance with given configuration."""
    return SoundTouchPlayerProvider(mass, manifest, config, SUPPORTED_FEATURES)


async def get_config_entries(
    mass: MusicAssistant,
    instance_id: str | None = None,
    action: str | None = None,
    values: dict[str, ConfigValueType] | None = None,
) -> tuple[ConfigEntry, ...]:
    """Return config entries to set up this provider."""
    # ruff: noqa: ARG001
    return (
        ConfigEntry(
            key=CONF_MANUAL_DISCOVERY_IP_ADDRESSES,
            type=ConfigEntryType.STRING,
            label="Manual SoundTouch devices",
            description=(
                "Optional list of SoundTouch devices to connect to. "
                "Enter one device per line as host or host:port. "
                "Port defaults to 8090."
            ),
            default_value=[],
            required=False,
            multi_value=True,
        ),
    )
