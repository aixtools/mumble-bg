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
    path('v1/pilot/<int:pkid>', control.pilot),
    path('v1/pilots/<int:pkid>', control.pilot),
    path('v1/registrations', control.registrations),
    path('v1/health', control.health),
    path('v1/servers', control.servers),
]
