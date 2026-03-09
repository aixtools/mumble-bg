from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('mumble', '0002_add_display_name'),
        ('accounts', '0039_sitesettings_mumble_url'),
    ]

    operations = [
        # 1. Create MumbleServer
        migrations.CreateModel(
            name='MumbleServer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Display name (e.g. "Main Fleet Comms")', max_length=255)),
                ('address', models.CharField(help_text='User-facing connection string (e.g. mumble.example.com:64738)', max_length=255)),
                ('ice_host', models.CharField(help_text='ICE endpoint hostname', max_length=255)),
                ('ice_port', models.PositiveIntegerField(default=6502, help_text='ICE endpoint port')),
                ('ice_secret', models.CharField(blank=True, default='', help_text='ICE write secret (leave blank if none)', max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('display_order', models.PositiveIntegerField(default=0, help_text='Ordering on the profile page (lower = first)')),
            ],
            options={
                'db_table': 'mumble_mumbleserver',
                'ordering': ['display_order', 'name'],
            },
        ),

        # 2. Drop unique on MumbleUser.username
        migrations.AlterField(
            model_name='mumbleuser',
            name='username',
            field=models.CharField(max_length=255),
        ),

        # 3. Change user from OneToOneField to ForeignKey
        migrations.AlterField(
            model_name='mumbleuser',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='mumble_accounts',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 4. Add server FK to MumbleUser (nullable initially)
        migrations.AddField(
            model_name='mumbleuser',
            name='server',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='accounts',
                to='mumble.mumbleserver',
            ),
        ),

        # 5. Add unique_together
        migrations.AlterUniqueTogether(
            name='mumbleuser',
            unique_together={('user', 'server')},
        ),
    ]
