# Cube schema summary (from models.py)

Source: /home/michael/git/cube

Note: No migrations/*.py were found in this tree at scan time.

## cube/.venv/cube/lib/python3.12/site-packages/celery/backends/database/models.py
### class Task(ResultModelBase)
- (no model fields found by regex)

### class TaskExtended(Task)
- (no model fields found by regex)

### class TaskSet(ResultModelBase)
- (no model fields found by regex)

## cube/.venv/cube/lib/python3.12/site-packages/charset_normalizer/models.py
## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/admin/models.py
### class LogEntryManager(models.Manager)
- (no model fields found by regex)

### class LogEntry(models.Model)
- action_time: DateTimeField
- user: ForeignKey
- content_type: ForeignKey
- object_id: TextField
- object_repr: CharField
- action_flag: PositiveSmallIntegerField
- change_message: TextField

## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/auth/models.py
### class PermissionManager(models.Manager)
- (no model fields found by regex)

### class Permission(models.Model)
- name: CharField
- content_type: ForeignKey
- codename: CharField

### class GroupManager(models.Manager)
- (no model fields found by regex)

### class Group(models.Model)
- name: CharField
- permissions: ManyToManyField

### class UserManager(BaseUserManager)
- (no model fields found by regex)

### class PermissionsMixin(models.Model)
- is_superuser: BooleanField
- groups: ManyToManyField
- user_permissions: ManyToManyField

### class AbstractUser(AbstractBaseUser, PermissionsMixin)
- username: CharField
- first_name: CharField
- last_name: CharField
- email: EmailField
- is_staff: BooleanField
- is_active: BooleanField
- date_joined: DateTimeField

### class User(AbstractUser)
- (no model fields found by regex)

## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/contenttypes/models.py
### class ContentTypeManager(models.Manager)
- (no model fields found by regex)

### class ContentType(models.Model)
- app_label: CharField
- model: CharField

## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/flatpages/models.py
### class FlatPage(models.Model)
- url: CharField
- title: CharField
- content: TextField
- enable_comments: BooleanField
- template_name: CharField
- registration_required: BooleanField
- sites: ManyToManyField

## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/gis/db/backends/base/models.py
## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/gis/db/backends/oracle/models.py
### class OracleGeometryColumns(models.Model)
- table_name: CharField
- column_name: CharField
- srid: IntegerField

### class OracleSpatialRefSys(models.Model, SpatialRefSysMixin)
- cs_name: CharField
- srid: IntegerField
- auth_srid: IntegerField
- auth_name: CharField
- wktext: CharField
- cs_bounds: PolygonField

## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/gis/db/backends/postgis/models.py
### class PostGISGeometryColumns(models.Model)
- f_table_catalog: CharField
- f_table_schema: CharField
- f_table_name: CharField
- f_geometry_column: CharField
- coord_dimension: IntegerField
- srid: IntegerField
- type: CharField

### class PostGISSpatialRefSys(models.Model, SpatialRefSysMixin)
- srid: IntegerField
- auth_name: CharField
- auth_srid: IntegerField
- srtext: CharField
- proj4text: CharField

## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/gis/db/backends/spatialite/models.py
### class SpatialiteGeometryColumns(models.Model)
- f_table_name: CharField
- f_geometry_column: CharField
- coord_dimension: IntegerField
- srid: IntegerField
- spatial_index_enabled: IntegerField
- type: IntegerField

### class SpatialiteSpatialRefSys(models.Model, SpatialRefSysMixin)
- srid: IntegerField
- auth_name: CharField
- auth_srid: IntegerField
- ref_sys_name: CharField
- proj4text: CharField
- srtext: CharField

## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/redirects/models.py
### class Redirect(models.Model)
- site: ForeignKey
- old_path: CharField
- new_path: CharField

## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/sessions/models.py
### class SessionManager(BaseSessionManager)
- (no model fields found by regex)

### class Session(AbstractBaseSession)
- (no model fields found by regex)

## cube/.venv/cube/lib/python3.12/site-packages/django/contrib/sites/models.py
### class SiteManager(models.Manager)
- (no model fields found by regex)

### class Site(models.Model)
- domain: CharField
- name: CharField

## cube/.venv/cube/lib/python3.12/site-packages/django/db/migrations/operations/models.py
### class ModelOperation(Operation)
- (no model fields found by regex)

### class CreateModel(ModelOperation)
- (no model fields found by regex)

### class DeleteModel(ModelOperation)
- (no model fields found by regex)

### class RenameModel(ModelOperation)
- (no model fields found by regex)

### class ModelOptionOperation(ModelOperation)
- (no model fields found by regex)

### class AlterModelTable(ModelOptionOperation)
- (no model fields found by regex)

### class AlterModelTableComment(ModelOptionOperation)
- (no model fields found by regex)

### class AlterTogetherOptionOperation(ModelOptionOperation)
- (no model fields found by regex)

### class AlterUniqueTogether(AlterTogetherOptionOperation)
- (no model fields found by regex)

### class AlterIndexTogether(AlterTogetherOptionOperation)
- (no model fields found by regex)

### class AlterOrderWithRespectTo(ModelOptionOperation)
- (no model fields found by regex)

### class AlterModelOptions(ModelOptionOperation)
- (no model fields found by regex)

### class AlterModelManagers(ModelOptionOperation)
- (no model fields found by regex)

### class IndexOperation(Operation)
- (no model fields found by regex)

### class AddIndex(IndexOperation)
- (no model fields found by regex)

### class RemoveIndex(IndexOperation)
- (no model fields found by regex)

### class RenameIndex(IndexOperation)
- old_index: Index

### class AddConstraint(IndexOperation)
- (no model fields found by regex)

### class RemoveConstraint(IndexOperation)
- (no model fields found by regex)

## cube/.venv/cube/lib/python3.12/site-packages/django/forms/models.py
### class ModelFormMetaclass(DeclarativeFieldsMetaclass)
- (no model fields found by regex)

### class BaseModelForm(BaseForm, AltersData)
- (no model fields found by regex)

### class ModelForm(BaseModelForm, metaclass=ModelFormMetaclass)
- (no model fields found by regex)

### class BaseModelFormSet(BaseFormSet, AltersData)
- (no model fields found by regex)

### class BaseInlineFormSet(BaseModelFormSet)
- (no model fields found by regex)

### class InlineForeignKeyField(Field)
- (no model fields found by regex)

### class ModelChoiceField(ChoiceField)
- (no model fields found by regex)

### class ModelMultipleChoiceField(ModelChoiceField)
- (no model fields found by regex)

## cube/.venv/cube/lib/python3.12/site-packages/django_celery_results/models.py
### class TaskResult(models.Model)
- task_id: CharField
- periodic_task_name: CharField
- task_name: CharField
- task_args: TextField
- task_kwargs: TextField
- status: CharField
- worker: CharField
- content_type: CharField
- content_encoding: CharField
- result: TextField
- date_created: DateTimeField
- date_started: DateTimeField
- date_done: DateTimeField
- traceback: TextField
- meta: TextField

### class ChordCounter(models.Model)
- group_id: CharField
- sub_tasks: TextField
- count: PositiveIntegerField

### class GroupResult(models.Model)
- group_id: CharField
- date_created: DateTimeField
- date_done: DateTimeField
- content_type: CharField
- content_encoding: CharField
- result: TextField

## cube/.venv/cube/lib/python3.12/site-packages/kombu/transport/sqlalchemy/models.py
## cube/.venv/cube/lib/python3.12/site-packages/pip/_internal/utils/models.py
## cube/.venv/cube/lib/python3.12/site-packages/pip/_vendor/requests/models.py
### class Request(RequestHooksMixin)
- (no model fields found by regex)

### class PreparedRequest(RequestEncodingMixin, RequestHooksMixin)
- (no model fields found by regex)

## cube/.venv/cube/lib/python3.12/site-packages/requests/models.py
### class Request(RequestHooksMixin)
- (no model fields found by regex)

### class PreparedRequest(RequestEncodingMixin, RequestHooksMixin)
- (no model fields found by regex)

## cube/accounts/models.py
### class UserProfile(models.Model)
- user: OneToOneField
- is_member: BooleanField
- member_since: DateTimeField
- member_notes: TextField
- discord_id: CharField
- discord_username: CharField
- discord_discriminator: CharField
- discord_avatar: CharField
- discord_access_token: TextField
- discord_refresh_token: TextField
- discord_token_expires: DateTimeField

### class EveCharacter(models.Model)
- user: ForeignKey
- character_id: BigIntegerField
- character_name: CharField
- corporation_id: BigIntegerField
- corporation_name: CharField
- alliance_id: BigIntegerField
- alliance_name: CharField
- is_main: BooleanField
- access_token: TextField
- refresh_token: TextField
- token_expires: DateTimeField
- scopes: TextField
- created_at: DateTimeField
- updated_at: DateTimeField

### class Group(models.Model)
- name: CharField
- description: TextField
- created_by: ForeignKey
- created_at: DateTimeField
- auto_accept: BooleanField

### class GroupDiscordConfig(models.Model)
- group: OneToOneField
- webhook_url: URLField
- enabled: BooleanField
- default_role_ids: JSONField
- default_mention_text: TextField
- enable_events: BooleanField
- default_event_channel_id: CharField
- default_event_location: CharField
- last_srp_pending_alert_at: DateTimeField
- created_at: DateTimeField
- updated_at: DateTimeField

### class GroupDiscordAlertConfig(models.Model)
- group: ForeignKey
- alert_type: CharField
- enabled: BooleanField
- ping_enabled: BooleanField
- ping_role_ids: JSONField
- mention_text: TextField
- message_template: TextField
- filters: JSONField
- last_sent_at: DateTimeField
- created_at: DateTimeField
- updated_at: DateTimeField

### class DiscordNotificationRule(models.Model)
- name: CharField
- alert_type: CharField
- enabled: BooleanField
- message_template: TextField
- filters: JSONField
- ping_enabled: BooleanField
- ping_role_ids: JSONField
- mention_text: TextField
- check_interval_hours: DecimalField
- next_run_at: DateTimeField
- created_by: ForeignKey
- created_at: DateTimeField
- updated_at: DateTimeField

### class DiscordNotificationTarget(models.Model)
- rule: ForeignKey
- group: ForeignKey
- enabled: BooleanField
- use_rule_ping: BooleanField
- ping_enabled: BooleanField
- ping_role_ids: JSONField
- mention_text: TextField
- last_sent_at: DateTimeField
- last_event_at: DateTimeField
- last_event_id: BigIntegerField

### class GroupMembership(models.Model)
- group: ForeignKey
- user: ForeignKey
- status: CharField
- is_admin: BooleanField
- requested_at: DateTimeField
- approved_at: DateTimeField
- approved_by: ForeignKey

### class Notification(models.Model)
- user: ForeignKey
- notification_type: CharField
- title: CharField
- message: TextField
- is_read: BooleanField
- created_at: DateTimeField
- group: ForeignKey

### class CharacterRefreshCooldown(models.Model)
- character: ForeignKey
- module_name: CharField
- last_refreshed: DateTimeField

### class SiteSettings(models.Model)
- eve_client_id: CharField
- eve_secret_key: CharField
- eve_callback_url: CharField
- discord_client_id: CharField
- discord_client_secret: CharField
- discord_redirect_uri: CharField
- discord_bot_token: CharField
- discord_guild_id: CharField
- allowed_alliance_ids: TextField
- allowed_corporation_ids: TextField

## cube/hivemind/models.py
### class APIKey(models.Model)
- name: CharField
- user: ForeignKey
- key_prefix: CharField
- key_hash: CharField
- scopes: JSONField
- allowed_characters: ManyToManyField
- requests_per_minute: IntegerField
- requests_per_hour: IntegerField
- is_active: BooleanField
- is_revoked: BooleanField
- created_at: DateTimeField
- last_used: DateTimeField
- last_ip: GenericIPAddressField

### class ESIRequest(models.Model)
- character: ForeignKey
- api_key: ForeignKey
- endpoint: CharField
- method: CharField
- status: CharField
- error: TextField
- response_time_ms: IntegerField
- cache_hit: BooleanField
- created_at: DateTimeField

### class HivemindMetrics(models.Model)
- total_requests: BigIntegerField
- successful_requests: BigIntegerField
- failed_requests: BigIntegerField
- cache_hits: BigIntegerField
- cache_misses: BigIntegerField
- total_response_time_ms: BigIntegerField
- error_rate_errors: BigIntegerField
- error_rate_limited: BigIntegerField
- average_response_time_ms: IntegerField
- last_updated: DateTimeField

## cube/modules/assets/models.py
### class AssetType(models.Model)
- type_id: IntegerField
- name: CharField
- group_id: IntegerField
- group_name: CharField
- category_id: IntegerField
- category_name: CharField

### class AssetLocation(models.Model)
- location_id: BigIntegerField
- name: CharField
- location_type: CharField
- solar_system_id: IntegerField
- solar_system_name: CharField
- region_id: IntegerField
- region_name: CharField
- last_updated: DateTimeField

### class CharacterAsset(models.Model)
- character: ForeignKey
- item_id: BigIntegerField
- type_id: IntegerField
- type_name: CharField
- location_id: BigIntegerField
- location_name: CharField
- location_type: CharField
- root_location_id: BigIntegerField
- root_location_name: CharField
- parent_item_id: BigIntegerField
- parent_item_name: CharField
- location_flag: CharField
- quantity: IntegerField
- is_blueprint_copy: BooleanField
- is_singleton: BooleanField
- last_updated: DateTimeField

### class CharacterAssetsSummary(models.Model)
- character: OneToOneField
- total_items: IntegerField
- total_quantity: BigIntegerField
- unique_types: IntegerField
- unique_locations: IntegerField
- last_updated: DateTimeField

## cube/modules/corporation/models.py
### class CorporationSettings(models.Model)
- alliance_leader_groups: ManyToManyField
- corp_leader_groups: ManyToManyField
- diplomat_groups: ManyToManyField

### class CorporationAsset(models.Model)
- corporation_id: BigIntegerField
- item_id: BigIntegerField
- type_id: IntegerField
- type_name: CharField
- location_id: BigIntegerField
- location_name: CharField
- location_flag: CharField
- quantity: IntegerField
- is_blueprint_copy: BooleanField
- is_singleton: BooleanField
- last_updated: DateTimeField

### class CorporationAssetsSummary(models.Model)
- corporation_id: BigIntegerField
- corporation_name: CharField
- total_items: IntegerField
- total_quantity: BigIntegerField
- unique_types: IntegerField
- unique_locations: IntegerField
- last_synced: DateTimeField
- sync_character: ForeignKey
- sync_error: TextField

### class RecruitingCorporation(models.Model)
- corporation_id: BigIntegerField
- corporation_name: CharField
- is_recruiting: BooleanField
- recruiting_message: TextField
- created_at: DateTimeField
- updated_at: DateTimeField

### class RecruitingApplication(models.Model)
- user: ForeignKey
- target_corporation: ForeignKey
- status: CharField
- applied_at: DateTimeField
- updated_at: DateTimeField
- applicant_notes: TextField
- reviewer_notes: TextField
- reviewed_by: ForeignKey

## cube/modules/counter_intel/models.py
### class CounterIntelSettings(models.Model)
- enabled: BooleanField
- min_character_age_days: PositiveIntegerField
- min_corp_tenure_days: PositiveIntegerField
- max_corp_hops_90d: PositiveIntegerField
- max_corp_hops_365d: PositiveIntegerField
- risk_score_threshold: PositiveIntegerField
- scan_cooldown_hours: PositiveIntegerField
- target_full_sweep_days: PositiveSmallIntegerField
- daily_budget_percent: PositiveSmallIntegerField
- max_characters_per_day: PositiveIntegerField
- max_characters_per_window: PositiveSmallIntegerField
- priority_new_character_hours: PositiveSmallIntegerField
- scan_window_start_hour: PositiveSmallIntegerField
- scan_window_end_hour: PositiveSmallIntegerField
- inactivity_flags_enabled: BooleanField
- inactivity_scan_threshold: PositiveSmallIntegerField
- fleet_inactivity_enabled: BooleanField
- fleet_inactivity_days: PositiveSmallIntegerField
- standings_source: CharField
- standings_corporation_id: BigIntegerField
- standings_alliance_id: BigIntegerField
- monitor_neutral_transfers: BooleanField
- transfer_lookback_days: PositiveIntegerField
- new_character_grace_hours: PositiveIntegerField
- isk_transfer_min_hostile: BigIntegerField
- isk_transfer_min_neutral: BigIntegerField
- contract_value_min_hostile: BigIntegerField
- contract_value_min_neutral: BigIntegerField
- unlinked_isk_transfer_min: BigIntegerField
- unlinked_contract_value_min: BigIntegerField
- friendly_alliance_ids: JSONField
- friendly_corporation_ids: JSONField
- hostile_alliance_ids: JSONField
- hostile_corporation_ids: JSONField
- last_scan_at: DateTimeField

### class CounterIntelCase(models.Model)
- user: OneToOneField
- status: CharField
- risk_score: PositiveIntegerField
- kills_total: PositiveIntegerField
- losses_total: PositiveIntegerField
- kills_recent: PositiveIntegerField
- losses_recent: PositiveIntegerField
- kills_since_join: PositiveIntegerField
- losses_since_join: PositiveIntegerField
- kill_stats_source: CharField
- kill_stats_updated_at: DateTimeField
- last_scanned_at: DateTimeField
- last_flagged_at: DateTimeField
- reviewed_by: ForeignKey
- reviewed_at: DateTimeField
- review_notes: TextField
- created_at: DateTimeField
- updated_at: DateTimeField

### class CounterIntelFlag(models.Model)
- case: ForeignKey
- character: ForeignKey
- reason: CharField
- severity: PositiveIntegerField
- details: JSONField
- is_active: BooleanField
- source: CharField
- created_at: DateTimeField

### class CounterIntelCharacterState(models.Model)
- character: OneToOneField
- last_wallet_journal_id: BigIntegerField
- last_wallet_journal_date: DateTimeField
- last_contract_id: BigIntegerField
- last_contract_date: DateTimeField
- last_killmail_id: BigIntegerField
- last_killmail_date: DateTimeField
- no_wallet_activity_scans: PositiveIntegerField
- no_contract_activity_scans: PositiveIntegerField
- no_killmail_activity_scans: PositiveIntegerField
- no_wallet_movement_scans: PositiveIntegerField
- updated_at: DateTimeField

### class CounterIntelDailyUsage(models.Model)
- date: DateField
- users_scanned: PositiveIntegerField
- characters_scanned: PositiveIntegerField
- updated_at: DateTimeField

### class CounterIntelWindowUsage(models.Model)
- window_start: DateTimeField
- characters_scanned: PositiveIntegerField
- updated_at: DateTimeField

## cube/modules/doctrines/models.py
### class Doctrine(models.Model)
- name: CharField
- description: TextField
- is_active: BooleanField
- created_at: DateTimeField
- updated_at: DateTimeField

### class DoctrineSettings(models.Model)
- editor_groups: ManyToManyField

### class DoctrineFit(models.Model)
- doctrines: ManyToManyField
- name: CharField
- ship_type_id: BigIntegerField
- ship_type_name: CharField
- input_method: CharField
- eft_text: TextField
- notes: TextField
- version: CharField
- primary_fit_label: CharField
- alt_eft_texts: JSONField
- alt_eft_labels: JSONField
- alt_desired_fit_stock: JSONField
- desired_ship_stock: PositiveIntegerField
- desired_fit_stock: PositiveIntegerField
- is_active: BooleanField
- srp_eligible: BooleanField
- created_by: ForeignKey
- created_at: DateTimeField
- updated_at: DateTimeField

### class DoctrineFitItem(models.Model)
- fit: ForeignKey
- type_id: BigIntegerField
- type_name: CharField
- quantity: PositiveIntegerField
- is_required: BooleanField
- slot_group: CharField
- allowed_group_ids: JSONField

### class DoctrineFitItemAlternative(models.Model)
- fit_item: ForeignKey
- type_id: BigIntegerField
- type_name: CharField

### class EsiGroupCache(models.Model)
- group_id: BigIntegerField
- name: CharField
- category_id: BigIntegerField
- type_ids: JSONField
- last_updated: DateTimeField

### class EsiTypeCache(models.Model)
- type_id: BigIntegerField
- name: CharField
- group_id: BigIntegerField
- category_id: BigIntegerField
- dogma_attributes: JSONField
- dogma_effects: JSONField
- last_updated: DateTimeField

## cube/modules/esi_queue/models.py
### class EsiQueueRequest(models.Model)
- created_at: DateTimeField
- updated_at: DateTimeField
- next_run_at: DateTimeField
- last_attempt_at: DateTimeField
- completed_at: DateTimeField
- status: CharField
- priority: PositiveSmallIntegerField
- source: CharField
- endpoint: CharField
- method: CharField
- params: JSONField
- data: JSONField
- headers: JSONField
- character: ForeignKey
- bypass_budget: BooleanField
- expected_token_cost: PositiveSmallIntegerField
- attempts: PositiveSmallIntegerField
- max_attempts: PositiveSmallIntegerField
- response_status: IntegerField
- response_headers: JSONField
- response_body: JSONField
- error_message: TextField
- token_cost: PositiveSmallIntegerField

## cube/modules/fleet_tracking/models.py
### class FleetTrackingConfig(models.Model)
- name: CharField
- commander: ForeignKey
- interval_minutes: PositiveIntegerField
- enabled: BooleanField
- notify_on_track: BooleanField
- srp_enabled: BooleanField
- participation_enabled: BooleanField
- doctrine: ForeignKey
- last_tracked_at: DateTimeField
- last_fleet_id: BigIntegerField
- last_member_count: PositiveIntegerField
- last_error: TextField
- last_error_at: DateTimeField
- ended_at: DateTimeField
- ended_by: ForeignKey
- created_at: DateTimeField
- updated_at: DateTimeField

### class FleetSnapshot(models.Model)
- config: ForeignKey
- fleet_id: BigIntegerField
- fleet_name: CharField
- tracked_at: DateTimeField
- member_count: PositiveIntegerField
- interval_minutes: PositiveIntegerField
- participation_enabled: BooleanField
- is_final: BooleanField

### class FleetMemberSnapshot(models.Model)
- snapshot: ForeignKey
- character_id: BigIntegerField
- character_name: CharField
- corporation_id: BigIntegerField
- corporation_name: CharField
- alliance_id: BigIntegerField
- alliance_name: CharField
- role: CharField
- wing_id: BigIntegerField
- squad_id: BigIntegerField
- ship_type_id: BigIntegerField
- ship_type_name: CharField

### class FleetParticipationSummary(models.Model)
- date: DateField
- character_id: BigIntegerField
- character_name: CharField
- corporation_id: BigIntegerField
- corporation_name: CharField
- alliance_id: BigIntegerField
- alliance_name: CharField
- snapshot_count: PositiveIntegerField
- fleet_count: PositiveIntegerField
- minutes_tracked: PositiveIntegerField
- updated_at: DateTimeField

### class FleetKillmailCheckpoint(models.Model)
- character: OneToOneField
- last_killmail_id: BigIntegerField
- last_checked_at: DateTimeField

### class FleetKillmailRecord(models.Model)
- character: ForeignKey
- killmail_id: BigIntegerField
- killmail_hash: CharField
- ship_type_id: BigIntegerField
- ship_type_name: CharField
- killmail_time: DateTimeField
- matched_snapshot: ForeignKey
- created_at: DateTimeField

### class FleetTrackingSettings(models.Model)
- retention_days: PositiveIntegerField
- participation_label: CharField
- fc_groups: ManyToManyField
- corp_view_groups: ManyToManyField
- alliance_view_groups: ManyToManyField

## cube/modules/hr_notes/models.py
### class HRNote(models.Model)
- subject: ForeignKey
- author: ForeignKey
- category: CharField
- content: TextField
- created_at: DateTimeField
- updated_at: DateTimeField

### class HRNoteAttachment(models.Model)
- note: ForeignKey
- image: ImageField
- original_filename: CharField
- uploaded_at: DateTimeField

## cube/modules/market/models.py
### class MarketPrice(models.Model)
- type_id: BigIntegerField
- region_id: BigIntegerField
- price_isk: BigIntegerField
- last_updated: DateTimeField
- source_date: DateField

## cube/modules/market_seeding/models.py
### class MarketSeedSettings(models.Model)
- enabled: BooleanField
- enable_doctrine_sync: BooleanField
- doctrine_target_days: PositiveIntegerField
- bulk_target_days: PositiveIntegerField
- shipping_rate_isk_per_m3: BigIntegerField
- min_shipping_isk: BigIntegerField
- price_ceiling_percent: FloatField
- coverage_green_threshold: PositiveIntegerField
- coverage_yellow_threshold: PositiveIntegerField
- manager_groups: ManyToManyField
- viewer_groups: ManyToManyField
- last_refresh: DateTimeField

### class MarketSeedItem(models.Model)
- type_id: BigIntegerField
- type_name: CharField
- category_name: CharField
- group_name: CharField
- volume_m3: FloatField
- minimal_desired_stock: PositiveIntegerField
- price_ceiling_percent: FloatField
- source: CharField
- is_active: BooleanField
- created_at: DateTimeField
- updated_at: DateTimeField

### class MonitoredMarket(models.Model)
- structure: ForeignKey
- enabled: BooleanField
- is_primary: BooleanField
- is_visible: BooleanField
- region_id: BigIntegerField
- access_character: ForeignKey
- max_pages: PositiveIntegerField
- last_refreshed: DateTimeField

### class MarketSeedStock(models.Model)
- market: ForeignKey
- item: ForeignKey
- quantity: BigIntegerField
- quantity_below_target: BigIntegerField
- lowest_sell_isk: BigIntegerField
- last_price_updated: DateTimeField
- last_quantity_updated: DateTimeField
- last_updated: DateTimeField

### class MarketSeedTarget(models.Model)
- market: ForeignKey
- item: ForeignKey
- minimal_desired_stock: PositiveIntegerField
- suggested_minimal_stock: PositiveIntegerField
- suggested_updated_at: DateTimeField

### class MarketSeedDoctrineConfig(models.Model)
- doctrine: OneToOneField
- target_days: PositiveIntegerField
- updated_at: DateTimeField

### class MarketSeedDoctrineMarket(models.Model)
- market: ForeignKey
- doctrine: ForeignKey
- enabled: BooleanField
- updated_at: DateTimeField

## cube/modules/mining_ledger/models.py
### class MiningLedgerEntry(models.Model)
- character: ForeignKey
- date: DateField
- quantity: BigIntegerField
- solar_system_id: BigIntegerField
- type_id: BigIntegerField
- created_at: DateTimeField
- updated_at: DateTimeField

### class CharacterMiningSummary(models.Model)
- character: OneToOneField
- total_entries: IntegerField
- total_quantity: BigIntegerField
- last_refreshed: DateTimeField
- last_error: TextField
- updated_at: DateTimeField

## cube/modules/recruiting_blacklist/models.py
### class RecruitingBlacklistEntry(models.Model)
- character_id: BigIntegerField
- character_name: CharField
- discord_id: CharField
- discord_username: CharField
- status: CharField
- reason: TextField
- banned_by: ForeignKey
- created_at: DateTimeField
- updated_at: DateTimeField
- is_active: BooleanField
- deactivated_at: DateTimeField
- deactivated_by: ForeignKey

### class ApplicationBlacklistFlag(models.Model)
- application: ForeignKey
- blacklist_entry: ForeignKey
- match_type: CharField
- matched_value: CharField
- notification_sent: BooleanField
- notification_sent_at: DateTimeField
- reviewed: BooleanField
- reviewed_at: DateTimeField
- reviewed_by: ForeignKey
- created_at: DateTimeField

## cube/modules/skills/models.py
### class SkillGroup(models.Model)
- group_id: IntegerField
- name: CharField

### class SkillType(models.Model)
- type_id: IntegerField
- name: CharField
- description: TextField
- group: ForeignKey
- primary_attribute: CharField
- secondary_attribute: CharField
- training_time_multiplier: IntegerField

### class CharacterSkill(models.Model)
- character: ForeignKey
- skill: ForeignKey
- active_skill_level: IntegerField
- trained_skill_level: IntegerField
- skillpoints_in_skill: BigIntegerField
- last_updated: DateTimeField

### class SkillQueueItem(models.Model)
- character: ForeignKey
- skill: ForeignKey
- queue_position: IntegerField
- finished_level: IntegerField
- start_date: DateTimeField
- finish_date: DateTimeField
- training_start_sp: BigIntegerField
- level_start_sp: BigIntegerField
- level_end_sp: BigIntegerField

### class CharacterAttributes(models.Model)
- character: OneToOneField
- intelligence: IntegerField
- memory: IntegerField
- perception: IntegerField
- willpower: IntegerField
- charisma: IntegerField
- bonus_remaps: IntegerField
- last_remap_date: DateTimeField
- accrued_remap_cooldown_date: DateTimeField
- last_updated: DateTimeField

### class CharacterSkillsSummary(models.Model)
- character: OneToOneField
- total_sp: BigIntegerField
- unallocated_sp: BigIntegerField
- last_updated: DateTimeField

### class CharacterWallet(models.Model)
- character: OneToOneField
- balance: DecimalField
- last_updated: DateTimeField

## cube/modules/srp/models.py
### class SrpSettings(models.Model)
- token_display_name: CharField
- token_value_isk: PositiveIntegerField
- min_payout_isk: PositiveIntegerField
- include_fittings: BooleanField
- include_cargo: BooleanField
- rounding_mode: CharField
- manual_claim_max_age_days: PositiveIntegerField
- reviewer_groups: ManyToManyField

### class SrpClaim(models.Model)
- killmail: OneToOneField
- character: ForeignKey
- snapshot: ForeignKey
- popup_fleet: ForeignKey
- doctrine_fit: ForeignKey
- status: CharField
- fit_status: CharField
- fit_check_details: JSONField
- fit_checked_at: DateTimeField
- estimated_isk: BigIntegerField
- price_breakdown: JSONField
- requested_sins: PositiveIntegerField
- approved_sins: PositiveIntegerField
- requester_note: TextField
- denial_note: TextField
- reviewed_by: ForeignKey
- reviewed_at: DateTimeField
- created_at: DateTimeField
- updated_at: DateTimeField

### class SrpBalance(models.Model)
- character: OneToOneField
- balance: PositiveIntegerField
- updated_at: DateTimeField

### class SrpRedemptionRequest(models.Model)
- character: ForeignKey
- requested_by: ForeignKey
- amount: PositiveIntegerField
- status: CharField
- reviewed_by: ForeignKey
- reviewed_at: DateTimeField
- created_at: DateTimeField
- updated_at: DateTimeField

### class SrpPopupFleet(models.Model)
- name: CharField
- notes: TextField
- token: CharField
- expires_at: DateTimeField
- created_by: ForeignKey
- created_at: DateTimeField

## cube/modules/structure_fuel/models.py
### class StructureFuelSettings(models.Model)
- enabled: BooleanField
- notify_group: ForeignKey
- min_fuel_days: IntegerField
- critical_fuel_days: IntegerField
- check_frequency_hours: IntegerField
- last_checked: DateTimeField

## cube/modules/structures/models.py
### class Structure(models.Model)
- structure_id: BigIntegerField
- name: CharField
- owner_id: BigIntegerField
- owner_name: CharField
- owner_type: CharField
- corporation_id: BigIntegerField
- corporation_name: CharField
- alliance_id: BigIntegerField
- alliance_name: CharField
- solar_system_id: IntegerField
- solar_system_name: CharField
- region_id: IntegerField
- region_name: CharField
- type_id: IntegerField
- type_name: CharField
- group_id: IntegerField
- group_name: CharField
- state: CharField
- state_timer_start: DateTimeField
- state_timer_end: DateTimeField
- unanchors_at: DateTimeField
- reinforce_hour: IntegerField
- next_reinforce_hour: IntegerField
- next_reinforce_apply: DateTimeField
- fuel_expires: DateTimeField
- ansiblex_ozone_qty: BigIntegerField
- ansiblex_ozone_updated_at: DateTimeField
- metenox_magmatic_gas_qty: BigIntegerField
- metenox_magmatic_gas_updated_at: DateTimeField
- assets_value_isk: BigIntegerField
- moon_material_value_isk: BigIntegerField
- assets_value_updated_at: DateTimeField
- has_core: BooleanField
- core_status: CharField
- profile_id: IntegerField
- has_services: BooleanField
- discovered_by: IntegerField
- last_updated: DateTimeField
- last_online_time: DateTimeField
- fuel_alerted_at: DateTimeField
- fuel_alerted_critical_at: DateTimeField
- tags: JSONField

### class StructureService(models.Model)
- structure: ForeignKey
- name: CharField
- state: CharField

### class StructureUpdateLog(models.Model)
- structure: ForeignKey
- character_id: IntegerField
- character_name: CharField
- updated_at: DateTimeField
- success: BooleanField
- error_message: TextField

### class DiscordNotificationConfig(models.Model)
- name: CharField
- webhook_url: URLField
- enabled: BooleanField
- monitor_corporations: JSONField
- monitor_alliances: JSONField
- notify_on_reinforced: BooleanField
- notify_on_anchoring: BooleanField
- notify_on_unanchoring: BooleanField
- notify_on_low_fuel: BooleanField
- notify_on_attacked: BooleanField
- created_at: DateTimeField
- updated_at: DateTimeField

### class StructureStateHistory(models.Model)
- structure: ForeignKey
- previous_state: CharField
- new_state: CharField
- changed_at: DateTimeField
- notification_sent: BooleanField

## cube/modules/tax_tracking/models.py
### class CorporationTaxConfig(models.Model)
- corporation_id: BigIntegerField
- corporation_name: CharField
- managers: ManyToManyField
- wallet_character: ForeignKey
- target_tax_rate: FloatField
- enabled: BooleanField
- last_checked: DateTimeField
- created_at: DateTimeField
- updated_at: DateTimeField

### class TaxRateHistory(models.Model)
- corporation: ForeignKey
- current_tax_rate: FloatField
- target_tax_rate: FloatField
- wallet_balance: BigIntegerField
- expected_tax: BigIntegerField
- comparison: CharField
- checked_at: DateTimeField
- created_at: DateTimeField

### class TaxReportSnapshot(models.Model)
- corporation: ForeignKey
- year: IntegerField
- month: IntegerField
- entries_count: IntegerField
- avg_tax_rate: FloatField
- min_tax_rate: FloatField
- max_tax_rate: FloatField
- total_expected_tax: BigIntegerField
- created_at: DateTimeField
- updated_at: DateTimeField

### class CorporationMonthlyIncome(models.Model)
- corporation: ForeignKey
- year: IntegerField
- month: IntegerField
- total_income: BigIntegerField
- bounty_income: BigIntegerField
- mission_income: BigIntegerField
- other_income: BigIntegerField
- transaction_count: IntegerField
- last_entry_date: DateTimeField
- tax_owed: BigIntegerField
- tax_rate: FloatField
- created_at: DateTimeField
- updated_at: DateTimeField

## cube/modules/transactions/models.py
### class WalletJournalEntry(models.Model)
- character: ForeignKey
- journal_id: BigIntegerField
- date: DateTimeField
- ref_type: CharField
- first_party_id: BigIntegerField
- first_party_name: CharField
- second_party_id: BigIntegerField
- second_party_name: CharField
- amount: DecimalField
- balance: DecimalField
- reason: TextField
- description: CharField
- context_id: BigIntegerField
- context_id_type: CharField
- tax: DecimalField
- tax_receiver_id: BigIntegerField

### class WalletJournalSyncStatus(models.Model)
- character: OneToOneField
- last_synced: DateTimeField
- sync_error: TextField
