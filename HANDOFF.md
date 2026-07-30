# SoundTouch Provider Handoff

## Current Branch

- Branch: `bose-soundtouch-group-presets`
- Branch is rebased onto upstream `dev` at `adbb927cf` and contains the SoundTouch
  feature commits on top.
- Latest pushed commit: `cb1167c9c` (`Fix Bose preset action identifiers`).
- Existing remote for the user's fork: `fork git@github.com:peterax/ma_server.git`

## What Is Implemented

- Bose SoundTouch provider is based on upstream PR `9476ac82a Add Bose SoundTouch player provider (#3891)`.
- This branch adds SoundTouch preset handling for Music Assistant groups:
  - physical preset button presses route to the active/static MA group when appropriate;
  - duplicate preset events inside a group are suppressed;
  - Sync Group settings expose SoundTouch preset mappings when the group contains Bose members;
  - provider/player config keeps SoundTouch-specific preset settings visible even when playback is delegated to linked protocols.
- Local follow-up changes in the final commit add:
  - native `/presets` parsing;
  - XML headers on Bose API POST calls;
  - Latin-1 fallback decode for Bose XML responses;
  - "Save current as preset N" actions in player/group config;
  - read-only preset selected-media labels.
- SoundTouch players expose their initial IP address for protocol matching, so the
  matching DLNA renderer is linked automatically on a fresh installation.
- When AirPlay and DLNA are both linked, set `Preferred Output Protocol` to DLNA
  on the native SoundTouch player if AirPlay is unavailable or unreliable.
- Empty Bose manual-discovery configuration no longer crashes provider startup.
- Stale Universal Player wrappers are removed when their protocol is linked to a native
  Bose player, preventing duplicates such as `BossR - Echoing`.
- Preset save/search/select actions use their action IDs, and saving the current item
  immediately persists the preset media, type, and label.

## Runtime Test Setup

Docker is no longer used for this branch. The local development server was run with
Python 3.14.6 and system FFmpeg 6.1.1:

```text
command: python -m music_assistant --log-level debug
web: http://172.25.24.117:8095
streamserver: port 8097
virtualenv: /root/server/.venv
data: /root/server/.ma-data
```

Important: `.ma-data/`, `.container-overrides/`, and `.ssh-codex/` are local runtime files and should not be committed.

## Devices Used For Testing

- `Uterum`: `172.25.25.120`, native player id `bose_soundtouch_68C90B84522E`
- `BossL`: `172.25.25.119`, native player id `bose_soundtouch_A81B6A5AA402`
- `BossR`: `172.25.25.116`, native player id `bose_soundtouch_A81B6AC6C803`

`Uterum` must play via linked DLNA output:

```text
uuid:BO5EBO5E-F00D-F00D-FEED-68C90B84522E
```

The native SoundTouch provider intentionally does not expose `PLAY_MEDIA`; arbitrary MA audio is routed through linked protocols such as DLNA.

## Verified Behavior

- Physical preset websocket events arrive through the SoundTouch websocket using protocol `gabbo`.
- Preset buttons can trigger MA media playback.
- Presets 1, 2, and 6 were tested by the user.
- Uterum, BossL, and BossR are discovered as native SoundTouch players with their
  protocol players linked; playback uses the selected output protocol while preset
  controls remain on the native SoundTouch player.
- User reported: "Works like a charm!" for websocket button/volume handling.
- After the persistent data migration and Latin-1 decode fix, logs showed:

```text
Registered Bose SoundTouch player: Uterum (172.25.25.120)
Registered Bose SoundTouch player: BossL (172.25.25.119)
Registered Bose SoundTouch player: BossR (172.25.25.116)
```

## Recent Fixes

- Moved MA test data from volatile `/tmp/ma-soundtouch-data` to persistent `/root/server/.ma-data`.
- Fixed a startup crash where `Uterum` returned `/now_playing` XML containing Latin-1 metadata and aiohttp tried to decode it as UTF-8.
- Fixed invalid Python 3 exception syntax in local SoundTouch config changes before committing.
- Fixed initial SoundTouch IP registration so fresh installations can auto-link the
  matching DLNA renderer instead of showing separate native and DLNA players.
- The feature branch is rebased onto the latest upstream `dev` to keep the bundled
  AirPlay server code aligned with the development App image.
- Fixed Bose provider startup when `manual_discovery_ip_addresses` is unset.
- Restored per-player preset mappings by removing the migration that deleted them.
- Added Bose config-action handling and immediate persistence for `Save current as preset N`.
- Corrected preset action entry keys so the UI routes save/search/select actions correctly.

## Validation

Passed:

```bash
python3 -m py_compile \
  music_assistant/providers/bose_soundtouch/client.py \
  music_assistant/providers/bose_soundtouch/config.py \
  music_assistant/providers/bose_soundtouch/player.py \
  music_assistant/providers/sync_group/player.py \
  tests/providers/bose_soundtouch/test_client.py
```

Targeted Bose and migration tests pass (47 tests), and the full repository
formatting/configuration hooks pass after provisioning `uv` and `pre-commit`:

```bash
pre-commit run --all-files
```

The full pytest suite was not run because unrelated environment-dependent tests
require additional system libraries and network sockets. Targeted tests, Ruff,
formatting, and mypy pass. For complete local validation, run:

```bash
scripts/setup.sh
pytest
pre-commit run --all-files
```

The local runtime files remain intentionally untracked:

```text
.container-overrides/
.ma-data/
.ssh-codex/
```

## Known Risks / Next Work

- Re-check upstream before PR updates.
- Run the full test suite in the intended development environment before opening/updating a PR.
- The backend preset action works and persists immediately, but the current frontend
  does not refresh the displayed form value until the page is refreshed.
