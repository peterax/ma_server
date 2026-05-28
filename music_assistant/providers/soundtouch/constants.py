"""Constants for the Bose SoundTouch player provider."""

from __future__ import annotations

from music_assistant_models.enums import PlaybackState, PlayerFeature

CONF_MANUAL_DISCOVERY_IP_ADDRESSES = "manual_discovery_ip_addresses"
CONF_LOCAL_PRESETS = "soundtouch_local_presets"
DEFAULT_SOUNDTOUCH_PORT = 8090
DEFAULT_SOUNDTOUCH_DLNA_PORT = 8091
IDLE_POLL_INTERVAL = 30
PLAYBACK_POLL_INTERVAL = 5
LOCAL_PRESET_PLAY_PREFIX = "ma_preset:"
LOCAL_PRESET_SAVE_PREFIX = "ma_preset_save:"

SOUNDTOUCH_MDNS_TYPE = "_soundtouch._tcp.local."

PLAYER_FEATURES = {
    PlayerFeature.POWER,
    PlayerFeature.VOLUME_SET,
    PlayerFeature.VOLUME_MUTE,
    PlayerFeature.PAUSE,
    PlayerFeature.NEXT_PREVIOUS,
    PlayerFeature.SELECT_SOURCE,
}

PLAYBACK_STATE_MAP = {
    "PLAY_STATE": PlaybackState.PLAYING,
    "BUFFERING_STATE": PlaybackState.PLAYING,
    "PAUSE_STATE": PlaybackState.PAUSED,
    "STOP_STATE": PlaybackState.IDLE,
    "INVALID_PLAY_STATUS": PlaybackState.IDLE,
}

PASSIVE_SOURCE_NAMES = {
    "AIRPLAY": "AirPlay",
    "AUX": "Aux",
    "BLUETOOTH": "Bluetooth",
    "DEEZER": "Deezer",
    "HDMI": "HDMI",
    "I_HEART_RADIO": "iHeartRadio",
    "INTERNET_RADIO": "Internet Radio",
    "NOTIFICATION": "Notification",
    "PANDORA": "Pandora",
    "SPOTIFY": "Spotify",
    "STORED_MUSIC": "Stored Music",
    "TUNEIN": "TuneIn",
    "TV": "TV",
}
