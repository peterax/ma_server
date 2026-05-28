"""Models for the Bose SoundTouch player provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .constants import DEFAULT_SOUNDTOUCH_DLNA_PORT, DEFAULT_SOUNDTOUCH_PORT


@dataclass(slots=True)
class SoundTouchDiscoveryInfo:
    """Discovery information for a Bose SoundTouch device."""

    host: str
    port: int = DEFAULT_SOUNDTOUCH_PORT
    dlna_port: int = DEFAULT_SOUNDTOUCH_DLNA_PORT
    name: str | None = None
    model: str | None = None
    device_id: str | None = None
    mac_address: str | None = None
    software_version: str | None = None


def get_now_selection_preset_slot(event: Any) -> int | None:
    """Return the preset slot from a SoundTouch nowSelectionUpdated event."""
    preset = event.find("preset") if event is not None and hasattr(event, "find") else None
    if preset is None:
        return None
    preset_id = preset.get("id")
    if not preset_id:
        return None
    try:
        return int(preset_id)
    except ValueError:
        return None
