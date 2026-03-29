# Setting Up a New Mumble Server with mumble-bg

This guide covers deploying the custom evilhash Murmur build and mumble-bg to a fresh Ubuntu 24.04 server (e.g., AWS Lightsail).

## Prerequisites

- Fresh Ubuntu 24.04 server with SSH access
- The custom Murmur `.deb` package (`mumble-server_1.5.857-evilhash_amd64.deb`)
- SSH key for GHA deploy (e.g., `mumble-us` keypair)
- Access to cube-de for copying pre-built wheels

## Step 1: Install PostgreSQL and Dependencies

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-client \
  libavahi-compat-libdnssd1 libzeroc-ice3.7t64 libqt5sql5-sqlite \
  libqt5core5t64 libqt5network5t64 libqt5xml5t64 libqt5sql5-psql \
  libqt5dbus5t64 libprotobuf32t64 libcap2 \
  pkg-config python3-dev default-libmysqlclient-dev build-essential
```

## Step 2: Install Custom Murmur

Upload the `.deb` and install:

```bash
scp mumble-server_1.5.857-evilhash_amd64.deb user@server:/tmp/
ssh user@server "sudo dpkg -i /tmp/mumble-server_1.5.857-evilhash_amd64.deb && sudo apt-get install -f -y"
```

The `.deb` is built from the `pkg-mumble-evil` source tree (a local copy lives at `~/aixtools/pkg-mumble-evil/`). It includes hash obfuscation patches to the standard Mumble 1.5.857 server.

## Step 3: Create Databases

Choose strong passwords — the examples below are placeholders.

```bash
sudo -u postgres createuser -d bg_user
sudo -u postgres psql -c "ALTER USER bg_user WITH PASSWORD '<BG_DB_PASSWORD>';"
sudo -u postgres createdb -O bg_user bg_data

sudo -u postgres createuser mumble
sudo -u postgres psql -c "ALTER USER mumble WITH PASSWORD '<MUMBLE_DB_PASSWORD>';"
sudo -u postgres createdb -O mumble mumble_db
```

## Step 4: Configure Murmur

Edit `/etc/mumble/mumble-server.ini`. Key settings:

```ini
dbDriver=QPSQL
dbUsername=mumble
dbPassword="<MUMBLE_DB_PASSWORD>"
dbHost=127.0.0.1
dbPort=5432
dbPrefix=mumble_
database=mumble_db

ice="tcp -h 127.0.0.1 -p 6502"
icesecretwrite=<ICE_SECRET>

port=64738
serverpassword=
bandwidth=558000
users=100

[Ice]
Ice.Warn.UnknownProperties=1
Ice.MessageSizeMax=65536
```

Start and enable Murmur:

```bash
sudo systemctl enable mumble-server
sudo systemctl start mumble-server
```

Verify ICE and Mumble ports are listening:

```bash
ss -tlnp | grep -E '6502|64738'
```

## Step 5: Create the `cube` User

```bash
sudo useradd -m -s /bin/bash cube
echo 'cube ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/cube
sudo chmod 440 /etc/sudoers.d/cube
sudo mkdir -p /home/cube/.ssh /home/cube/.env /home/cube/.venv /etc/mumble-bg/keys
sudo chown -R cube:cube /home/cube/.ssh /home/cube/.env /home/cube/.venv /etc/mumble-bg/keys
```

Add the GHA deploy SSH public key:

```bash
echo '<SSH_PUBLIC_KEY>' | sudo tee /home/cube/.ssh/authorized_keys
sudo chmod 700 /home/cube/.ssh
sudo chmod 600 /home/cube/.ssh/authorized_keys
sudo chown -R cube:cube /home/cube/.ssh
```

## Step 6: Pre-install Expensive Wheels (Time Saver)

Building `zeroc-ice` from source takes 10+ minutes and can OOM on small instances. Copy pre-built wheels from an existing server (e.g., cube-de):

```bash
# From your local machine:
scp root@cube-de.aixtools.com:/home/cube/.cache/pip/wheels/.../zeroc_ice-3.7.11-cp312-cp312-linux_x86_64.whl /tmp/
scp root@cube-de.aixtools.com:/home/cube/.cache/pip/wheels/.../mysqlclient-2.2.8-cp312-cp312-linux_x86_64.whl /tmp/

