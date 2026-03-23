from django.test import SimpleTestCase

from bg.control import _BadRequest, _validate_password
from bg.provisioner import _new_password


class PasswordPolicyTest(SimpleTestCase):
    def test_space_is_rejected(self):
        with self.assertRaises(_BadRequest) as ctx:
            _validate_password("abc def123", field_name="password")
        self.assertIn("space", str(ctx.exception))

    def test_generated_password_has_no_spaces(self):
        generated = _new_password(64)
        self.assertNotIn(" ", generated)
