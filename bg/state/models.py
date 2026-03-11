from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User


class MumbleServer(models.Model):
    name = models.CharField(max_length=255, help_text='Display name (e.g. "Main Fleet Comms")')
    address = models.CharField(max_length=255, help_text='User-facing connection string (e.g. mumble.example.com:64738)')
    ice_host = models.CharField(max_length=255, help_text='ICE endpoint hostname')
    ice_port = models.PositiveIntegerField(default=6502, help_text='ICE endpoint port')
    ice_secret = models.CharField(max_length=255, blank=True, default='', help_text='ICE write secret (leave blank if none)')
    virtual_server_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Target Murmur virtual server ID on this ICE endpoint. Leave blank only if the endpoint hosts a single booted server.',
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0, help_text='Ordering on the profile page (lower = first)')

    class Meta:
        db_table = 'mumble_server'
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class MumbleUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mumble_registrations')
    server = models.ForeignKey(MumbleServer, on_delete=models.CASCADE, related_name='mumble_registrations')
    mumble_userid = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Server-assigned Murmur user ID for this registration.',
    )
    username = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255, blank=True, default='')
    pwhash = models.CharField(max_length=255)
    hashfn = models.CharField(max_length=32, default='murmur-pbkdf2-sha384')
    pw_salt = models.CharField(max_length=64, blank=True, default='')
    kdf_iterations = models.PositiveIntegerField(null=True, blank=True)
    certhash = models.CharField(max_length=255, blank=True, default='', help_text='Client certificate hash (updated on each connection)')
    groups = models.TextField(blank=True, default='')
    last_authenticated = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last successful mumble-bg authenticator callback timestamp',
    )
    last_connected = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last confirmed Murmur connection timestamp',
    )
    last_disconnected = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last confirmed Murmur disconnect timestamp',
    )
    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last time Murmur Pulse observed this account online',
    )
    last_spoke = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Last time Murmur reported voice activity for this account',
    )
    is_mumble_admin = models.BooleanField(default=False, help_text='Grant Mumble server admin permissions')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mumble_user'
        permissions = [
            ('manage_mumble_admin', 'Can manage Mumble admin grants'),
        ]
        unique_together = [('user', 'server')]
        constraints = [
            models.UniqueConstraint(
                fields=['server', 'mumble_userid'],
                condition=Q(mumble_userid__isnull=False),
                name='mumble_user_unique_server_userid',
            ),
        ]

    def __str__(self):
        return self.username


class MumbleSession(models.Model):
    server = models.ForeignKey(MumbleServer, on_delete=models.CASCADE, related_name='mumble_sessions')
    mumble_user = models.ForeignKey(
        MumbleUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mumble_sessions',
    )
    session_id = models.PositiveIntegerField()
    mumble_userid = models.IntegerField(
        null=True,
        blank=True,
        help_text='Murmur registered-user ID observed for this live session, if any.',
    )
    username = models.CharField(max_length=255)
    channel_id = models.IntegerField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True, default='')
    cert_hash = models.CharField(max_length=255, blank=True, default='')
    tcponly = models.BooleanField(default=False)
    mute = models.BooleanField(default=False)
    deaf = models.BooleanField(default=False)
    suppress = models.BooleanField(default=False)
    priority_speaker = models.BooleanField(default=False)
    self_mute = models.BooleanField(default=False)
    self_deaf = models.BooleanField(default=False)
    recording = models.BooleanField(default=False)
    onlinesecs = models.PositiveIntegerField(default=0)
    idlesecs = models.PositiveIntegerField(default=0)
    connected_at = models.DateTimeField()
    last_seen = models.DateTimeField()
    last_state = models.DateTimeField()
    last_spoke = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mumble_session'
        ordering = ['-connected_at', '-id']
        permissions = [
            ('view_mumble_presence', 'Can view current Mumble presence'),
            ('view_mumble_presence_history', 'Can view Mumble presence history'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['server', 'session_id'],
                condition=Q(is_active=True),
                name='mumble_session_unique_active_session',
            ),
        ]
        indexes = [
            models.Index(fields=['server', 'is_active'], name='mumble_sess_server__0310c1_idx'),
            models.Index(fields=['mumble_user', 'is_active'], name='mumble_sess_mumble__5be72e_idx'),
        ]

    def __str__(self):
        return f'{self.server.name}:{self.username}#{self.session_id}'
