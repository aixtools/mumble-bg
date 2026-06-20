"""Register FCRelay standing-bridge bot accounts in BG.

These are ordinary BG ``MumbleUser`` rows (not pilots, ``evepilot_id=None``) with a
password and a dedicated, least-privilege ``Relay`` group. No authd code change is
needed: the existing ``authenticate()`` matches the row by username, verifies the
password, and returns ``mu.groups`` — so the bots authenticate AND carry the
``Relay`` group, which the bridge-channel ACLs grant ``Enter/Speak`` to.

Run on the BG host as the ``cube`` user, fed to ``manage.py shell``:

    # Probes only (unblocks a channel scan):
    RELAY_BOT_PW='<strong-pw>' \
      sudo -u cube --preserve-env=RELAY_BOT_PW bash -lc '
        cd /home/cube/mumble-bg && set -a && source /home/cube/.env/mumble-bg && set +a &&
        export DJANGO_SETTINGS_MODULE=bg.settings &&
        /home/cube/.venv/mumble-bg/bin/python manage.py shell < scripts/register_relay_bots.py'

    # Probes + per-channel bots (once the bridged channel slugs are known):
    RELAY_BOT_PW='<same-pw>' RELAY_BOT_GROUPS='fleet1,fleet2,fleet3' \
      sudo -u cube --preserve-env=RELAY_BOT_PW,RELAY_BOT_GROUPS bash -lc '... same as above ...'

Use the SAME RELAY_BOT_PW you store on the Cube MumbleServer row and put in
FCRelay's per-server ``password``. Idempotent: re-running updates in place.

NOTE: this only handles AUTH + group membership. The bots still need an ACL that
grants the ``Relay`` group ``Enter/Speak`` on the channels they bridge (e.g. one
ACL on the ``Fleets`` parent with apply_sub). See docs/relay_bots.md.
"""
import os

from django.contrib.auth.models import User

from bg.passwords import build_murmur_password_record
from bg.state.models import MumbleUser

# (BG server pk on the Contabo control-plane DB, region tag used in the
# FCRelay-<TAG>-<group> username). US=1, HK=4. Tokyo/server_2 is decommissioned
# and intentionally absent.
SERVERS = [(1, 'US'), (4, 'HK')]

# Least-privilege group handed to relay bots. Grant this group Enter/Speak on the
# bridge channels via ACL; do NOT use 'admin'/is_mumble_admin for unattended bots.
RELAY_GROUP = 'Relay'

pw = os.environ.get('RELAY_BOT_PW', '').strip()
if not pw:
    raise SystemExit('Set RELAY_BOT_PW (the same password you put on the Cube MumbleServer rows and in FCRelay).')
rec = build_murmur_password_record(pw)

groups_env = os.environ.get('RELAY_BOT_GROUPS', '').strip()
channel_groups = [g.strip() for g in groups_env.split(',') if g.strip()]

# Probe usernames are always registered so a channel scan can connect.
usernames = []
for server_id, tag in SERVERS:
    usernames.append((server_id, f'FCRelay-{tag}-probe'))
    for g in channel_groups:
        usernames.append((server_id, f'FCRelay-{tag}-{g}'))


def ensure(server_id, username):
    du, _ = User.objects.get_or_create(username=username, defaults={'is_active': True})
    _, created = MumbleUser.objects.update_or_create(
        user=du, server_id=server_id,
        defaults=dict(
            username=username, display_name=username,
            groups=RELAY_GROUP, is_mumble_admin=False, is_active=True,
            evepilot_id=None,
            pwhash=rec['pwhash'], hashfn=rec['hashfn'],
            pw_salt=rec['pw_salt'], kdf_iterations=rec['kdf_iterations'],
        ),
    )
    print(f"{'created' if created else 'updated'} {username} (server {server_id}, group {RELAY_GROUP})")


for server_id, username in usernames:
    ensure(server_id, username)
print(f'done: {len(usernames)} account(s) ensured '
      f'({len(channel_groups)} channel group(s) per server + probes)')
