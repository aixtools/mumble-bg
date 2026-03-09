from django.db import migrations, models
import django.db.models


class Migration(migrations.Migration):

    dependencies = [
        ('mumble', '0005_mumbleuser_is_mumble_admin'),
    ]

    operations = [
        migrations.AddField(
            model_name='mumbleserver',
            name='virtual_server_id',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Target Murmur virtual server ID on this ICE endpoint. Leave blank only if the endpoint hosts a single booted server.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='mumbleuser',
            name='kdf_iterations',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mumbleuser',
            name='mumble_userid',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Server-assigned Murmur user ID for this registration.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='mumbleuser',
            name='pw_salt',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='mumbleuser',
            name='hashfn',
            field=models.CharField(default='murmur-pbkdf2-sha384', max_length=32),
        ),
        migrations.AddConstraint(
            model_name='mumbleuser',
            constraint=models.UniqueConstraint(
                condition=django.db.models.Q(mumble_userid__isnull=False),
                fields=('server', 'mumble_userid'),
                name='mumble_user_unique_server_userid',
            ),
        ),
    ]
