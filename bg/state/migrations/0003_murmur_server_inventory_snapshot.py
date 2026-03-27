from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("state", "0002_control_channel_key_entry"),
    ]

    operations = [
        migrations.CreateModel(
            name="MurmurServerInventorySnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("fetch_status", models.CharField(blank=True, default="unknown", max_length=32)),
                ("fetch_error", models.TextField(blank=True, default="")),
                ("protocol", models.CharField(blank=True, default="", max_length=16)),
                ("fetched_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "server",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="inventory_snapshot",
                        to="state.mumbleserver",
                    ),
                ),
            ],
            options={
                "db_table": "murmur_server_inventory_snapshot",
                "ordering": ["server_id"],
            },
        ),
    ]
