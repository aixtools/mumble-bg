from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("state", "0003_murmur_server_inventory_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="mumbleuser",
            name="is_temporary",
            field=models.BooleanField(default=False, help_text="Provisioned from a temporary guest link"),
        ),
        migrations.AddField(
            model_name="mumbleuser",
            name="temporary_link_token",
            field=models.CharField(blank=True, default="", help_text="FG temp-link token that created this guest registration", max_length=64),
        ),
        migrations.AddField(
            model_name="mumbleuser",
            name="temporary_expires_at",
            field=models.DateTimeField(blank=True, help_text="When a temporary guest registration should stop authenticating", null=True),
        ),
    ]