# Upload to new server:
scp /tmp/zeroc_ice-*.whl /tmp/mysqlclient-*.whl user@newserver:/tmp/

# Pre-install into the venv:
sudo -u cube python3 -m venv /home/cube/.venv/mumble-bg
sudo -u cube /home/cube/.venv/mumble-bg/bin/pip install /tmp/zeroc_ice-*.whl /tmp/mysqlclient-*.whl
```

This saves the GHA deploy from building them from source.

## Step 7: Create systemd Services

### `/etc/systemd/system/bg-authd.service`

```ini
[Unit]
Description=mumble-bg ICE authenticator
After=network.target postgresql.service mumble-server.service

[Service]
User=cube
Group=cube
WorkingDirectory=/home/cube/mumble-bg
EnvironmentFile=/home/cube/.env/mumble-bg
Environment=BG_ENV_FILE=/home/cube/.env/mumble-bg
Environment=DJANGO_SETTINGS_MODULE=bg.settings
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/cube/.venv/mumble-bg/bin/python -I -m bg.authd
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/bg-control.service`

```ini
[Unit]
Description=mumble-bg HTTP control server
After=network.target postgresql.service

[Service]
User=cube
Group=cube
WorkingDirectory=/home/cube/mumble-bg
EnvironmentFile=/home/cube/.env/mumble-bg
Environment=BG_ENV_FILE=/home/cube/.env/mumble-bg
Environment=DJANGO_SETTINGS_MODULE=bg.settings
Environment=BG_KEY_DIR=/etc/mumble-bg/keys
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/cube/.venv/mumble-bg/bin/python -I -m bg.control_main --noreload
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable bg-authd bg-control
```

## Step 8: Firewall

**Important**: Add the SSH rule BEFORE enabling ufw, or you will lock yourself out.

```bash
sudo ufw allow 22/tcp                                          # SSH — add FIRST
sudo ufw allow 64738                                           # Mumble (TCP + UDP)
sudo ufw allow from <CUBE_DE_IP> to any port 18080 proto tcp   # BG control from FG
sudo ufw deny 18080/tcp                                        # Block BG control from others
sudo ufw --force enable
```

If using AWS Lightsail, also open ports in the Lightsail networking firewall:
- TCP 22 (SSH)
- TCP 64738 (Mumble)
- UDP 64738 (Mumble)
- TCP 18080 (BG control)

## Step 9: Configure GHA Deploy

### Create a workflow file

Copy `deploy-dev.yml` to a new file (e.g., `deploy-dev-us.yml`). Change:
- `name:` to identify the target (e.g., `Deploy mumble-bg (Dev US-East)`)
- Remove the `push` trigger (manual `workflow_dispatch` only)
- Replace all secret references with `_<REGION>_DEV` suffixed names

### Add GitHub Secrets

Add these secrets to the `aixtools/mumble-bg` repo:

| Secret | Value |
|--------|-------|
| `TARGETHOST_<REGION>_DEV` | Server IP |
| `TARGETUSER_<REGION>_DEV` | `{"user":"cube","key":"<SSH_PRIVATE_KEY_WITH_ESCAPED_NEWLINES>"}` |
| `BG_DBMS_<REGION>_DEV` | `{"host":"127.0.0.1","username":"bg_user","database":"bg_data","password":"<BG_DB_PASSWORD>"}` |
| `ICE_<REGION>_DEV` | `[{"name":"<SERVER_NAME>","address":"<PUBLIC_IP>:64738","icehost":"127.0.0.1","virtual_server_id":1,"icewrite":"<ICE_SECRET>","iceport":6502,"iceread":"<ICE_SECRET>"}]` |
| `MURMUR_PROBE_<REGION>_DEV` | `[{"host":"127.0.0.1","username":"mumble","database":"mumble_db","password":"<MUMBLE_DB_PASSWORD>","dbport":5432,"dbengine":"postgres"}]` |
| `BG_PSK_<REGION>_DEV` | Same PSK as other BG instances (FG must auth to all) |
| `BG_PKI_PASSPHRASE_<REGION>_DEV` | PKI passphrase |

For the SSH key secret, escape newlines: `awk '{printf "%s\\n", $0}' ~/.ssh/keyfile`

### Run First Deploy

```bash
gh workflow run "Deploy mumble-bg (Dev <REGION>)" --repo aixtools/mumble-bg
```

The deploy will create the venv (or reuse the one with pre-installed wheels), install dependencies, run migrations, and restart services.

## Step 10: Seed the MumbleServer Row

After the first deploy, BG's database has no server record. Seed it:

```bash
ssh cube@<SERVER_IP> "cd /home/cube/mumble-bg && \
  source /home/cube/.env/mumble-bg && \
  export BG_DBMS DJANGO_SETTINGS_MODULE=bg.settings && \
  /home/cube/.venv/mumble-bg/bin/python manage.py shell -c \"
