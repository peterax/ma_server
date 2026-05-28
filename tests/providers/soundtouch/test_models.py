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

    return sys.modules["music_assistant.providers.soundtouch.models"].get_now_selection_preset_slot


get_now_selection_preset_slot = _load_get_now_selection_preset_slot()


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
