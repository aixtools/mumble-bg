from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("state", "0001_mumble_server_tls_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ControlChannelKeyEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "secret_ciphertext_b64",
                    models.TextField(
                        help_text="Base64 RSA ciphertext of the control secret (encrypted with BG public key)."
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "control_channel_key_entry",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
