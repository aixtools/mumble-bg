from django.db import migrations, models

# Django drops the database-level DEFAULT after backfilling an AddField, but
# bg/ice_inventory.py (run at authd startup) creates mumble_server rows with a
# raw SQL INSERT that does not list these columns. Re-instate the defaults so
# raw inserters keep working after this migration.
_DB_DEFAULTS = (
    ("driver", "ice"),
    ("control_url", ""),
    ("control_tls_cert", ""),
    ("control_tls_key", ""),
    ("control_tls_ca", ""),
    ("auth_token", ""),
)


def _keep_db_defaults(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        # sqlite's ADD COLUMN keeps the inline default; nothing to do.
        return
    with schema_editor.connection.cursor() as cursor:
        for column, default in _DB_DEFAULTS:
            cursor.execute(
                f"ALTER TABLE mumble_server ALTER COLUMN {column} SET DEFAULT '{default}'"
            )


def _drop_db_defaults(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        return
    with schema_editor.connection.cursor() as cursor:
        for column, _default in _DB_DEFAULTS:
            cursor.execute(
                f"ALTER TABLE mumble_server ALTER COLUMN {column} DROP DEFAULT"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("state", "0004_mumble_user_temporary_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="mumbleserver",
            name="driver",
            field=models.CharField(
                choices=[
                    ("ice", "Murmur (ZeroC Ice)"),
                    ("shitspeak", "ShitSpeak (HTTP control API)"),
                ],
                default="ice",
                help_text="How BG drives this server: Murmur over ZeroC Ice, or ShitSpeak over its HTTP control API.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="mumbleserver",
            name="control_url",
            field=models.CharField(
                blank=True,
                default="",
                help_text="ShitSpeak driver: base URL of the node-local admin control API (e.g. https://voice1.example.com:64750). mTLS is mandatory.",
                max_length=1024,
            ),
        ),
        migrations.AddField(
            model_name="mumbleserver",
            name="control_tls_cert",
            field=models.CharField(
                blank=True,
                default="",
                help_text="ShitSpeak driver: path to the client certificate BG presents to the admin control API.",
                max_length=1024,
            ),
        ),
        migrations.AddField(
            model_name="mumbleserver",
            name="control_tls_key",
            field=models.CharField(
                blank=True,
                default="",
                help_text="ShitSpeak driver: path to the private key for control_tls_cert.",
                max_length=1024,
            ),
        ),
        migrations.AddField(
            model_name="mumbleserver",
            name="control_tls_ca",
            field=models.CharField(
                blank=True,
                default="",
                help_text="ShitSpeak driver: path to the CA bundle used to verify the admin control API server certificate.",
                max_length=1024,
            ),
        ),
        migrations.AddField(
            model_name="mumbleserver",
            name="auth_token",
            field=models.CharField(
                blank=True,
                default="",
                help_text="ShitSpeak driver: bearer token the voice server must present to POST /shitspeak/authenticate. Empty disables the endpoint for this server.",
                max_length=255,
            ),
        ),
        migrations.RunPython(_keep_db_defaults, _drop_db_defaults),
    ]
