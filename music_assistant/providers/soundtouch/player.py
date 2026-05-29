"""Bose SoundTouch Player implementation."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError, WSMsgType
from music_assistant_models.config_entries import ConfigEntry, ConfigValueOption
from music_assistant_models.enums import ConfigEntryType, IdentifierType, MediaType, PlaybackState
from music_assistant_models.errors import PlayerCommandFailed

from music_assistant.constants import CONF_PLAYERS
from music_assistant.models.player import DeviceInfo, Player, PlayerMedia, PlayerSource

from .constants import (
    CONF_LOCAL_PRESETS,
    DEFAULT_SOUNDTOUCH_WEBSOCKET_PORT,
    IDLE_POLL_INTERVAL,
    LOCAL_PRESET_CONFIG_PREFIX,
    LOCAL_PRESET_PLAY_PREFIX,
    LOCAL_PRESET_SAVE_PREFIX,
    PASSIVE_SOURCE_NAMES,
    PLAYBACK_POLL_INTERVAL,
    PLAYBACK_STATE_MAP,
    PLAYER_FEATURES,
)
from .models import (
    SoundTouchDiscoveryInfo,
    get_now_selection_preset_slot,
    iter_websocket_events,
    parse_websocket_xml,
)

if TYPE_CHECKING:
    from bosesoundtouchapi import SoundTouchClient
    from music_assistant_models.config_entries import ConfigValueType

    from .provider import SoundTouchPlayerProvider


class SoundTouchPlayer(Player):
    """Music Assistant player for a Bose SoundTouch device."""

    def __init__(
        self,
        provider: SoundTouchPlayerProvider,
        player_id: str,
        discovery_info: SoundTouchDiscoveryInfo,
        client: SoundTouchClient,
    ) -> None:
        """Initialize the SoundTouch player."""
        super().__init__(provider, player_id)
        self.discovery_info = discovery_info
        self.client = client
        self._attr_name = discovery_info.name or f"SoundTouch {discovery_info.host}"
        self._attr_supported_features = PLAYER_FEATURES.copy()
        self._attr_needs_poll = True
        self._attr_poll_interval = IDLE_POLL_INTERVAL
        self._attr_source_list = []
        self._handling_local_preset = False
        self._last_bose_preset_signatures: dict[int, str] = {}
        self._websocket_refresh_pending = False
        self._websocket_stopping = False
        self._websocket_task: asyncio.Task[None] | None = None
        self._attr_device_info = DeviceInfo(
            model=discovery_info.model or "SoundTouch",
            manufacturer="Bose",
            software_version=discovery_info.software_version,
        )
        self._attr_device_info.ip_address = discovery_info.host
        self._attr_device_info.add_identifier(IdentifierType.IP_ADDRESS, discovery_info.host)
        if discovery_info.mac_address:
            self._attr_device_info.add_identifier(
                IdentifierType.MAC_ADDRESS, discovery_info.mac_address
            )

    async def setup(self) -> None:
        """Set up the player."""
        await self.update_attributes()
        await self.mass.players.register_or_update(self)
        self._start_websocket()

    async def on_config_updated(self) -> None:
        """Refresh player state when local preset config changes."""
        await self._sync_local_preset_names()
        await self.update_attributes()

    async def update_discovery_info(self, discovery_info: SoundTouchDiscoveryInfo) -> None:
        """Update connection metadata from a new discovery event."""
        previous_host = self.discovery_info.host
        self.discovery_info = discovery_info
        self._attr_device_info.ip_address = discovery_info.host
        self._attr_available = True
        await self.update_attributes()
        if discovery_info.host != previous_host:
            await self._stop_websocket()
            self._start_websocket()

    async def close(self) -> None:
        """Close background resources for the player."""
        self._websocket_stopping = True
        await self._stop_websocket()

    async def get_config_entries(
        self,
        action: str | None = None,
        values: dict[str, ConfigValueType] | None = None,
    ) -> list[ConfigEntry]:
        """Return provider/player specific config entries."""
        base_entries = await super().get_config_entries(action=action, values=values)
        preset_options = await self._get_local_preset_options()
        local_presets = self._get_local_presets()
        entries = [
            ConfigEntry(
                key=f"{LOCAL_PRESET_CONFIG_PREFIX}{slot}",
                type=ConfigEntryType.STRING,
                label=f"SoundTouch favorite {slot}",
                description=(
                    "Assign Music Assistant media to this SoundTouch preset button. "
                    "Choose a library playlist/radio item or paste any playable MA URI."
                ),
                category="presets",
                required=False,
                default_value=local_presets.get(str(slot), {}).get("uri", ""),
                options=preset_options,
            )
            for slot in range(1, 7)
        ]
        return [*base_entries, *entries]

    async def power(self, powered: bool) -> None:
        """Send a POWER command to the player."""
        await self._call("PowerOn" if powered else "PowerOff")
        self._attr_powered = powered
        self.update_state()

    async def play(self) -> None:
        """Send PLAY command to the player."""
        await self._call("MediaPlay")
        self._attr_playback_state = PlaybackState.PLAYING
        self.update_state()

    async def pause(self) -> None:
        """Send PAUSE command to the player."""
        await self._call("MediaPause")
        self._attr_playback_state = PlaybackState.PAUSED
        self.update_state()

    async def stop(self) -> None:
        """Send STOP command to the player."""
        await self._call("MediaStop")
        self._attr_playback_state = PlaybackState.IDLE
        self._attr_current_media = None
        self.update_state()

    async def next_track(self) -> None:
        """Send NEXT TRACK command to the player."""
        await self._call("MediaNextTrack")
        self.update_state()

    async def previous_track(self) -> None:
        """Send PREVIOUS TRACK command to the player."""
        await self._call("MediaPreviousTrack")
        self.update_state()

    async def volume_set(self, volume_level: int) -> None:
        """Set player volume."""
        await self._call("SetVolumeLevel", volume_level)
        self._attr_volume_level = volume_level
        self.update_state()

    async def volume_mute(self, muted: bool) -> None:
        """Set player mute state."""
        await self._call("MuteOn" if muted else "MuteOff")
        self._attr_volume_muted = muted
        self.update_state()

    async def select_source(self, source: str) -> None:
        """Select a SoundTouch source or preset."""
        if source.startswith("preset:"):
            preset_id = int(source.split(":", 1)[1])
            presets = await self._call("GetPresetList")
            preset = next(
                (
                    item
                    for item in self._as_iterable(presets)
                    if self._get_first_attr(item, "PresetId", "preset_id", "id") == preset_id
                ),
                None,
            )
            if preset is None:
                raise PlayerCommandFailed(f"SoundTouch preset {preset_id} is not available")
            await self._call("SelectPreset", preset)
        elif source.startswith(LOCAL_PRESET_PLAY_PREFIX):
            await self._play_local_preset(int(source.removeprefix(LOCAL_PRESET_PLAY_PREFIX)))
        elif source.startswith(LOCAL_PRESET_SAVE_PREFIX):
            await self._save_current_media_as_local_preset(
                int(source.removeprefix(LOCAL_PRESET_SAVE_PREFIX))
            )
        elif source.startswith("source:"):
            source_id, _, source_account = source.removeprefix("source:").partition("|")
            await self._call("SelectSource", source_id, source_account or None)
        else:
            await self._call("SelectSource", source)
        await self.update_attributes()

    async def poll(self) -> None:
        """Poll the player for state updates."""
        self._ensure_websocket_running()
        await self.update_attributes()

    async def update_attributes(self) -> None:
        """Update dynamic player attributes from the SoundTouch API."""
        try:
            status = await self._call("GetNowPlayingStatus")
            volume = await self._call("GetVolume")
            presets = await self._call_optional("GetPresetList")
            sources = await self._call_optional("GetSourceList")
        except PlayerCommandFailed as err:
            self.logger.debug("SoundTouch status check failed for %s: %s", self.name, err)
            self._attr_available = False
            self._attr_poll_interval = IDLE_POLL_INTERVAL
            self.update_state()
            return

        self._attr_available = True
        self._update_volume(volume)
        self._update_playback(status)
        self._update_media(status)
        self._update_sources(sources, presets)
        await self._handle_hardware_preset_update(status, presets)
        self.update_state()

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Call a blocking bosesoundtouchapi method."""
        func = getattr(self.client, method, None)
        if func is None:
            raise PlayerCommandFailed(f"bosesoundtouchapi has no {method} method")
        try:
            return await self.provider._call_api(func, *args, **kwargs)
        except Exception as err:
            raise PlayerCommandFailed(str(err)) from err

    async def _call_optional(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Call an optional bosesoundtouchapi method."""
        try:
            return await self._call(method, *args, **kwargs)
        except PlayerCommandFailed:
            return None

    def _start_websocket(self) -> None:
        """Start SoundTouch websocket notifications."""
        if (
            self._websocket_stopping
            or (self._websocket_task is not None and not self._websocket_task.done())
        ):
            return
        self._websocket_task = self.mass.create_task(self._websocket_loop())
        self.logger.debug("Started SoundTouch websocket listener for %s", self.name)

    def _ensure_websocket_running(self) -> None:
        """Restart SoundTouch websocket notifications if the task stopped."""
        if self._websocket_task is None or self._websocket_task.done():
            self.logger.debug("Restarting stopped SoundTouch websocket for %s", self.name)
            self._start_websocket()

    async def _stop_websocket(self) -> None:
        """Stop SoundTouch websocket notifications."""
        if self._websocket_task is None:
            return
        self._websocket_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._websocket_task
        self._websocket_task = None

    async def _websocket_loop(self) -> None:
        """Listen for raw SoundTouch websocket XML events."""
        websocket_url = (
            f"ws://{self.discovery_info.host}:{DEFAULT_SOUNDTOUCH_WEBSOCKET_PORT}/"
        )
        while not self._websocket_stopping:
            try:
                async with self.mass.http_session_no_ssl.ws_connect(
                    websocket_url,
                    protocols=("gabbo",),
                    heartbeat=30,
                ) as websocket:
                    async for message in websocket:
                        if message.type == WSMsgType.TEXT:
                            await self._handle_websocket_message(message.data)
                        elif message.type == WSMsgType.ERROR:
                            self.logger.debug(
                                "SoundTouch websocket error for %s: %s",
                                self.name,
                                websocket.exception(),
                            )
                            break
            except asyncio.CancelledError:
                raise
            except (ClientError, TimeoutError, OSError) as err:
                self.logger.debug("SoundTouch websocket failed for %s: %s", self.name, err)
            if not self._websocket_stopping:
                await asyncio.sleep(5)

    async def _handle_websocket_message(self, raw_message: str) -> None:
        """Handle a raw SoundTouch websocket XML message."""
        event = parse_websocket_xml(raw_message)
        if event is None:
            return
        refresh_needed = False
        for child_event in iter_websocket_events(event):
            event_name = child_event.tag.rsplit("}", 1)[-1]
            if event_name == "nowSelectionUpdated":
                if (slot := get_now_selection_preset_slot(child_event)) is not None:
                    await self._handle_websocket_preset_selection(slot)
                refresh_needed = True
            elif event_name in {"presetsUpdated", "nowPlayingUpdated", "volumeUpdated"}:
                refresh_needed = True
        if refresh_needed:
            self._queue_websocket_state_refresh()

    def _queue_websocket_state_refresh(self) -> None:
        """Debounce SoundTouch websocket state refreshes on the event loop."""
        if self._websocket_refresh_pending:
            return
        self._websocket_refresh_pending = True
        self.mass.loop.call_later(
            0.2,
            self.mass.create_task,
            self._handle_websocket_state_update(),
        )

    async def _handle_websocket_state_update(self) -> None:
        """Refresh state after a websocket notification."""
        self._websocket_refresh_pending = False
        await self.update_attributes()

    async def _restart_websocket_after_delay(self) -> None:
        """Restart websocket notifications after a close event."""
        if self._websocket_stopping:
            return
        await self._stop_websocket()
        await asyncio.sleep(5)
        self._start_websocket()

    async def _handle_websocket_preset_selection(self, slot: int) -> None:
        """Handle a physical SoundTouch preset button selection."""
        if self._handling_local_preset:
            return
        if str(slot) not in self._get_local_presets():
            return
        self.logger.debug("SoundTouch hardware preset %s selected on %s", slot, self.name)
        await self._play_local_preset(slot)

    def _update_volume(self, volume: Any) -> None:
        """Map SoundTouch volume model to Music Assistant volume attributes."""
        self._attr_volume_level = self._get_first_attr(
            volume,
            "Actual",
            "actual",
            "ActualVolume",
            "volume",
        )
        self._attr_volume_muted = bool(
            self._get_first_attr(volume, "IsMuted", "muted", "Muted", default=False)
        )

    def _update_playback(self, status: Any) -> None:
        """Map SoundTouch playback model to Music Assistant playback attributes."""
        state = self._get_first_attr(status, "play_status", "PlayStatus", "state", default="")
        source = self._get_first_attr(status, "Source", "source", default="")
        if source in ("STANDBY", "INVALID_SOURCE"):
            self._attr_playback_state = PlaybackState.IDLE
        else:
            self._attr_playback_state = PLAYBACK_STATE_MAP.get(str(state), PlaybackState.UNKNOWN)
        self._attr_poll_interval = (
            PLAYBACK_POLL_INTERVAL
            if self._attr_playback_state == PlaybackState.PLAYING
            else IDLE_POLL_INTERVAL
        )
        self._attr_powered = str(state) != "INVALID_PLAY_STATUS"

    def _update_media(self, status: Any) -> None:
        """Map SoundTouch now-playing model to Music Assistant media attributes."""
        source = self._get_first_attr(status, "Source", "source", default=None)
        self._attr_active_source = (
            None if source in (None, "DLNA", "STANDBY", "INVALID_SOURCE", "UPNP") else str(source)
        )

        content_item = self._get_first_attr(status, "ContentItem", "content_item")
        title = self._get_first_attr(status, "Track", "track") or self._get_first_attr(
            content_item,
            "Name",
            "name",
        )
        artist = self._get_first_attr(status, "Artist", "artist")
        album = self._get_first_attr(status, "Album", "album")
        image_url = self._get_first_attr(status, "ArtUrl", "art", "Art", "image", "Image")
        duration = self._get_first_attr(status, "Duration", "duration")
        position = self._get_first_attr(status, "Position", "position")
        uri = self._get_first_attr(content_item, "Location", "location", default=title)

        if not any((title, artist, album, image_url)):
            if self._attr_playback_state == PlaybackState.IDLE:
                self._attr_current_media = None
            return

        self._attr_current_media = PlayerMedia(
            uri=uri,
            media_type=MediaType.TRACK,
            title=title,
            artist=artist,
            album=album,
            image_url=image_url,
            duration=duration,
            elapsed_time=position,
            elapsed_time_last_updated=time.time() if position is not None else None,
            source_id=self._attr_active_source,
        )

    def _update_sources(self, sources: Any, presets: Any) -> None:
        """Build available source list from SoundTouch API data."""
        player_sources: list[PlayerSource] = []
        source_items = self._as_iterable(sources)
        ready_sources: set[tuple[str, str | None]] = set()
        for source in source_items:
            source_id = str(self._get_first_attr(source, "Source", "source", "id", default=""))
            if not source_id:
                continue
            source_account = self._get_first_attr(source, "SourceAccount", "source_account")
            source_status = self._get_first_attr(source, "Status", "status")
            if source_status != "UNAVAILABLE":
                ready_sources.add((source_id, source_account))
                ready_sources.add((source_id, None))
            source_label = (
                source_id if not source_account else f"source:{source_id}|{source_account}"
            )
            source_title = self._get_first_attr(source, "SourceTitle", "FriendlyName")
            player_sources.append(
                PlayerSource(
                    id=source_label,
                    name=source_title
                    or PASSIVE_SOURCE_NAMES.get(source_id, source_id.replace("_", " ").title()),
                    passive=True,
                    can_play_pause=True,
                    can_next_previous=source_id in {"SPOTIFY", "DEEZER", "PANDORA"},
                    can_seek=False,
                )
            )
        for preset in self._as_iterable(presets):
            preset_id = self._get_first_attr(preset, "PresetId", "preset_id", "id")
            name = self._get_first_attr(preset, "Name", "name", default=f"Preset {preset_id}")
            if preset_id is None:
                continue
            preset_source = self._get_first_attr(preset, "Source", "source")
            preset_source_account = self._get_first_attr(
                preset,
                "SourceAccount",
                "source_account",
            )
            if source_items and (preset_source, preset_source_account or None) not in ready_sources:
                continue
            player_sources.append(
                PlayerSource(
                    id=f"preset:{preset_id}",
                    name=str(name),
                    passive=False,
                    can_play_pause=True,
                    can_next_previous=False,
                    can_seek=False,
                )
            )
        local_presets = self._get_local_presets()
        for slot in range(1, 7):
            if saved_preset := local_presets.get(str(slot)):
                player_sources.append(
                    PlayerSource(
                        id=f"{LOCAL_PRESET_PLAY_PREFIX}{slot}",
                        name=f"MA Preset {slot}: {saved_preset.get('name') or saved_preset['uri']}",
                        passive=False,
                        can_play_pause=True,
                        can_next_previous=True,
                        can_seek=False,
                    )
                )
            player_sources.append(
                PlayerSource(
                    id=f"{LOCAL_PRESET_SAVE_PREFIX}{slot}",
                    name=f"Save current as MA Preset {slot}",
                    passive=False,
                    can_play_pause=False,
                    can_next_previous=False,
                    can_seek=False,
                )
            )
        self._attr_source_list = player_sources

    async def _handle_hardware_preset_update(self, status: Any, presets: Any) -> None:
        """Handle hardware preset button activity as local Music Assistant preset actions."""
        current_signatures = {
            int(
                self._get_first_attr(
                    preset,
                    "PresetId",
                    "preset_id",
                    "id",
                )
            ): self._preset_signature(preset)
            for preset in self._as_iterable(presets)
            if self._get_first_attr(preset, "PresetId", "preset_id", "id") is not None
        }
        if not self._last_bose_preset_signatures:
            self._last_bose_preset_signatures = current_signatures

        for slot, signature in current_signatures.items():
            if signature != self._last_bose_preset_signatures.get(slot):
                try:
                    await self._save_current_media_as_local_preset(
                        slot,
                        trigger_state_update=False,
                    )
                except PlayerCommandFailed as err:
                    self.logger.debug(
                        "Ignoring SoundTouch hardware preset save for slot %s: %s",
                        slot,
                        err,
                    )
        self._last_bose_preset_signatures = current_signatures

        slot = self._get_active_bose_preset_slot(status, presets)
        if slot is None or self._handling_local_preset:
            return
        if str(slot) not in self._get_local_presets():
            return
        await self._play_local_preset(slot)

    async def _play_local_preset(self, slot: int) -> None:
        """Play a Music Assistant local preset slot."""
        local_presets = self._get_local_presets()
        preset = local_presets.get(str(slot))
        if not preset:
            raise PlayerCommandFailed(f"MA preset {slot} is not configured")
        self._handling_local_preset = True
        try:
            await self.mass.player_queues.play_media(self.player_id, preset["uri"])
        finally:
            self._handling_local_preset = False

    async def _save_current_media_as_local_preset(
        self,
        slot: int,
        trigger_state_update: bool = True,
    ) -> None:
        """Save current MA media as a local SoundTouch preset slot."""
        media_uri, media_name, image_url = self._get_current_ma_media_for_local_preset()
        if not media_uri:
            raise PlayerCommandFailed("No Music Assistant media is currently active to save")
        local_presets = self._get_local_presets()
        local_presets[str(slot)] = {
            "uri": media_uri,
            "name": media_name or media_uri,
            "image_url": image_url,
        }
        self.mass.config.set(
            f"{CONF_PLAYERS}/{self.player_id}/values/{CONF_LOCAL_PRESETS}",
            local_presets,
        )
        self.mass.config.set(
            f"{CONF_PLAYERS}/{self.player_id}/values/{LOCAL_PRESET_CONFIG_PREFIX}{slot}",
            media_uri,
        )
        if trigger_state_update:
            await self.update_attributes()

    def _get_current_ma_media_for_local_preset(self) -> tuple[str | None, str | None, str | None]:
        """Return current Music Assistant queue media suitable for a local preset."""
        queue = self.mass.player_queues.get_active_queue(self.player_id)
        queue = queue or self.mass.player_queues.get(self.player_id)
        if queue and (queue_item := queue.current_item):
            image_url = None
            if queue_item.image:
                image_url = self.mass.metadata.get_image_url(
                    queue_item.image,
                    size=512,
                    image_format="jpeg",
                )
            return queue_item.uri, queue_item.name, image_url

        media = self._attr_current_media
        if media is not None and media.uri and not self._attr_active_source:
            return media.uri, media.title, media.image_url
        return None, None, None

    def _get_local_presets(self) -> dict[str, dict[str, str | None]]:
        """Return local Music Assistant preset mapping for this SoundTouch player."""
        raw_presets = self.mass.config.get_raw_player_config_value(
            self.player_id,
            CONF_LOCAL_PRESETS,
            {},
        )
        local_presets = dict(raw_presets) if isinstance(raw_presets, dict) else {}
        for slot in range(1, 7):
            slot_key = str(slot)
            uri = self.mass.config.get(
                f"{CONF_PLAYERS}/{self.player_id}/values/{LOCAL_PRESET_CONFIG_PREFIX}{slot}"
            )
            if uri is None:
                continue
            if uri:
                existing = local_presets.get(slot_key, {})
                local_presets[slot_key] = {
                    "uri": str(uri),
                    "name": existing.get("name") or str(uri),
                    "image_url": existing.get("image_url"),
                }
            else:
                local_presets.pop(slot_key, None)
        return local_presets

    async def _get_local_preset_options(self) -> list[ConfigValueOption]:
        """Return selectable Music Assistant media options for local preset config."""
        options_by_uri: dict[str, str] = {}
        for preset in self._get_local_presets().values():
            if uri := preset.get("uri"):
                options_by_uri[uri] = preset.get("name") or uri

        async for playlist in self.mass.music.playlists.iter_library_items(True):
            options_by_uri[playlist.uri] = playlist.name
        async for radio in self.mass.music.radio.iter_library_items(True):
            options_by_uri[radio.uri] = radio.name

        return [
            ConfigValueOption(title, uri)
            for uri, title in sorted(options_by_uri.items(), key=lambda item: item[1].lower())
        ]

    async def _sync_local_preset_names(self) -> None:
        """Persist friendly names for directly configured local presets."""
        local_presets = self._get_local_presets()
        if not local_presets:
            return

        names_by_uri: dict[str, str] = {}
        async for playlist in self.mass.music.playlists.iter_library_items(True):
            names_by_uri[playlist.uri] = playlist.name
        async for radio in self.mass.music.radio.iter_library_items(True):
            names_by_uri[radio.uri] = radio.name

        updated = False
        for preset in local_presets.values():
            uri = preset.get("uri")
            if not uri:
                continue
            name = names_by_uri.get(uri, uri)
            if preset.get("name") != name:
                preset["name"] = name
                updated = True

        if updated:
            self.mass.config.set(
                f"{CONF_PLAYERS}/{self.player_id}/values/{CONF_LOCAL_PRESETS}",
                local_presets,
            )

    def _get_active_bose_preset_slot(self, status: Any, presets: Any) -> int | None:
        """Return Bose preset slot if current native status matches a Bose preset."""
        current_signature = self._content_signature(
            self._get_first_attr(status, "ContentItem", "content_item")
        )
        preset_items = self._as_iterable(presets)
        for preset in self._as_iterable(presets):
            if current_signature and current_signature == self._preset_signature(preset):
                return self._get_first_attr(preset, "PresetId", "preset_id", "id")
        source = self._get_first_attr(status, "Source", "source")
        source_account = self._get_first_attr(status, "SourceAccount", "source_account")
        if not source:
            return None
        source_matches = [
            preset
            for preset in preset_items
            if self._get_first_attr(preset, "Source", "source") == source
            and self._get_first_attr(preset, "SourceAccount", "source_account") == source_account
        ]
        if len(source_matches) == 1:
            return self._get_first_attr(source_matches[0], "PresetId", "preset_id", "id")
        return None

    def _preset_signature(self, preset: Any) -> str:
        """Return a stable signature for a Bose preset content item."""
        return self._content_signature(self._get_first_attr(preset, "ContentItem", "content_item"))

    def _content_signature(self, content_item: Any) -> str:
        """Return a stable signature for a Bose content item."""
        source = self._get_first_attr(content_item, "Source", "source", default="")
        source_account = self._get_first_attr(
            content_item,
            "SourceAccount",
            "source_account",
            default="",
        )
        location = self._get_first_attr(content_item, "Location", "location", default="")
        item_type = self._get_first_attr(content_item, "TypeValue", "type", default="")
        if not source and not location:
            return ""
        return f"{source}|{source_account}|{item_type}|{location}"

    @staticmethod
    def _as_iterable(value: Any) -> list[Any]:
        """Return value as a list, handling common library response wrappers."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        for attr in (
            "items",
            "Items",
            "Presets",
            "presets",
            "SourceItems",
            "source_items",
            "Sources",
            "sources",
            "Members",
            "members",
        ):
            if hasattr(value, attr):
                wrapped = getattr(value, attr)
                return list(wrapped() if callable(wrapped) else wrapped)
        return []

    @staticmethod
    def _get_first_attr(value: Any, *names: str, default: Any = None) -> Any:
        """Return the first matching object attribute or mapping key."""
        if value is None:
            return default
        for name in names:
            if isinstance(value, dict) and name in value:
                return value[name]
            if hasattr(value, name):
                attr_value = getattr(value, name)
                return attr_value() if callable(attr_value) else attr_value
        return default
