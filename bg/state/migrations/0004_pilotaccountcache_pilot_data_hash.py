from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('state', '0003_pilotaccountcache_account_username'),
    ]

    operations = [
        migrations.AddField(
            model_name='pilotaccountcache',
            name='pilot_data_hash',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Hash of pilot snapshot payload for this account (md5 placeholder).',
                max_length=64,
            ),
        ),
    ]
