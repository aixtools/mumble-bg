# FCRelay standing-bridge bots

How FCRelay's per-channel relay bots authenticate and enter ACL-gated channels on
the BG-authenticated Murmur servers (Contabo control plane: **US = `server_1`**,
**HK = `server_4`**; Tokyo/`server_2` is decommissioned).

## Why no authd change is needed

The bots are registered as ordinary BG `MumbleUser` rows (`evepilot_id=None`) with a
password and a `groups='Relay'` value. The existing `authenticate()` already:

1. matches the row by username,
2. verifies the password (`verify_murmur_password`),
3. returns `mu.groups` → Murmur applies the `Relay` group to the connection.

So authentication and group membership both come from the same path pilots use. The
only thing that makes the group *useful* is an ACL granting `Relay` entry on the
bridge channels (step 3 below).

A bot that authenticates with only a Murmur **server password** is an unregistered,
group-less user and can enter **open channels only** — never ACL-gated ones. That is
why the relay bots must be BG `MumbleUser` rows, not server-password connections.

## Procedure

One **bot password per server** (US, HK). The *same* value goes in three places:
the BG `MumbleUser` rows, the Cube `MumbleServer` row, and FCRelay's per-server
`password`. The username pattern is `FCRelay-<US|HK>-<channelslug>`.

### 1. Register the bot accounts in BG

```bash
RELAY_BOT_PW='<US/HK bot password>' RELAY_BOT_GROUPS='fleet1,fleet2,...' \
  sudo -u cube --preserve-env=RELAY_BOT_PW,RELAY_BOT_GROUPS bash -lc '
    cd /home/cube/mumble-bg && set -a && source /home/cube/.env/mumble-bg && set +a &&
    export DJANGO_SETTINGS_MODULE=bg.settings &&
    /home/cube/.venv/mumble-bg/bin/python manage.py shell < scripts/register_relay_bots.py'
```

(If US and HK use different bot passwords, run once per server — edit `SERVERS` in
the script to a single entry per run, or extend it to read a per-server password.)
New/updated rows are picked up **live** by the running `mumble-bg-auth`; no restart.

### 2. Store the bot password on the Cube `MumbleServer` rows

So Cube's standing-bridge subsystem and admins can see/manage it. (Cube side.)

### 3. Grant the `Relay` group entry on the bridge channels (per Murmur)

`Relay` is a brand-new ACL group, so it grants nothing until you add an ACL. On each
Murmur, as SuperUser (Mumble client → channel → Edit → ACL), add to the parent of
the bridged tree (e.g. `Fleets`), applies-to-sub-channels:

- group `@Relay` → **grant**: Traverse, Enter, Speak  (Whisper if needed)

Scope it to just the channels you bridge (least privilege). For an "every channel"
bridge, grant `@Relay` at the root with apply-sub — but note that hands a
shared-password bot entry everywhere, so prefer scoping where practical.

### 4. Point FCRelay at the channels

Per bridged channel, one relay `server` entry:

```yaml
relay:
  servers:
    - { name: us-fleet1, address: voice.insidiousevil.org:64738, username: FCRelay-US-fleet1, password: <US bot pw>, channel: "Fleets/Fleet 1", group: fleet1 }
    - { name: hk-fleet1, address: evil-voice-hk.undock.wtf:64738, username: FCRelay-HK-fleet1, password: <HK bot pw>, channel: "Fleets/Fleet 1", group: fleet1 }
```

Same `group:` on both → they bridge each other (and only each other).

## Verification

- `manage.py shell -c "from bg.state.models import MumbleUser; print(MumbleUser.objects.filter(username__startswith='FCRelay-').values_list('server_id','username','groups'))"`
- Connect a bot; confirm it lands in the channel and is heard across the bridge.
- `list_ice_users --server-id 1` / `--server-id 4` to see live registrations.
