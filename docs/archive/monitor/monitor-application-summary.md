# Monitor Application Summary

## Snapshot
- Name: `monitor`
- Version (pyproject): `0.3.0.dev0`
- Type: Django-based monitoring/status utility with plain Python domain models
- Primary purpose: show EVE app + Mumble health and expose roster/wealth status endpoints

## What Monitor Does
- Detects and checks EVE backends (`AUTH` and/or `CUBE`) from configured DB aliases.
- Checks Mumble connectivity through:
  - client login path (pymumble)
  - ICE admin path
  - Murmur database aliases (`mumble_mysql`, `mumble_psql`)
- Serves a lightweight status UI at `/monitor/status/`.
- Exposes JSON endpoints for mains/alts/spies/orphans and pilot wealth detail.

## Runtime Entry Points
- CLI module: `python -m monitor`
- Script wrapper: `scripts/monitor`
- Status server: `monitor.services.status_server`

## CLI Behavior
- Foreground is the default start mode.
- Background can be requested with `--bg`.
- Key controls:
  - `--verify`
  - `--status`
  - `--stop`
  - `--restart`
  - `--version`
  - `--debug` / `--verbose`

## HTTP Surface
- HTML:
  - `/monitor/status/`
- JSON:
  - `/monitor/status/mains/`
  - `/monitor/status/mains-with-alts/`
  - `/monitor/status/main-alts/`
  - `/monitor/status/orphans/`
  - `/monitor/status/pilots/`
  - `/monitor/status/spies/`
  - `/monitor/status/pilot-wealth/`
  - `/monitor/status/ice-users/`

## UI Highlights
- Page title includes version (`monitor <version>`); page heading remains `monitor`.
- Right-side drilldown panel for pilot lists/details.
- Details table includes:
  - `Assets`
  - `Assets-ISK`
  - `Wallet`
  - `SP`
  - `Clones`
  - `Contacts` (agents excluded from counts in AUTH query path)
- Optional alliance logo background when alliance ID is available.

## Core Architecture
- `monitor/views.py`:
  - builds the status page and JSON API responses
  - drives wealth endpoint and asset valuation
- `monitor/checks.py`:
  - verify and collect connection state
- `monitor/services/`:
  - `env.py` resolves app/database aliases
  - `ice_client.py` and `mumble_client.py` handle Mumble checks
  - `status_server.py` runs WSGI server and flushes caches on shutdown
  - `item_pricing.py` implements Janice-preferred pricing with fallback/cache
- `monitor/adapters/repositories.py`:
  - SQL-backed repositories for AUTH and CUBE
  - alliance/corp/pilot/asset/skill/clone data access
- `monitor/models/eve.py`:
  - OO domain model for pilots, orgs, items, skills, clones, and valuations

## Pricing and Cache Model
- Preferred method: Janice (`JANICE_API_KEY`).
  - Default key may not work; see:
    https://github.com/E-351/janice?tab=readme-ov-file#api
- Fallback method: memberaudit/EveUniverse market price tables.
- Cache backend:
  - JSON file backend by default
  - cache TTL default: 3600 seconds
  - in-memory + persisted JSON behavior
- Cache flush on shutdown is wired in status server signal handling.

## Key Configuration Inputs
- Alliance lookup:
  - `ALLIANCE_ID`
  - `ALLIANCE_TICKER`
  - `AUTH_DBPREFIX`
  - `CUBE_DBPREFIX`
- ICE:
  - `ICE_HOST`
  - `ICE_PORT`
  - `ICE_SECRET`
- Mumble client:
  - `PYMUMBLE_SERVER` (defaults to ICE host)
  - `PYMUMBLE_PORT`, `PYMUMBLE_USER`, `PYMUMBLE_PASSWD`
- Item pricing cache:
  - `ITEM_PRICE_CACHE_BACKEND`
  - `ITEM_PRICE_CACHE_FILE`
  - `ITEM_PRICE_CACHE_TTL_SECONDS`
  - `JANICE_MARKET` (default `2` = Jita)
  - `JANICE_PRICING` (`buy|split|sell|purchase`, default `sell`)
  - `JANICE_VARIANT` (`immediate|top5percent`, default `immediate`)
  - `JANICE_DAYS` (`0|1|5|30`, default `0`;
    `0/1` immediate, `5/30` median windows)

## Verification Note
- If DB connections succeed but AUTH/CUBE schema verification fails, `--debug` logs include a hint to check `AUTH_DBPREFIX` and `CUBE_DBPREFIX`.

## Domain Model Scope (Current)
- Organizations: `EveAlliance`, `EveCorporation` (+ refs)
- Pilot: `EvePilot`
- Skills:
  - `EveSkill`
  - `EvePilotSkill`
  - `EveSkillBasket`
  - `EvePilotSkillSummary`
  - `EvePilotSkillbook`
- Clones:
  - `EveImplant`
  - `EveCloneLocation`
  - `EveJumpClone`
  - `EvePilotCloneSummary`
  - `EveCloneBay`
  - `EvePilotClonebook`
- Assets/pricing:
  - `EveItemType`
  - `EveItemStack`
  - `EveAssetItem`
  - `EveItemBasket`
  - `EveItemPrice`
  - `EveItemValuation`

## Current Test Coverage
- Test module present: `tests/test_item_pricing.py`
- Coverage focus:
  - item object construction
  - preferred/fallback pricing flow
  - unresolved type handling
  - cache hit behavior
  - JSON cache flush/reload persistence
