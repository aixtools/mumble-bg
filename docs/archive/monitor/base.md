# Base Documentation (Generated)

This file provides a concise overview of the current codebase, excluding `monitor/ice`.

## Overview
The project provides a Django-based monitor for checking AllianceAuth/CUBE and Mumble/Murmur connectivity and exposing status views from AUTH/CUBE databases.

## Entrypoints
- `monitor/__main__.py`: Runs the CLI entrypoint.
- `monitor/cli.py`: Loads settings, configures logging, verifies connections, and serves status/listing operations.
- `scripts/mumble-monitor`: Convenience launcher that calls the module with the repo `.venv` Python.

## Settings
- `config/settings.py`: Settings defaults for dev use, with secrets provided via environment variables or an external file.
- `config/settings.py`: Example settings file for configuration.
- `monitor/services/local_settings.py`: Parses key/value or Python settings and configures Django settings for standalone runs.

## App Configuration
- `monitor/apps.py`: Django `AppConfig`.
- `monitor/checks.py`: Lightweight settings validation.
- `monitor/__init__.py`: Connection verification utility for ICE and databases.

## Models
- `monitor/models/eve_types.py`: Core EVE types (`EveCharacter`, `CorporationRef`, `AllianceInfo`, `CorporationInfo`).
- `monitor/models/alliance.py`: `AllianceRef` resolution helper.
- `monitor/models/pilots.py`: `EvePilots` loader and `PilotInfo` structure for mains/alts.
- `monitor/models/murmur.py`: `MumbleUser` and `ChannelSpec` structures.
- `monitor/models/state.py`: `MonitorState` persistence container.

## Adapters
- `monitor/adapters/auth.py`: AUTH queries for mains and alliance/corp resolution.
- `monitor/adapters/cube.py`: CUBE queries for mains.
- `monitor/adapters/__init__.py`: Convenience imports for adapter functions.

## Services
- `monitor/services/ice_client.py`: ICE client wrapper for Murmur operations.
- `monitor/services/corp_channels.py`: Placeholder for corp channel management.
- `monitor/services/env.py`: Detects AUTH vs CUBE by DB schema hints.
- `monitor/services/logging_config.py`: Logging configuration.

## Data and State Files
- No sync state file is required for normal monitor operation.

## Notes
- Local secrets are not documented here.
- `monitor/ice` is intentionally excluded from this document.
