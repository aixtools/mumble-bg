"""
Tests for registration probe payload shape.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, Client

from bg.state.models import MumbleServer, MumbleUser


class ProbePayloadShapeTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username='pilot', password='pass')
        self.server = MumbleServer.objects.create(
            name='Probe Server',
            address='127.0.0.1:64738',
            ice_host='127.0.0.1',
            ice_port=6502,
        )
        self.mumble_user = MumbleUser.objects.create(
            user=self.user,
            server=self.server,
            username='pilot_name',
            pwhash='hash',
        )

    def test_pilot_probe_payload_includes_user_id(self):
        response = self.client.get(f'/v1/pilots/{self.user.pk}')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        registrations = payload.get('registrations', [])
        self.assertEqual(len(registrations), 1)
        registration = registrations[0]

        self.assertEqual(registration.get('user_id'), self.user.pk)
        self.assertEqual(registration.get('pkid'), self.user.pk)
        self.assertEqual(registration.get('server_id'), self.server.pk)

    def test_registrations_payload_includes_user_id(self):
        response = self.client.get('/v1/registrations')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        registrations = payload.get('registrations', [])
        self.assertEqual(len(registrations), 1)
        registration = registrations[0]

        self.assertEqual(registration.get('user_id'), self.user.pk)
        self.assertEqual(registration.get('pkid'), self.user.pk)
        self.assertEqual(registration.get('server_id'), self.server.pk)
