"""Add fg/bg control channel key storage for PSK lifecycle."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('state', '0001_alter_mumbleserver_ice_secret_nullable'),
    ]

    operations = [
        migrations.CreateModel(
            name='ControlChannelKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='fg_bg', max_length=64, unique=True)),
                (
                    'shared_secret',
                    models.CharField(
                        blank=True,
                        default=None,
                        help_text='FG/BG control channel PSK. If NULL, control falls back to env bootstrap secret.',
                        max_length=255,
                        null=True,
                    ),
                ),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'control_channel_key',
                'ordering': ['name'],
            },
        ),
    ]
