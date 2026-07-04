# SoundTouch Provider Handoff

## Current Branch

- Branch: `bose-soundtouch-group-presets`
- Upstream comparison at handoff time: `origin/dev` is 51 commits ahead, this branch is 4 commits ahead.
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

## Runtime Test Setup

Music Assistant is running in Docker:

```text
container: ma-soundtouch-test
image: ghcr.io/music-assistant/server:latest
network: host
web: http://172.25.24.117:8095
data mount: /root/server/.ma-data -> /data
```

Mounted local code overrides:

```text
/root/server/music_assistant/providers/bose_soundtouch
/root/server/music_assistant/providers/sync_group/player.py
/root/server/.container-overrides/music_assistant/providers/dlna/player.py
/root/server/.container-overrides/music_assistant/controllers/config.py
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

Could not run:

```text
pytest: command not found
pre-commit: command not found
```

Project instructions require `pre-commit run --all-files` after changes, so this should be run in a fully provisioned environment before opening/updating a PR.

## Known Risks / Next Work

- Rebase onto latest `origin/dev`; this branch is behind by 51 commits.
- Add automatic SoundTouch-to-DLNA linking/migration so runtime settings do not need manual linking after config churn.
- Decide whether the local `.container-overrides` changes are still required or should be removed from the test container after upstream catches up.
- Ensure `.ma-data/` is ignored or kept out of any git add operation. This environment could not write `.git/info/exclude` because `.git` was read-only.
- Run the full test suite/pre-commit in the intended development environment.
