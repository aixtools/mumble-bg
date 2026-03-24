from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class InstallAssistantSchemaTest(SimpleTestCase):
    @patch("bg.state.management.commands.install_assistant.Command._existing_tables", return_value={"django_migrations"})
    @patch("bg.state.management.commands.install_assistant.MigrationRecorder")
    def test_schema_warning_when_migration_recorded_but_tables_missing(self, recorder_cls, _existing_tables):
        from bg.state.management.commands.install_assistant import Command

        recorder = recorder_cls.return_value
        recorder.has_table.return_value = True
        recorder.applied_migrations.return_value = {("state", "0000_initial")}

        result = Command()._check_schema_migration()

        self.assertEqual(result["status"], "warning")
        self.assertIn("required BG table(s) are missing", result["message"])
        self.assertIn("bg_pilot_account", result["message"])
        self.assertIn("bg_pilot_character", result["message"])


class InstallAssistantOutputTest(SimpleTestCase):
    @patch("bg.state.management.commands.install_assistant.Command._check_bg_db", return_value={"status": "ok", "message": "connected"})
    @patch("bg.state.management.commands.install_assistant.Command._check_control_psk", return_value={"status": "ok", "message": "set"})
    @patch("bg.state.management.commands.install_assistant.Command._check_control_url", return_value={"status": "warning", "message": "MURMUR_CONTROL_URL is not set"})
    @patch("bg.state.management.commands.install_assistant.Command._check_control_bind", return_value={"status": "warning", "message": "127.0.0.1:18080 (source=default)"})
    @patch("bg.state.management.commands.install_assistant.Command._check_encryption", return_value={"status": "ok", "message": "active"})
    @patch("bg.state.management.commands.install_assistant.Command._check_schema_migration", return_value={"status": "ok", "message": "state.0000_initial applied"})
    @patch(
        "bg.state.management.commands.install_assistant.Command._check_pilot_snapshot",
        return_value={
            "status": "warning",
            "message": "pilot snapshot tables are missing (run python manage.py migrate; if nothing applies, repair stale migration state)",
        },
    )
    @patch("bg.state.management.commands.install_assistant.Command._check_ice_endpoints", return_value={"status": "ok", "message": "all endpoints reachable", "endpoints": []})
    @patch(
        "bg.state.management.commands.install_assistant.Command._check_authd_registration",
        return_value={"status": "ok", "message": "registered on 1 target server(s)"},
    )
    def test_output_recommends_migrate_when_pilot_snapshot_detects_missing_tables(self, *_mocks):
        out = StringIO()

        call_command("install_assistant", stdout=out)

        self.assertIn("Recommended next step: python manage.py migrate", out.getvalue())
