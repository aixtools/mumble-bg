from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mumble', '0004_mumbleuser_certhash_last_connected'),
    ]

    operations = [
        migrations.AddField(
            model_name='mumbleuser',
            name='is_mumble_admin',
            field=models.BooleanField(default=False, help_text='Grant Mumble server admin permissions'),
        ),
    ]
