from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mumble', '0009_alter_mumblesession_options'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='mumbleuser',
            options={
                'permissions': [('manage_mumble_admin', 'Can manage Mumble admin grants')],
            },
        ),
    ]