from bg.state.models import MumbleServer
MumbleServer.objects.get_or_create(
    name='<SERVER_NAME>',
    defaults={
        'address': '<PUBLIC_IP>:64738',
        'ice_host': '127.0.0.1',
        'ice_port': 6502,
        'ice_secret': '<ICE_SECRET>',
        'is_active': True,
    }
)
print('Server seeded')
\""
```

Then restart authd so it picks up the new server:

```bash
ssh user@server "sudo systemctl restart bg-authd"
```

Verify authd registered: `journalctl -u bg-authd -n 5 -o cat` should show "Authenticator registered".

## Step 11: Bind bg-control for Remote Access

By default bg-control listens on `127.0.0.1:18080`. For FG to reach it, add to the env file:

```bash
echo "MURMUR_CONTROL_URL='http://0.0.0.0:18080'" >> /home/cube/.env/mumble-bg
sudo systemctl restart bg-control
```

The firewall rules from Step 8 restrict access to the FG server's IP only.

## Step 12: Register in FG

In the Cube Django admin (`/admin/mumble_fg/bgendpoint/`), add a new BgEndpoint:

- **Name**: e.g., `US-East`
- **URL**: `http://<SERVER_IP>:18080`
- **PSK**: the shared PSK (or leave blank to use global)
- **Is active**: checked

FG will now include this server in group syncs (every 3 minutes), ACL syncs, and the profile panel.

## Verification Checklist

- [ ] `ss -tlnp | grep -E '6502|64738|18080'` — all three ports listening
- [ ] `systemctl is-active mumble-server bg-authd bg-control` — all active
- [ ] `journalctl -u bg-authd -n 5` — "Authenticator registered" message
- [ ] Mumble client connects and authenticates
- [ ] FG profile page shows the new server in the dropdown
- [ ] Password reset from FG UI works for the new server
- [ ] Group sync populates groups on the new server

## Troubleshooting

### "Wrong certificate or password" but authd shows no logs
Authd's ICE authenticator may have disconnected from Murmur. Restart both:
```bash
sudo systemctl restart mumble-server bg-authd
```

### Murmur hangs / stuck in "deactivating"
A previous ICE callback may have deadlocked. Force kill:
```bash
sudo systemctl kill -s KILL mumble-server bg-authd
sudo systemctl start mumble-server
sleep 2
sudo systemctl start bg-authd
```

### `InvalidSecretException` in authd or control logs
The ICE write secret in BG's env (`icewrite` in the ICE JSON) doesn't match Murmur's `icesecretwrite` in `mumble-server.ini`. Verify they match.

### GHA deploy fails building zeroc-ice
The server ran out of memory building the C++ extension. Pre-install the wheel (see Step 6).

### Locked out of SSH after enabling ufw
If `ufw --force enable` was run without an SSH allow rule, access via the cloud provider's console (e.g., Lightsail browser SSH or EC2 serial console) and run `sudo ufw allow 22/tcp`. If the console also uses SSH, stop the instance, snapshot, launch a new instance from the snapshot with a user-data script that adds the rule.
