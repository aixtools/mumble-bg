"""Public HTTP control entrypoints for mumble-bg."""

from django.http import HttpResponse
from django.urls import path

from . import control


def _health(_request):
    return HttpResponse('ok')


urlpatterns = [
    path('', _health),
    path('v1/registrations/sync', control.registrations_sync),
    path('v1/registrations/contract-sync', control.registration_contract_sync),
    path('v1/registrations/disable', control.registrations_disable),
    path('v1/admin-membership/sync', control.admin_membership_sync),
    path('v1/password-reset', control.password_reset),
    path('v1/control-key/bootstrap', control.control_key_bootstrap),
    path('v1/control-key/rotate', control.control_key_rotate),
    path('v1/control-key/status', control.control_key_status),
    path('v1/control-keys/export', control.control_keys_export),
    path('v1/pilot/<int:pkid>', control.pilot),
    path('v1/pilots/<int:pkid>', control.pilot),
    path('v1/registrations', control.registrations),
    path('v1/health', control.health),
    path('v1/servers', control.servers),
    path('v1/servers/<slug:server_key>/inventory', control.server_inventory),
    path('v1/access-rules/sync', control.access_rules_sync),
    path('v1/eve-objects/sync', control.eve_objects_sync),
    path('v1/pilot-snapshot/sync', control.pilot_snapshot_sync),
    path('v1/access-rules', control.access_rules),
    path('v1/eve-objects', control.eve_objects),
    path('v1/provision', control.provision),
    path('v1/public-key', control.public_key),
]
