"""MumbleServer.endpoint_entries / endpoint_list parsing."""

from django.test import SimpleTestCase

from bg.state.models import MumbleServer


class EndpointEntriesTest(SimpleTestCase):
    def test_labelled_and_plain_lines(self):
        s = MumbleServer(
            driver=MumbleServer.DRIVER_SHITSPEAK,
            address='eu-voice.example.org:64738',
            endpoints=(
                'US Voice | us-voice.example.org:64738\n'
                'eu-voice.example.org:64738\n'          # no label -> defaults to host
                'HK Voice | evil-voice-hk.example.org:64739'
            ),
        )
        self.assertEqual(
            s.endpoint_entries,
            [
                {'label': 'US Voice', 'host': 'us-voice.example.org', 'port': '64738',
                 'address': 'us-voice.example.org:64738'},
                {'label': 'eu-voice.example.org', 'host': 'eu-voice.example.org', 'port': '64738',
                 'address': 'eu-voice.example.org:64738'},
                {'label': 'HK Voice', 'host': 'evil-voice-hk.example.org', 'port': '64739',
                 'address': 'evil-voice-hk.example.org:64739'},
            ],
        )
        # endpoint_list stays clean host:port even with labels present
        self.assertEqual(
            s.endpoint_list,
            ['us-voice.example.org:64738', 'eu-voice.example.org:64738',
             'evil-voice-hk.example.org:64739'],
        )

    def test_comma_separator_and_whitespace(self):
        s = MumbleServer(endpoints='a.example:1 , b.example:2')
        self.assertEqual([e['address'] for e in s.endpoint_entries],
                         ['a.example:1', 'b.example:2'])

    def test_falls_back_to_address_when_empty(self):
        s = MumbleServer(address='only.example:64738', endpoints='')
        self.assertEqual(s.endpoint_entries,
                         [{'label': 'only.example', 'host': 'only.example',
                           'port': '64738', 'address': 'only.example:64738'}])

    def test_empty_everything(self):
        self.assertEqual(MumbleServer(address='', endpoints='').endpoint_entries, [])
