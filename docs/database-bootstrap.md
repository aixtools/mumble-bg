# Database Bootstrap

This document gives cut/paste commands for creating a dedicated database user and database for `mumble-bg` from the CLI.

Use this when you want a clean `mumble-bg` database such as:

- user: `bg_user`
- database: `bg_data`

The helper script is:

- [deploy/create-db.sh](/home/michael/prj/mumble-bg/deploy/create-db.sh)

It is meant to be runnable:

- manually by an operator as `root`
- later from deploy automation

It accepts:

- optional `--engine`
- `--user`
- `--db`
- `--host`
- `--pw`

If `--pw` is omitted, the script prompts securely.
If `--engine` is omitted, the script defaults to PostgreSQL.
If the database user already exists, the script does not change that user's password.

## Engine Values

Accepted engine aliases:

- PostgreSQL: `postgres`, `postgresql`, `psql`
- MySQL/MariaDB: `mysql`, `maria`, `mariadb`

This engine value is for provisioning only. It is not part of the `mumble-bg` runtime env contract.

## Interactive Example

PostgreSQL:

```bash
read -rsp 'Password for bg_user: ' BG_DB_PW && echo
bash /home/cube/mumble-bg/deploy/create-db.sh \
  --user bg_user \
  --db bg_data \
  --host 127.0.0.1 \
  --pw "${BG_DB_PW}"
```

MySQL/MariaDB:

```bash
read -rsp 'Password for bg_user: ' BG_DB_PW && echo
bash /home/cube/mumble-bg/deploy/create-db.sh \
  --engine mysql \
  --user bg_user \
  --db bg_data \
  --host 127.0.0.1 \
  --pw "${BG_DB_PW}"
```

If you prefer a prompt inside the script, omit `--pw`:

```bash
bash /home/cube/mumble-bg/deploy/create-db.sh \
  --user bg_user \
  --db bg_data \
  --host 127.0.0.1
```

## Deploy-Friendly Example

This is the intended flag shape for later deploy automation:

```bash
bash /home/cube/mumble-bg/deploy/create-db.sh \
  --engine "${BG_ENGINE}" \
  --user "$(python3 -c 'import json, os; print(json.loads(os.environ["DATABASES"])["bg"]["username"])')" \
  --db "$(python3 -c 'import json, os; print(json.loads(os.environ["DATABASES"])["bg"]["database"])')" \
  --host "$(python3 -c 'import json, os; print(json.loads(os.environ["DATABASES"])["bg"]["host"])')" \
  --pw "$(python3 -c 'import json, os; print(json.loads(os.environ["DATABASES"])["bg"]["password"])')"
```

Optional provisioning-only secret:

- `BG_ENGINE`

Recommended values:

- `psql` for PostgreSQL
- `mysql` for MySQL or MariaDB

## What The Script Does

For PostgreSQL:

- runs as `root`
- uses `su - postgres -c ...`
- creates the role if missing
- creates the database if missing
- sets the database owner to the requested user
- creates a same-named schema for that user
- sets the role search path to `user_schema, public`
- only sets the password when the role is first created

For MySQL/MariaDB:

- runs as `root`
- uses the local `mysql` client
- creates the login if missing
- grants privileges on the requested database
- only sets the password when the user is first created

## After Database Creation

Provisioning the database is only the first step. `mumble-bg` still needs its own tables:

```bash
cd /home/cube/mumble-bg
set -a
source /home/cube/.env/mumble-bg
set +a
/home/cube/.venv/mumble-bg/bin/python manage.py migrate
```

That is the step that creates:

- `mumble_server`
- `mumble_user`
- `mumble_session`

## Current Local Finding

At the moment, the local `mumble-bg` env points at:

- database: `mumble_db`
- user: `mumble`
- schema: `mumble`

That database does not currently contain `mumble_server`, while the old tables still exist in `cube_db.public` as:

- `mumble_mumbleserver`
- `mumble_mumbleuser`

So the clean next step is to provision or fix the dedicated bg database and then run `manage.py migrate` there, rather than renaming old core tables in place.
