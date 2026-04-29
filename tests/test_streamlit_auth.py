import os
import unittest
from unittest.mock import patch

from streamlit_app import _check_trusted_header_auth, _get_header_value


class TestStreamlitAuth(unittest.TestCase):
    def test_get_header_value_is_case_insensitive(self) -> None:
        headers = {"X-Authenticated-User": "alice@example.com"}
        self.assertEqual(
            _get_header_value(headers, "x-authenticated-user"),
            "alice@example.com",
        )

    @patch.dict(
        os.environ,
        {
            "APP_TRUSTED_AUTH_HEADER": "X-Authenticated-User",
            "APP_TRUSTED_AUTH_VALUE": "",
            "APP_TRUSTED_USER_HEADER": "",
        },
        clear=False,
    )
    def test_trusted_header_auth_uses_header_value_as_principal(self) -> None:
        headers = {"x-authenticated-user": "alice@example.com"}
        authenticated, principal = _check_trusted_header_auth(headers)
        self.assertTrue(authenticated)
        self.assertEqual(principal, "alice@example.com")

    @patch.dict(
        os.environ,
        {
            "APP_TRUSTED_AUTH_HEADER": "X-Forwarded-Authenticated",
            "APP_TRUSTED_AUTH_VALUE": "true",
            "APP_TRUSTED_USER_HEADER": "X-Authenticated-User",
        },
        clear=False,
    )
    def test_trusted_header_auth_supports_expected_value_and_user_header(self) -> None:
        headers = {
            "x-forwarded-authenticated": "true",
            "x-authenticated-user": "alice@example.com",
        }
        authenticated, principal = _check_trusted_header_auth(headers)
        self.assertTrue(authenticated)
        self.assertEqual(principal, "alice@example.com")

    @patch.dict(
        os.environ,
        {
            "APP_TRUSTED_AUTH_HEADER": "X-Forwarded-Authenticated",
            "APP_TRUSTED_AUTH_VALUE": "true",
        },
        clear=False,
    )
    def test_trusted_header_auth_rejects_wrong_expected_value(self) -> None:
        headers = {"x-forwarded-authenticated": "false"}
        authenticated, principal = _check_trusted_header_auth(headers)
        self.assertFalse(authenticated)
        self.assertEqual(principal, "")


if __name__ == "__main__":
    unittest.main()
