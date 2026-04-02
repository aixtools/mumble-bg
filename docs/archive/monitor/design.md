**Overview**
This repo contains a Django-style app that monitors a read-only AUTH or CUBE database and syncs pilot access into a Murmur server via ICE. No views are included; the app is service-driven.

**Environment Detection**
The app auto-detects AUTH vs CUBE by checking for DB table hints:
1. AUTH: `authentication_userprofile`, `eveonline_evecharacter`
2. CUBE: `accounts_evecharacter`
Detection is automatic; no override is provided.

**Main Character Discovery**
AUTH:
1. `authentication_userprofile.main_character_id` -> `eveonline_evecharacter.character_id`
2. Uses `eveonline_evecharacter.alliance_id` and `alliance_ticker`

CUBE:
1. `accounts_evecharacter.is_main = TRUE`
2. Uses `accounts_evecharacter.alliance_id` and `alliance_name` as a ticker placeholder (no ticker in docs)

**Murmur Sync Rules**
1. If main character `alliance_id` matches `MONITOR_ALLIANCE_ID`, create a Murmur user.
2. Login name uses display format: `[alliance_ticker corp_ticker] character_name` (HTML-safe).
3. Comment/display field uses `character_name (character_id)` (HTML-safe).
3. Generate ASCII password + salt/hash; currently not stored or used, but created.
4. If the character leaves the alliance, delete the Murmur user via ICE.

**Channels**
On startup, if no channels exist, create default layout:
1. Lobby
2. Standing Fleet
3. Fleets
4. SIGS
5. Meetings
6. Corps

**State + Logging**
State is tracked in `data/murmur_state.json` (configurable) to remember known users and detect env changes.
Logging includes AUTH/CUBE reads, ICE CRUD calls, and warnings on non-zero ICE results.

**Model Index**
Parsed docs are indexed in `data/model_index.json` for later iterations.
Use `scripts/build_model_index.py` to rebuild.
