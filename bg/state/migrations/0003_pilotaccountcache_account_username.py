from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('state', '0002_pilotaccountcache_display_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='pilotaccountcache',
            name='account_username',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Cube login username from the latest FG snapshot.',
                max_length=255,
            ),
        ),
    ]
