from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("state", "0000_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="mumbleserver",
            name="ice_tls_cert",
            field=models.CharField(
                blank=True,
                help_text="Optional ICE SSL/TLS certificate file path exposed to BG.",
                max_length=1024,
                null=True,
                default=None,
            ),
        ),
        migrations.AddField(
            model_name="mumbleserver",
            name="ice_tls_key",
            field=models.CharField(
                blank=True,
                help_text="Optional ICE SSL/TLS key file path exposed to BG.",
                max_length=1024,
                null=True,
                default=None,
            ),
        ),
        migrations.AddField(
            model_name="mumbleserver",
            name="ice_tls_ca",
            field=models.CharField(
                blank=True,
                help_text="Optional CA certificate that BG should trust for this ICE endpoint.",
                max_length=1024,
                null=True,
                default=None,
            ),
        ),
    ]
