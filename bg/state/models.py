from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User


class MumbleServer(models.Model):
    name = models.CharField(max_length=255, help_text='Display name (e.g. "Main Fleet Comms")')
    address = models.CharField(max_length=255, help_text='User-facing connection string (e.g. mumble.example.com:64738)')
    ice_host = models.CharField(max_length=255, help_text='ICE endpoint hostname')
    ice_port = models.PositiveIntegerField(default=6502, help_text='ICE endpoint port')
    ice_secret = models.CharField(max_length=255, blank=True, null=True, default=None, help_text='ICE write secret (leave blank if none)')
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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='murmur_registrations')
    server = models.ForeignKey(MumbleServer, on_delete=models.CASCADE, related_name='murmur_registrations')
    evepilot_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text='Pilot character ID tracked in the FG/BG contract.',
    )
    corporation_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text='Pilot corporation ID tracked in the FG/BG contract.',
    )
    alliance_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text='Pilot alliance ID tracked in the FG/BG contract.',
    )
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
    server = models.ForeignKey(MumbleServer, on_delete=models.CASCADE, related_name='murmur_sessions')
    mumble_user = models.ForeignKey(
        MumbleUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='murmur_sessions',
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


ENTITY_TYPE_ALLIANCE = 'alliance'
ENTITY_TYPE_CORPORATION = 'corporation'
ENTITY_TYPE_PILOT = 'pilot'

ENTITY_TYPE_CHOICES = [
    (ENTITY_TYPE_ALLIANCE, 'Alliance'),
    (ENTITY_TYPE_CORPORATION, 'Corporation'),
    (ENTITY_TYPE_PILOT, 'Pilot'),
]


class AccessRule(models.Model):
    """
    BG's operational copy of the eligibility decision table, received from FG
    via the control channel.

    Precedence (most specific wins):
      1. Pilot allow/deny overrides everything
      2. Corp deny applies if no pilot-level override
      3. Alliance allow is the baseline (alliance in = permitted)

    Default is permit (deny=False). When deny=True the entity is denied.
    EVE IDs are globally unique so entity_id is unique across the table.
    Block checks are account-wide: main or any alt matching triggers denial
    unless a pilot-level allow overrides it.
    """

    entity_id = models.BigIntegerField(
        unique=True,
        help_text='EVE Online ID (alliance, corporation, or character).',
    )
    entity_type = models.CharField(
        max_length=16,
        choices=ENTITY_TYPE_CHOICES,
        help_text='Deducible from ID range but kept for query convenience.',
    )
    deny = models.BooleanField(
        default=False,
        help_text='False = permit (default). True = deny access.',
    )
    note = models.TextField(
        blank=True,
        default='',
        help_text='Admin notes (e.g. reason for denial, ticket reference).',
    )
    created_by = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Who added this rule.',
    )
    synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When this rule was last received from FG via control channel.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bg_access_rule'
        ordering = ['entity_type', 'entity_id']

    def __str__(self):
        action = 'DENY' if self.deny else 'ALLOW'
        return f'{action} {self.entity_type} {self.entity_id}'


class ControlChannelKey(models.Model):
    name = models.CharField(max_length=64, unique=True, default='fg_bg')
    shared_secret = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        default=None,
        help_text='FG/BG control channel PSK. If NULL, control falls back to env bootstrap secret.',
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'control_channel_key'
        ordering = ['name']

    def __str__(self):
        return self.name


BG_AUDIT_ACTION_ACL_SYNC = 'acl_sync'
BG_AUDIT_ACTION_MURMUR_USER_CREATED = 'murmur_user_created'
BG_AUDIT_ACTION_PASSWORD_CHANGED = 'password_changed'

BG_AUDIT_ACTION_CHOICES = [
    (BG_AUDIT_ACTION_ACL_SYNC, 'ACL Sync'),
    (BG_AUDIT_ACTION_MURMUR_USER_CREATED, 'Murmur User Created'),
    (BG_AUDIT_ACTION_PASSWORD_CHANGED, 'Password Changed'),
]


class BgAudit(models.Model):
    """Append-only BG audit log for control mutations and Murmur operations."""

    action = models.CharField(max_length=64, choices=BG_AUDIT_ACTION_CHOICES)
    request_id = models.CharField(max_length=64, blank=True, default='')
    requested_by = models.CharField(max_length=255, blank=True, default='')
    source = models.CharField(max_length=64, blank=True, default='')
    user_id = models.BigIntegerField(null=True, blank=True)
    server_name = models.CharField(max_length=255, blank=True, default='')
    metadata = models.JSONField(blank=True, default=dict)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bg_audit'
        ordering = ['-occurred_at', '-id']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError('BgAudit entries are append-only.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError('BgAudit entries are append-only.')


def append_bg_audit(
    *,
    action: str,
    request_id: str = '',
    requested_by: str = '',
    source: str = '',
    user_id: int | None = None,
    server_name: str = '',
    metadata: dict | None = None,
) -> BgAudit:
    return BgAudit.objects.create(
        action=str(action),
        request_id=str(request_id or ''),
        requested_by=str(requested_by or ''),
        source=str(source or ''),
        user_id=int(user_id) if user_id is not None else None,
        server_name=str(server_name or ''),
        metadata=metadata or {},
    )
