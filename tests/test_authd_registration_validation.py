"""Tests for authd mumble_userid self-healing validation.

Only Murmur's ``InvalidUserException`` proves a registration is gone. Transient
failures (bounded invocation timeouts from a stalled ICE dispatch, transport
errors) must NOT clear ``mumble_userid`` — doing so re-provisions a live
registration, creating duplicates and piling more calls onto the stalled
dispatch.
"""

from bg.authd import service as authd
from tests.conftest import IceOwnedInvalidUserException


class _FakeM:
    InvalidUserException = IceOwnedInvalidUserException


class _FakeSrv:
    def __init__(self, get_registration_raise=None):
        self._raise = get_registration_raise
        self.get_registration_calls = []

    def getRegistration(self, userid):
        self.get_registration_calls.append(userid)
        if self._raise is not None:
            raise self._raise
        return {}


def _patch_repair_hooks(monkeypatch):
    cleared = []
    provisioned = []
    monkeypatch.setattr(authd, '_clear_mumble_userid', cleared.append)
    monkeypatch.setattr(
        authd, '_provision_murmur_registration',
        lambda bg_row_id, *args: provisioned.append(bg_row_id),
    )
    return cleared, provisioned


def test_valid_registration_marks_validated_and_repairs_nothing(monkeypatch):
    cleared, provisioned = _patch_repair_hooks(monkeypatch)
    monkeypatch.setattr(authd, '_validated_ids', {})
    srv = _FakeSrv()

    authd._validate_and_repair_registration(7, 42, 'pilot', 'Pilot', _FakeM, srv)

    assert 42 in authd._validated_ids
    assert cleared == []
    assert provisioned == []


def test_missing_registration_clears_and_reprovisions(monkeypatch):
    cleared, provisioned = _patch_repair_hooks(monkeypatch)
    srv = _FakeSrv(get_registration_raise=IceOwnedInvalidUserException('no such user'))

    authd._validate_and_repair_registration(7, 42, 'pilot', 'Pilot', _FakeM, srv)

    assert cleared == [7]
    assert provisioned == [7]


def test_transient_failure_skips_cycle_without_clearing(monkeypatch):
    cleared, provisioned = _patch_repair_hooks(monkeypatch)
    srv = _FakeSrv(get_registration_raise=RuntimeError('invocation timed out'))

    authd._validate_and_repair_registration(7, 42, 'pilot', 'Pilot', _FakeM, srv)

    assert cleared == []
    assert provisioned == []
