# Bose SoundTouch Player Provider

This provider adds native local control for Bose SoundTouch speakers in Music Assistant. It talks directly to each speaker on the LAN through the SoundTouch Webservices API exposed by the device, using the `bosesoundtouchapi` Python package as the protocol library.

## Status

The provider is marked `experimental`. The first implementation focuses on the Music Assistant player-provider surface and the SoundTouch features that can be mapped cleanly without cloud services:

- mDNS discovery using `_soundtouch._tcp.local.`
- manual host configuration for devices that are not discoverable
- local transport control: play, pause, stop, next, previous
- local volume and mute control
- power on/off
- polling of now-playing, volume, source, and preset state
- native aiohttp websocket notifications for hardware preset buttons and faster volume/state updates
- passive external sources for native SoundTouch services such as AirPlay, Bluetooth, Spotify, TuneIn, and aux inputs
- SoundTouch preset selection as Music Assistant player sources
- Music Assistant-local presets that can be saved and played without relying on Bose cloud presets
- linked output-protocol playback for Music Assistant queue audio, including DLNA/UPnP and AirPlay/Sendspin where available

## Files

| File | Purpose |
| --- | --- |
| `__init__.py` | Provider setup entry point and provider-level configuration entries. |
| `manifest.json` | Music Assistant provider metadata, mDNS discovery declaration, and Python dependency pin. |
| `constants.py` | Shared constants, mDNS type, poll intervals, feature flags, source labels, and playback-state mapping. |
| `models.py` | Small provider-local dataclasses used by both provider and player modules. |
| `provider.py` | Discovery, manual device setup, client construction, player registration, and lifecycle handling. |
| `player.py` | Music Assistant `Player` implementation and mapping between MA commands/state and SoundTouch API calls. |
| `README.md` | Provider design notes, setup, behavior, and known limitations. |
| `LICENSE` | MIT license text for this provider contribution. |

## Dependency

The provider uses:

```text
bosesoundtouchapi==1.0.87
defusedxml==0.7.1
```

Version `1.0.87` of `bosesoundtouchapi` is the latest PyPI release as of May 28, 2026. The package requires Python `>3.11.0`, which matches current Music Assistant server development expectations.

The library exposes `SoundTouchClient` methods for the Webservices API, including `GetNowPlayingStatus`, `GetVolume`, `GetSourceList`, `GetPresetList`, media transport commands, volume control, source selection, and power control. Websocket notifications are handled directly with Music Assistant's shared aiohttp session, and raw XML events are parsed with `defusedxml`.

## Discovery

The provider declares SoundTouch mDNS discovery in `manifest.json`:

```json
"mdns_discovery": ["_soundtouch._tcp.local."]
```

When Music Assistant receives a matching service, `SoundTouchPlayerProvider.on_mdns_service_state_change` extracts the device IP address and port, queries the device for identity data, creates a `SoundTouchClient`, and registers or updates a `SoundTouchPlayer`.

Manual configuration is also supported with the `manual_discovery_ip_addresses` config entry. Each value may be:

```text
192.168.1.81
192.168.1.81:8090
soundtouch-kitchen.local
```

## Playback Model

SoundTouch devices do not expose a Music Assistant-native queue API, and the SoundTouch Webservices URL playback endpoint is not reliable enough to use as a Music Assistant output protocol. Hardware testing showed that `PlayUrlDlna` can work for simple direct HTTP URLs, but Music Assistant queue playback can leave the speaker's UPnP receiver in the wrong state. The older `PlayUrl` endpoint left the device in `INVALID_SOURCE`.

For that reason, this provider does not advertise native `PLAY_MEDIA`. Music Assistant audio should be sent through a linked output protocol, for example the speaker's DLNA/UPnP protocol player or its AirPlay/Sendspin protocol player. The SoundTouch provider remains responsible for local control, websocket hardware button handling, volume, power, source selection, and local MA preset mapping.

## Source Model

The provider maps native SoundTouch sources into `PlayerSource` entries. Sources reported by the SoundTouch API are passive because many are controlled by external services or local device inputs. Presets are selectable and are exposed as active player sources using IDs like:

```text
preset:1
preset:2
```

The provider also exposes local Music Assistant preset slots:

```text
ma_preset:1
ma_preset_save:1
```

`ma_preset_save:<slot>` stores the currently active Music Assistant media URI in Music Assistant's player configuration. `ma_preset:<slot>` plays that saved URI through the Music Assistant queue. These local presets do not write anything back to the Bose device or Bose cloud service.

When a physical SoundTouch preset button is pressed on a speaker that belongs to a Music Assistant group, the local preset is routed to the active or configured group player instead of starting unsynced playback on the individual speaker. Duplicate preset events from multiple group members are suppressed briefly so the group receives a single queue command.

The provider opens the SoundTouch websocket notification endpoint with the `gabbo` subprotocol. `nowSelectionUpdated` events expose the physical preset slot, including slots that later fail as `INVALID_SOURCE`, so a hardware preset button can trigger the matching local Music Assistant preset. `volumeUpdated`, `nowPlayingUpdated`, and `presetsUpdated` websocket events schedule immediate state refreshes.

If the physical speaker rewrites a Bose preset while Music Assistant media is active, the provider also treats the changed slot as a signal to save the current Music Assistant media to the matching local slot. Current hardware testing did not show a websocket event for long-presses that do not change the speaker's native preset list.

## Grouping

SoundTouch zone grouping is not exposed by this first provider version. Grouping behavior depends on firmware, model generation, and current zone master state, so it should be added only after dedicated multi-device hardware testing.

## Known Limitations

- The provider still keeps polling enabled as a fallback, but websocket notifications are used for physical preset selection and faster state refreshes.
- Music Assistant audio playback is delegated to linked protocols such as DLNA/UPnP or AirPlay/Sendspin. Native SoundTouch Webservices URL playback is intentionally disabled because it is unreliable with MA stream URLs.
- Source selection is intentionally conservative. Some services require account-specific source account data or a full SoundTouch content item.
- Hardware preset long-presses are only detected when they mutate the native Bose preset list. No dedicated long-press websocket event was seen during hardware testing.
- Native SoundTouch zone grouping is not implemented in this first version. Music Assistant group players can be used with linked output protocols, but stability depends on the selected protocol and speaker network quality.
- The provider was tested against SoundTouch 10 hardware on a local network, but broader model coverage is still needed.

## Development Notes

Keep the provider self-contained under `music_assistant/providers/soundtouch` so it can live cleanly on a `soundtouch` branch in a fork of `music-assistant/server` and be rebased from upstream `dev`.

Recommended validation before a pull request:

```bash
python3 -m compileall music_assistant/providers/soundtouch
ruff check music_assistant/providers/soundtouch tests/providers/soundtouch
pytest tests/providers/soundtouch
```

Hardware validation should include:

- one manually configured device
- one mDNS-discovered device
- playback of Music Assistant queue content through linked output protocols
- local preset playback on a Music Assistant group that contains two SoundTouch speakers
- native source detection while AirPlay/Spotify/Bluetooth is active
- preset selection
- volume and mute
- power on/off
- websocket handling for physical preset and volume buttons
