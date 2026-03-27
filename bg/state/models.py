from django.db import models
import uuid
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
    ice_tls_cert = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        default=None,
        help_text='Optional ICE SSL/TLS certificate file path exposed to BG.',
    )
    ice_tls_key = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        default=None,
        help_text='Optional ICE SSL/TLS key file path exposed to BG.',
    )
    ice_tls_ca = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        default=None,
        help_text='Optional CA certificate that BG should trust for this ICE endpoint.',
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0, help_text='Ordering on the profile page (lower = first)')

    class Meta:
        db_table = 'mumble_server'
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class MurmurServerInventorySnapshot(models.Model):
    server = models.OneToOneField(
        MumbleServer,
        on_delete=models.CASCADE,
        related_name='inventory_snapshot',
    )
    payload = models.JSONField(blank=True, default=dict)
    fetch_status = models.CharField(max_length=32, blank=True, default='unknown')
    fetch_error = models.TextField(blank=True, default='')
    protocol = models.CharField(max_length=16, blank=True, default='')
    fetched_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'murmur_server_inventory_snapshot'
        ordering = ['server_id']

    def __str__(self):
        return f'{self.server_id}:{self.fetch_status}'


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

CATEGORY_ALLIANCE = 'alliance'
CATEGORY_CORPORATION = 'corporation'
CATEGORY_CHARACTER = 'character'

CATEGORY_CHOICES = [
    (CATEGORY_ALLIANCE, 'Alliance'),
    (CATEGORY_CORPORATION, 'Corporation'),
    (CATEGORY_CHARACTER, 'Character'),
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
    acl_admin = models.BooleanField(
        default=False,
        help_text='Pilot-only Murmur admin marker. Ignored for alliance/corporation rules.',
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
        constraints = [
            models.CheckConstraint(
                check=Q(acl_admin=False) | Q(entity_type=ENTITY_TYPE_PILOT),
                name='bg_access_rule_acl_admin_pilot_only',
            ),
        ]

    def __str__(self):
        action = 'DENY' if self.deny else 'ALLOW'
        return f'{action} {self.entity_type} {self.entity_id}'

    def save(self, *args, **kwargs):
        if self.entity_type != ENTITY_TYPE_PILOT:
            self.acl_admin = False
        if self.deny:
            self.acl_admin = False
        return super().save(*args, **kwargs)


class EveObject(models.Model):
    """Immutable EVE object dictionary row synchronized from FG."""

    entity_id = models.BigIntegerField(
        unique=True,
        help_text='EVE object ID (pilot, corporation, alliance).',
    )
    type = models.CharField(
        max_length=16,
        choices=ENTITY_TYPE_CHOICES,
    )
    category = models.CharField(
        max_length=16,
        choices=CATEGORY_CHOICES,
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        default='',
    )
    ticker = models.CharField(
        max_length=32,
        blank=True,
        default='',
    )
    synced_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bg_eve_object'
        ordering = ['type', 'entity_id']

    def __str__(self):
        return f'{self.type} ({self.category}) {self.entity_id} {self.name}'


class AccessRuleSyncAudit(models.Model):
    """
    Immutable audit history for ACL sync operations.

    The BG side should only insert rows when the effective active rules change.
    Rows are never edited or deleted and are intended for troubleshooting and
    incident review.
    """

    request_id = models.CharField(max_length=64, blank=True, default='')
    requested_by = models.CharField(max_length=255, blank=True, default='')
    action = models.CharField(max_length=16, default='sync', help_text='Operation that produced this record')
    state_before = models.JSONField(blank=True, default=dict)
    state_after = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bg_access_rule_audit'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.action} ({self.requested_by or "unknown"}) @ {self.created_at}'


class PilotAccountCache(models.Model):
    pkid = models.BigIntegerField(
        unique=True,
        help_text='Stable FG/BG account identity key.',
    )
    account_username = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Cube login username from the latest FG snapshot.',
    )
    pilot_data_hash = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        help_text='Hash of pilot snapshot payload for this account (md5 placeholder).',
    )
    display_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Computed display name from the latest FG snapshot.',
    )
    main_character_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text='Main character ID from the latest FG snapshot.',
    )
    main_character_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Main character name from the latest FG snapshot.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bg_pilot_account'
        ordering = ['pkid']

    def __str__(self):
        return str(self.pkid)


class PilotCharacterCache(models.Model):
    account = models.ForeignKey(
        PilotAccountCache,
        on_delete=models.CASCADE,
        related_name='characters',
    )
    character_id = models.BigIntegerField(unique=True)
    character_name = models.CharField(max_length=255)
    corporation_id = models.BigIntegerField(null=True, blank=True)
    corporation_name = models.CharField(max_length=255, blank=True, default='')
    alliance_id = models.BigIntegerField(null=True, blank=True)
    alliance_name = models.CharField(max_length=255, blank=True, default='')
    is_main = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bg_pilot_character'
        ordering = ['account__pkid', '-is_main', 'character_name', 'character_id']
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'character_id'],
                name='bg_pilot_character_unique_account_character',
            ),
        ]

    def __str__(self):
        return self.character_name


class PilotSnapshotSyncAudit(models.Model):
    request_id = models.CharField(max_length=64, blank=True, default='')
    requested_by = models.CharField(max_length=255, blank=True, default='')
    action = models.CharField(max_length=16, default='sync', help_text='Operation that produced this record')
    summary_before = models.JSONField(blank=True, default=dict)
    summary_after = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bg_pilot_snapshot_audit'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.action} ({self.requested_by or "unknown"}) @ {self.created_at}'


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


class ControlChannelKeyEntry(models.Model):
    """Rotating control-channel secrets ("keys") retained for drift/recovery.

    Stored encrypted (RSA-OAEP) so a DB leak does not reveal plaintext secrets.
    """

    key_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    secret_ciphertext_b64 = models.TextField(
        help_text='Base64 RSA ciphertext of the control secret (encrypted with BG public key).'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'control_channel_key_entry'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return str(self.key_id)


BG_AUDIT_ACTION_ACL_SYNC = 'acl_sync'
BG_AUDIT_ACTION_PILOT_CREATE = 'pilot_create'
BG_AUDIT_ACTION_PILOT_DISABLE = 'pilot_disable'
BG_AUDIT_ACTION_PILOT_ENABLE = 'pilot_enable'
BG_AUDIT_ACTION_PILOT_PWRESET = 'pilot_pwreset'
BG_AUDIT_ACTION_PILOT_LOGIN = 'pilot_login'
BG_AUDIT_ACTION_PILOT_DISPLAY_NAME_UPDATE = 'pilot_display_name_update'

BG_AUDIT_ACTION_CHOICES = [
    (BG_AUDIT_ACTION_ACL_SYNC, 'ACL Sync'),
    (BG_AUDIT_ACTION_PILOT_CREATE, 'Pilot Created'),
    (BG_AUDIT_ACTION_PILOT_DISABLE, 'Pilot Disabled'),
    (BG_AUDIT_ACTION_PILOT_ENABLE, 'Pilot Enabled'),
    (BG_AUDIT_ACTION_PILOT_PWRESET, 'Pilot Password Reset'),
    (BG_AUDIT_ACTION_PILOT_LOGIN, 'Pilot Authenticated'),
    (BG_AUDIT_ACTION_PILOT_DISPLAY_NAME_UPDATE, 'Pilot Display Name Updated'),
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
