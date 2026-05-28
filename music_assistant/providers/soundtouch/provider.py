"""Bose SoundTouch Player Provider implementation."""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING, Any

from bosesoundtouchapi import SoundTouchClient, SoundTouchDevice
from zeroconf import ServiceStateChange

from music_assistant.helpers.util import (
    get_port_from_zeroconf,
    get_primary_ip_address_from_zeroconf,
)
from music_assistant.models.player_provider import PlayerProvider

from .constants import (
    CONF_MANUAL_DISCOVERY_IP_ADDRESSES,
    DEFAULT_SOUNDTOUCH_PORT,
)
from .models import SoundTouchDiscoveryInfo
from .player import SoundTouchPlayer

if TYPE_CHECKING:
    from zeroconf.asyncio import AsyncServiceInfo


class SoundTouchPlayerProvider(PlayerProvider):
    """Player provider for Bose SoundTouch speakers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the SoundTouch provider."""
        super().__init__(*args, **kwargs)
        self._players: dict[str, SoundTouchPlayer] = {}
        self._devices_by_host: dict[str, str] = {}

    async def loaded_in_mass(self) -> None:
        """Call after the provider has been loaded."""
        await self._load_manual_players()

    async def unload(self, is_removed: bool = False) -> None:
        """Handle unload of the provider."""
        for player_id, player in list(self._players.items()):
            await player.close()
            await self.mass.players.unregister(player_id)
        self._players.clear()
        self._devices_by_host.clear()

    async def remove_player(self, player_id: str) -> None:
        """Remove a player from this provider."""
        if player := self._players.pop(player_id, None):
            await player.close()
        await self.mass.players.unregister(player_id)

    async def on_mdns_service_state_change(
        self, name: str, state_change: ServiceStateChange, info: AsyncServiceInfo | None
    ) -> None:
        """Handle mDNS service state callback for Bose SoundTouch."""
        if state_change == ServiceStateChange.Removed:
            return
        if info is None:
            return

        host = get_primary_ip_address_from_zeroconf(info)
        if not host:
            self.logger.debug("Ignoring SoundTouch discovery without an IP address: %s", name)
            return

        port = get_port_from_zeroconf(info) or DEFAULT_SOUNDTOUCH_PORT
        properties = info.decoded_properties
        discovery_info = SoundTouchDiscoveryInfo(
            host=host,
            port=port,
            name=properties.get("name") or name.split(".", 1)[0],
            model=properties.get("model"),
            device_id=properties.get("deviceid") or properties.get("id"),
            mac_address=properties.get("mac") or properties.get("macaddress"),
            software_version=properties.get("version"),
        )
        await self._setup_player(discovery_info)

    async def _load_manual_players(self) -> None:
        """Load manually configured SoundTouch devices."""
        manual_hosts = self.config.get_value(CONF_MANUAL_DISCOVERY_IP_ADDRESSES, [])
        if isinstance(manual_hosts, str):
            manual_hosts = [manual_hosts]

        for raw_host_entry in manual_hosts or []:
            host_entry = str(raw_host_entry).strip()
            if not host_entry:
                continue
            host, port = self._parse_host_entry(host_entry)
            await self._setup_player(SoundTouchDiscoveryInfo(host=host, port=port))

    async def _setup_player(self, discovery_info: SoundTouchDiscoveryInfo) -> None:
        """Create or update a SoundTouch player from discovery data."""
        try:
            discovery_info.host = await asyncio.to_thread(socket.gethostbyname, discovery_info.host)
        except OSError as err:
            self.logger.debug("Could not resolve SoundTouch host %s: %s", discovery_info.host, err)
            return

        if existing_player_id := self._devices_by_host.get(discovery_info.host):
            player = self._players.get(existing_player_id)
            if player is not None:
                await player.update_discovery_info(discovery_info)
                return

        try:
            client = await asyncio.to_thread(self._create_client, discovery_info)
        except Exception as err:
            self.logger.debug(
                "Could not connect to SoundTouch host %s: %s",
                discovery_info.host,
                err,
            )
            return
        identity = client.Device
        discovery_info = self._enrich_discovery_info(discovery_info, identity)
        player_id = self._get_player_id(discovery_info)

        if player := self._players.get(player_id):
            await player.update_discovery_info(discovery_info)
            return

        self.logger.debug(
            "Discovered SoundTouch player %s at %s",
            discovery_info.name,
            discovery_info.host,
        )
        player = SoundTouchPlayer(self, player_id, discovery_info, client)
        self._players[player_id] = player
        self._devices_by_host[discovery_info.host] = player_id
        await player.setup()

    def _create_client(self, discovery_info: SoundTouchDiscoveryInfo) -> SoundTouchClient:
        """Create a SoundTouch API client."""
        device = SoundTouchDevice(
            discovery_info.host,
            port=discovery_info.port,
            dlna_port=discovery_info.dlna_port,
        )
        return SoundTouchClient(device)

    async def _call_api(self, func, *args: Any, **kwargs: Any) -> Any:
        """Run a blocking bosesoundtouchapi call in the executor."""
        return await asyncio.to_thread(func, *args, **kwargs)

    @staticmethod
    def _enrich_discovery_info(
        discovery_info: SoundTouchDiscoveryInfo, identity: Any
    ) -> SoundTouchDiscoveryInfo:
        """Merge API identity fields into discovery data."""
        return SoundTouchDiscoveryInfo(
            host=discovery_info.host,
            port=discovery_info.port,
            dlna_port=discovery_info.dlna_port,
            name=(
                discovery_info.name
                or getattr(identity, "name", None)
                or getattr(identity, "DeviceName", None)
                or getattr(identity, "Name", None)
            ),
            model=(
                discovery_info.model
                or getattr(identity, "model", None)
                or getattr(identity, "DeviceType", None)
                or getattr(identity, "Type", None)
                or getattr(identity, "device_type", None)
            ),
            device_id=(
                discovery_info.device_id
                or getattr(identity, "device_id", None)
                or getattr(identity, "DeviceId", None)
                or getattr(identity, "DeviceID", None)
                or getattr(identity, "deviceID", None)
            ),
            mac_address=(
                discovery_info.mac_address
                or getattr(identity, "mac_address", None)
                or getattr(identity, "MacAddress", None)
                or getattr(identity, "MACAddress", None)
            ),
            software_version=(
                discovery_info.software_version
                or getattr(identity, "software_version", None)
                or getattr(identity, "SoftwareVersion", None)
            ),
        )

    @staticmethod
    def _get_player_id(discovery_info: SoundTouchDiscoveryInfo) -> str:
        """Return stable Music Assistant player id for a SoundTouch device."""
        if discovery_info.device_id:
            return f"soundtouch_{discovery_info.device_id}".lower()
        if discovery_info.mac_address:
            return f"soundtouch_{discovery_info.mac_address}".replace(":", "").lower()
        return f"soundtouch_{discovery_info.host}".replace(".", "_").lower()

    @staticmethod
    def _parse_host_entry(host_entry: str) -> tuple[str, int]:
        """Parse a manual host entry as host or host:port."""
        if ":" not in host_entry:
            return host_entry, DEFAULT_SOUNDTOUCH_PORT
        host, port = host_entry.rsplit(":", 1)
        try:
            return host, int(port)
        except ValueError:
            return host_entry, DEFAULT_SOUNDTOUCH_PORT
