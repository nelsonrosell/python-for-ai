import os
import unittest
from unittest.mock import patch

from streamlit_app import (
    _check_trusted_header_auth,
    _get_header_value,
    _get_password_lock_state,
    _is_anonymous_dev_auth_allowed,
    _record_failed_password_attempt,
    _validate_trusted_header_auth_config,
)


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

    @patch.dict(os.environ, {}, clear=False)
    def test_anonymous_dev_auth_defaults_to_disabled(self) -> None:
        os.environ.pop("APP_ALLOW_ANONYMOUS_DEV_AUTH", None)
        self.assertFalse(_is_anonymous_dev_auth_allowed())

    @patch.dict(
        os.environ,
        {
            "APP_ALLOW_ANONYMOUS_DEV_AUTH": "true",
        },
        clear=False,
    )
    def test_anonymous_dev_auth_can_be_explicitly_enabled(self) -> None:
        self.assertTrue(_is_anonymous_dev_auth_allowed())

    @patch.dict(
        os.environ,
        {
            "APP_PASSWORD_MAX_ATTEMPTS": "3",
            "APP_PASSWORD_LOCKOUT_SECONDS": "45",
        },
        clear=False,
    )
    def test_failed_password_attempts_trigger_lockout(self) -> None:
        state: dict[str, object] = {}

        first_message = _record_failed_password_attempt(state, now=100.0)
        second_message = _record_failed_password_attempt(state, now=101.0)
        third_message = _record_failed_password_attempt(state, now=102.0)

        self.assertEqual(
            first_message, "Incorrect password. Please try again.")
        self.assertEqual(
            second_message, "Incorrect password. Please try again.")
        self.assertEqual(
            third_message,
            "Too many incorrect password attempts. Try again in 45 second(s).",
        )
        self.assertEqual(state["password_attempt_count"], 3)
        self.assertEqual(state["password_locked_until"], 147.0)

    def test_password_lock_state_expires_and_resets_counter(self) -> None:
        state: dict[str, object] = {
            "password_attempt_count": 5,
            "password_locked_until": 150.0,
        }

        locked, message = _get_password_lock_state(state, now=151.0)

        self.assertFalse(locked)
        self.assertEqual(message, "")
        self.assertEqual(state["password_attempt_count"], 0)
        self.assertEqual(state["password_locked_until"], 0.0)

    @patch.dict(
        os.environ,
        {
            "APP_TRUSTED_AUTH_HEADER": "X-Authenticated-User",
            "APP_TRUSTED_AUTH_VALUE": "",
            "APP_TRUSTED_USER_HEADER": "",
        },
        clear=False,
    )
    def test_trusted_header_config_requires_expected_value_outside_dev(self) -> None:
        self.assertEqual(
            _validate_trusted_header_auth_config("prod"),
            "APP_TRUSTED_AUTH_VALUE must be configured when APP_TRUSTED_AUTH_HEADER is used outside dev.",
        )

    @patch.dict(
        os.environ,
        {
            "APP_TRUSTED_AUTH_HEADER": "X-Forwarded-Authenticated",
            "APP_TRUSTED_AUTH_VALUE": "true",
            "APP_TRUSTED_USER_HEADER": "X-Forwarded-Authenticated",
        },
        clear=False,
    )
    def test_trusted_header_config_requires_distinct_user_header_outside_dev(self) -> None:
        self.assertEqual(
            _validate_trusted_header_auth_config("prod"),
            "APP_TRUSTED_USER_HEADER must be different from APP_TRUSTED_AUTH_HEADER outside dev.",
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
    def test_trusted_header_config_allows_legacy_dev_setup(self) -> None:
        self.assertEqual(_validate_trusted_header_auth_config("dev"), "")


if __name__ == "__main__":
    unittest.main()
