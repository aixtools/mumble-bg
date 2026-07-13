from django.db import migrations, models


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
    ]
