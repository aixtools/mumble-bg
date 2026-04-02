# monitor/__init__.py

Mumble monitor Django app.


## verify_connections
Verify configured Murmur ICE and database connections at startup.

This attempts each configured connection, logs errors, and terminates
the process if any connection checks fail.

# monitor/adapters/__init__.py


## iter_auth_main_characters
Yield main characters from the AUTH schema adapter.


## iter_cube_main_characters
Yield main characters from the CUBE schema adapter.

# monitor/adapters/auth.py


## iter_main_characters
Return main characters from AllianceAuth via UserProfile.main_character.


## resolve_alliance_info
Resolve alliance info by id, name, ticker, or a generic identifier.


## resolve_corporation_info
Resolve corporation info by id, name, ticker, or a generic identifier.

# monitor/adapters/cube.py


## iter_main_characters
Return main characters from CUBE via accounts_evecharacter.is_main.

# monitor/apps.py


## MumbleMonitorConfig
Django app configuration for the mumble monitor.

Optionally triggers a bootstrap run on app startup.

# monitor/checks.py


## validate_settings
Return a list of configuration errors.

This is a lightweight validation pass for settings needed by the app.

# monitor/cli.py


## main
Command-line entry point for the mumble monitor.

Loads settings, configures logging, verifies connections, and runs a
status/listing operation.

# monitor/models/__init__.py

Domain-level classes (not Django ORM models).

# monitor/models/alliance.py


## AllianceRef
Resolve an alliance identifier (id, ticker, or name) to a numeric id.

# monitor/models/eve_types.py


## EveCharacter
Core EVE character fields used by the monitor.


## CorporationRef
Resolve a corporation identifier (id, ticker, or name) to a numeric id.


## AllianceInfo
Mapping-like holder for resolved alliance info.


## CorporationInfo
Mapping-like holder for resolved corporation info.

# monitor/models/murmur.py


## MumbleUser
Data needed to create or manage a Murmur user.


## ChannelSpec
Channel layout specification for bootstrap operations.

# monitor/models/pilots.py


## EvePilots
Helper to fetch pilot information for an alliance or corporation.


## PilotInfo
Loaded pilot details for output and filtering.

# monitor/models/state.py


## MonitorState
Persisted monitor state for comparing runs.

# monitor/services/corp_channels.py


## ensure_corp_channels
Placeholder for creating corp channels under the Corps parent channel.

This currently logs intent only; real ICE channel creation is future work.


## remove_corp_channel
Placeholder for deleting a corp channel when a corp leaves the alliance.

This currently logs intent only; real ICE channel deletion is future work.

# monitor/services/env.py


## detect_environment
Detect whether the database schema matches AUTH or CUBE.

Returns the environment label, or raises if the schema is unknown.

# monitor/services/ice_client.py


## Channel
Simple representation of a Murmur channel.


## IceResult
Wrapper for ICE operations that return a status code and value.


## MurmurIceClient
Minimal ICE client interface for Murmur operations.


## _read_ice_secret
Read the Ice secret from the murmur ini file.


## _require_ice
Import Ice and MumbleServer bindings, adding fallbacks as needed.


## _candidate_ice_module_paths
Return candidate filesystem paths for MumbleServer_ice modules.


## _ensure_ice_pythonpath
Ensure Python can import ICE slice bindings from configured paths.

# monitor/services/local_settings.py


## configure_django_from_local_settings
Configure Django settings from a local settings file.

This supports key/value files or Python settings modules for standalone runs
when a full Django project is not present.


## _build_django_settings
Translate parsed settings values into Django settings dict.


## _parse_settings_file
Parse a simple key=value settings file into a dict.


## _parse_python_settings
Load a Python settings file and return its variables.


## _extract_database_settings
Extract a database config from parsed settings.


## _strip_inline_comment
Remove inline comments while preserving quoted values.


## _coerce_value
Coerce a string value to bool/int where appropriate.

# monitor/services/logging_config.py


## configure_logging
Configure app logging to stdout or an optional file.

# monitor/services/names.py


## format_login_name
Format a Murmur login name using optional alliance/corp tickers.

# monitor/services/state.py


## load_state
Load the monitor state from JSON.

Returns a default state when the file does not exist.


## save_state
Persist monitor state to JSON atomically.

Writes to a temporary file before replacing the target.


## update_known_users
Update the state with the latest known usernames.
