"""Tests for SoundTouch model helpers."""

from __future__ import annotations

import sys
import types
from importlib import util
from pathlib import Path
from typing import Any

from defusedxml import ElementTree


def _load_get_now_selection_preset_slot() -> Any:
    """Load the helper without importing the full Music Assistant package."""
    provider_path = Path(__file__).parents[3] / "music_assistant" / "providers" / "soundtouch"
    package_paths = {
        "music_assistant": provider_path.parents[1],
        "music_assistant.providers": provider_path.parent,
        "music_assistant.providers.soundtouch": provider_path,
    }
    for package_name, package_path in package_paths.items():
        if package_name not in sys.modules:
            package = types.ModuleType(package_name)
            package.__path__ = [str(package_path)]  # type: ignore[attr-defined]
            sys.modules[package_name] = package

    for module_name in ("constants", "models"):
        full_name = f"music_assistant.providers.soundtouch.{module_name}"
        spec = util.spec_from_file_location(full_name, provider_path / f"{module_name}.py")
        assert spec is not None
        assert spec.loader is not None
        module = util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)

    models = sys.modules["music_assistant.providers.soundtouch.models"]
    return (
        models.get_now_selection_preset_slot,
        models.iter_websocket_events,
        models.parse_websocket_xml,
    )


get_now_selection_preset_slot, iter_websocket_events, parse_websocket_xml = (
    _load_get_now_selection_preset_slot()
)


def test_get_now_selection_preset_slot() -> None:
    """Return the slot from a SoundTouch nowSelectionUpdated websocket event."""
    event = ElementTree.fromstring(
        '<nowSelectionUpdated><preset id="2"><ContentItem source="TUNEIN" /></preset>'
        "</nowSelectionUpdated>"
    )

    assert get_now_selection_preset_slot(event) == 2


def test_get_now_selection_preset_slot_missing_preset() -> None:
    """Return None when no preset node is present."""
    event = ElementTree.fromstring("<nowSelectionUpdated />")

    assert get_now_selection_preset_slot(event) is None


def test_get_now_selection_preset_slot_invalid_id() -> None:
    """Return None when the preset id is not numeric."""
    event = ElementTree.fromstring('<nowSelectionUpdated><preset id="bad" /></nowSelectionUpdated>')

    assert get_now_selection_preset_slot(event) is None


def test_parse_websocket_xml_returns_event() -> None:
    """Parse raw SoundTouch websocket XML safely."""
    event = parse_websocket_xml(
        '<nowSelectionUpdated><preset id="5"><ContentItem source="TUNEIN" /></preset>'
        "</nowSelectionUpdated>"
    )

    assert event is not None
    assert get_now_selection_preset_slot(event) == 5


def test_parse_websocket_xml_rejects_invalid_xml() -> None:
    """Return None for malformed websocket payloads."""
    assert parse_websocket_xml("<nowSelectionUpdated>") is None


def test_iter_websocket_events_includes_wrapped_children() -> None:
    """Return child event nodes when a websocket payload wraps multiple events."""
    event = ElementTree.fromstring(
        "<updates>"
        '<volumeUpdated><volume actual="20" /></volumeUpdated>'
        '<nowSelectionUpdated><preset id="4" /></nowSelectionUpdated>'
        "</updates>"
    )

    event_names = [child.tag for child in iter_websocket_events(event)]

    assert event_names == ["updates", "volumeUpdated", "nowSelectionUpdated"]
