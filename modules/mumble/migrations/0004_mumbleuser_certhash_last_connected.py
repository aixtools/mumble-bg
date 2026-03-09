from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mumble', '0003_multi_server'),
    ]

    operations = [
        migrations.AddField(
            model_name='mumbleuser',
            name='certhash',
            field=models.CharField(blank=True, default='', help_text='Client certificate hash (updated on each connection)', max_length=255),
        ),
        migrations.AddField(
            model_name='mumbleuser',
            name='last_connected',
            field=models.DateTimeField(blank=True, help_text='Last successful authentication timestamp', null=True),
        ),
    ]
