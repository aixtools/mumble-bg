from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MumbleServer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Display name (e.g. "Main Fleet Comms")', max_length=255)),
                ('address', models.CharField(help_text='User-facing connection string (e.g. mumble.example.com:64738)', max_length=255)),
                ('ice_host', models.CharField(help_text='ICE endpoint hostname', max_length=255)),
                ('ice_port', models.PositiveIntegerField(default=6502, help_text='ICE endpoint port')),
                ('ice_secret', models.CharField(blank=True, default='', help_text='ICE write secret (leave blank if none)', max_length=255)),
                ('virtual_server_id', models.PositiveIntegerField(blank=True, help_text='Target Murmur virtual server ID on this ICE endpoint. Leave blank only if the endpoint hosts a single booted server.', null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('display_order', models.PositiveIntegerField(default=0, help_text='Ordering on the profile page (lower = first)')),
            ],
            options={
                'db_table': 'mumble_server',
                'ordering': ['display_order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='MumbleUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mumble_userid', models.PositiveIntegerField(blank=True, help_text='Server-assigned Murmur user ID for this registration.', null=True)),
                ('username', models.CharField(max_length=255)),
                ('display_name', models.CharField(blank=True, default='', max_length=255)),
                ('pwhash', models.CharField(max_length=255)),
                ('hashfn', models.CharField(default='murmur-pbkdf2-sha384', max_length=32)),
                ('pw_salt', models.CharField(blank=True, default='', max_length=64)),
                ('kdf_iterations', models.PositiveIntegerField(blank=True, null=True)),
                ('certhash', models.CharField(blank=True, default='', help_text='Client certificate hash (updated on each connection)', max_length=255)),
                ('groups', models.TextField(blank=True, default='')),
                ('last_authenticated', models.DateTimeField(blank=True, help_text='Last successful mumble-bg authenticator callback timestamp', null=True)),
                ('last_connected', models.DateTimeField(blank=True, help_text='Last confirmed Murmur connection timestamp', null=True)),
                ('last_disconnected', models.DateTimeField(blank=True, help_text='Last confirmed Murmur disconnect timestamp', null=True)),
                ('last_seen', models.DateTimeField(blank=True, help_text='Last time Murmur Pulse observed this account online', null=True)),
                ('last_spoke', models.DateTimeField(blank=True, help_text='Last time Murmur reported voice activity for this account', null=True)),
                ('is_mumble_admin', models.BooleanField(default=False, help_text='Grant Mumble server admin permissions')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mumble_registrations', to='state.mumbleserver')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mumble_registrations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'mumble_user',
                'permissions': [('manage_mumble_admin', 'Can manage Mumble admin grants')],
                'unique_together': {('user', 'server')},
            },
        ),
        migrations.CreateModel(
            name='MumbleSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_id', models.PositiveIntegerField()),
                ('mumble_userid', models.IntegerField(blank=True, help_text='Murmur registered-user ID observed for this live session, if any.', null=True)),
                ('username', models.CharField(max_length=255)),
                ('channel_id', models.IntegerField(blank=True, null=True)),
                ('address', models.CharField(blank=True, default='', max_length=255)),
                ('cert_hash', models.CharField(blank=True, default='', max_length=255)),
                ('tcponly', models.BooleanField(default=False)),
                ('mute', models.BooleanField(default=False)),
                ('deaf', models.BooleanField(default=False)),
                ('suppress', models.BooleanField(default=False)),
                ('priority_speaker', models.BooleanField(default=False)),
                ('self_mute', models.BooleanField(default=False)),
                ('self_deaf', models.BooleanField(default=False)),
                ('recording', models.BooleanField(default=False)),
                ('onlinesecs', models.PositiveIntegerField(default=0)),
                ('idlesecs', models.PositiveIntegerField(default=0)),
                ('connected_at', models.DateTimeField()),
                ('last_seen', models.DateTimeField()),
                ('last_state', models.DateTimeField()),
                ('last_spoke', models.DateTimeField(blank=True, null=True)),
                ('disconnected_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('mumble_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mumble_sessions', to='state.mumbleuser')),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mumble_sessions', to='state.mumbleserver')),
            ],
            options={
                'db_table': 'mumble_session',
                'ordering': ['-connected_at', '-id'],
                'permissions': [
                    ('view_mumble_presence', 'Can view current Mumble presence'),
                    ('view_mumble_presence_history', 'Can view Mumble presence history'),
                ],
                'indexes': [
                    models.Index(fields=['server', 'is_active'], name='mumble_sess_server__0310c1_idx'),
                    models.Index(fields=['mumble_user', 'is_active'], name='mumble_sess_mumble__5be72e_idx'),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name='mumbleuser',
            constraint=models.UniqueConstraint(
                condition=Q(mumble_userid__isnull=False),
                fields=('server', 'mumble_userid'),
                name='mumble_user_unique_server_userid',
            ),
        ),
        migrations.AddConstraint(
            model_name='mumblesession',
            constraint=models.UniqueConstraint(
                condition=Q(is_active=True),
                fields=('server', 'session_id'),
                name='mumble_session_unique_active_session',
            ),
        ),
    ]
