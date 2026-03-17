from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('state', '0002_access_rule'),
    ]

    operations = [
        migrations.RenameField(
            model_name='AccessRule',
            old_name='block',
            new_name='deny',
        ),
    ]
