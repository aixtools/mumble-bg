"""Allow an empty Mumble write secret to round-trip as NULL."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('state', '0000_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mumbleserver',
            name='ice_secret',
            field=models.CharField(
                blank=True,
                default=None,
                help_text='ICE write secret (leave blank if none)',
                max_length=255,
                null=True,
            ),
        ),
    ]
