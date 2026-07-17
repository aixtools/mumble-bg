from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('state', '0006_mumbleserver_endpoints'),
    ]

    operations = [
        migrations.AddField(
            model_name='mumbleuser',
            name='certhash_fake',
            field=models.CharField(
                blank=True,
                default='',
                help_text=(
                    "Derived fake certhash shown to non-superusers under ShitSpeak's "
                    'Randomized privacy mode (sha256 of the real certhash). Retrieve a '
                    'pilot by an observed fake hash via this field; the real hash is in '
                    'certhash.'
                ),
                max_length=255,
            ),
        ),
    ]
