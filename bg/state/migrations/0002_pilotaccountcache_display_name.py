from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('state', '0001_pilot_snapshot_cache'),
    ]

    operations = [
        migrations.AddField(
            model_name='pilotaccountcache',
            name='display_name',
            field=models.CharField(blank=True, default='', help_text='Computed display name from the latest FG snapshot.', max_length=255),
        ),
    ]
